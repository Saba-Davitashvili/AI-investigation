"""Cloud adapter regressions using real Qdrant; no cloud credentials or LLM."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from qdrant_client import QdrantClient
from bm25_index import BM25Index
from cloud_search import corpus_statistics, document_sparse, query_sparse
from cloud_runtime import CloudUploads, create_collection, write_batch, cloud_search_all, UPLOAD_COLLECTION
from cloud_storage import SharedUploadLock
from test_closeout import FakeModel
from document_reader import read_document
import document_store as store
from threading import RLock


class SparseBM25Tests(unittest.TestCase):
    def setUp(self):
        self.documents = [dict(id=str(i), parent_id=str(i), title='Synthetic', text=text)
                          for i, text in enumerate(['payment timeout payment', 'cat sleeps', 'payment request timeout'])]
        self.vocabulary, self.count, self.average = corpus_statistics(self.documents)

    def test_qdrant_sparse_matches_existing_bm25_scores(self):
        client = QdrantClient(':memory:')
        try:
            create_collection(client, 'test', 4)
            write_batch(client, 'test', FakeModel(), self.documents, self.vocabulary, self.average)
            for query in ['payment', 'payment timeout', 'PAYMENT, payment!', 'cat', 'unknown']:
                expected = BM25Index(self.documents).search(query)
                sparse = query_sparse(query, self.vocabulary, self.count)
                points = client.query_points('test', query=sparse, using='keyword', limit=20, with_payload=True).points if sparse.indices else []
                self.assertEqual({x['document']['id'] for x in expected}, {p.payload['id'] for p in points})
                actual = {p.payload['id']: p.score for p in points}
                for item in expected:
                    self.assertAlmostEqual(item['score'], actual[item['document']['id']], places=5)
        finally:
            client.close()

    def test_vocabulary_ids_are_deterministic(self):
        self.assertEqual(self.vocabulary, corpus_statistics(reversed(self.documents))[0])

    def test_query_repeats_are_not_counted_twice(self):
        self.assertEqual(query_sparse('payment', self.vocabulary, self.count), query_sparse('payment payment', self.vocabulary, self.count))

    def test_empty_corpus_and_unknown_query_are_empty(self):
        self.assertEqual(corpus_statistics([]), ({}, 0, 0))
        self.assertEqual(query_sparse('unknown', {}, 0).indices, [])


class CloudUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.db_patch = patch.object(store, 'DATABASE_PATH', self.path / 'docs.sqlite')
        self.db_patch.start()
        store.initialize_store()
        self.stats, self.vocabulary = {}, {}
        def save(name, meta, vocabulary, complete=False):
            self.stats[name] = {**meta, '_complete': complete}
            self.vocabulary[name] = vocabulary
        def meta(name, require_complete=True):
            if require_complete and not self.stats[name]['_complete']:
                raise RuntimeError('Index incomplete')
            return self.stats[name]
        def complete(name):
            self.stats[name]['_complete'] = True
        self.patches = [patch('cloud_runtime.storage.SharedUploadLock', RLock),
                        patch('cloud_runtime.storage.save_statistics', side_effect=save),
                        patch('cloud_runtime.storage.mark_complete', side_effect=complete),
                        patch('cloud_runtime.storage.metadata', side_effect=meta),
                        patch('cloud_runtime.storage.lookup_terms', side_effect=lambda name, words: {w:self.vocabulary[name][w] for w in words if w in self.vocabulary[name]})]
        for item in self.patches:
            item.start()
        self.client = QdrantClient(path=str(self.path / 'qdrant'))
        self.model = FakeModel()
        corpus = [dict(id='corpus-1',parent_id='source-1',title='Synthetic corpus',text='A cat sleeps.')]
        vocab, count, average = corpus_statistics(corpus)
        create_collection(self.client, 'corpus-test', 4)
        write_batch(self.client, 'corpus-test', self.model, corpus, vocab, average)
        save('corpus-test', {'chunk_count':count, 'average_length':average}, vocab, True)
        self.uploads = CloudUploads(self.client, self.model)
        self.uploads.refresh()
        self.state = NS(client=self.client, model=self.model, collection='corpus-test', upload_index=self.uploads)

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def save(self, text):
        content = text.encode()
        result = store.save_document(read_document('synthetic.txt',content),content)
        self.uploads.refresh()
        return result['document']

    def test_update_and_delete_remove_old_payloads_in_every_mode(self):
        doc = self.save('Project OLD7391 has a budget of 1200 GEL.')
        self.assertTrue(cloud_search_all(self.state, 'OLD7391', 'keyword'))
        content = b'Project NEW7391 has a budget of 1800 GEL.'
        store.replace_document(doc['id'], read_document('new.md',content), content)
        self.uploads.refresh()
        self.assertFalse(cloud_search_all(self.state, 'OLD7391', 'keyword'))
        self.assertTrue(cloud_search_all(self.state, 'NEW7391', 'keyword'))
        for mode in ['keyword','semantic','hybrid']:
            found = cloud_search_all(self.state, 'NEW7391', mode, 20)
            changed = [x['document'] for x in found if x['document']['parent_id']==doc['id']]
            self.assertTrue(changed)
            self.assertTrue(all(x['version']==2 and 'OLD7391' not in x['text'] for x in changed))
        store.delete_document(doc['id']); self.uploads.refresh()
        for mode in ['keyword','semantic','hybrid']:
            self.assertFalse(any(x['document']['parent_id']==doc['id'] for x in cloud_search_all(self.state,'NEW7391',mode,20)))

    def test_persistent_qdrant_and_documents_survive_client_reopen(self):
        doc = self.save('Restart PERSIST7391 test.')
        self.client.close()
        self.client = QdrantClient(path=str(self.path/'qdrant'))
        self.uploads = CloudUploads(self.client,self.model)
        self.uploads.refresh()
        self.state.client=self.client; self.state.upload_index=self.uploads
        self.assertEqual(store.get_document(doc['id'])['text'], 'Restart PERSIST7391 test.')
        self.assertEqual(cloud_search_all(self.state,'PERSIST7391','keyword')[0]['document']['parent_id'],doc['id'])

    def test_failed_indexing_is_not_silently_searchable(self):
        from uploaded_index import UploadIndexError
        self.save('Synthetic failure check.')
        with patch.object(self.client,'upsert',side_effect=RuntimeError('Fixture failure')):
            with self.assertRaises(UploadIndexError):
                self.uploads.refresh()
        self.assertFalse(self.uploads.ready)
        with self.assertRaises(UploadIndexError):
            cloud_search_all(self.state,'failure')

    def test_search_dependency_error_is_explicit(self):
        from uploaded_index import UploadIndexError
        with patch('cloud_runtime.storage.metadata',side_effect=RuntimeError('Offline')):
            with self.assertRaises(UploadIndexError):
                cloud_search_all(self.state,'cat')


class CloudBoundaryTests(unittest.TestCase):
    def test_postgres_adapter_binds_values_and_translates_schema(self):
        from unittest.mock import MagicMock
        connection = MagicMock()
        adapter = store.PostgresAdapter(connection)
        value = "x'); DROP TABLE documents; --"
        adapter.execute('SELECT * FROM documents WHERE id = ?', (value,))
        connection.execute.assert_called_once_with('SELECT * FROM documents WHERE id = %s', (value,))

    def test_cloud_store_requires_connection_environment(self):
        import cloud_storage
        with patch.dict(os.environ, {'DATABASE_URL':''}):
            with self.assertRaises(RuntimeError):
                with cloud_storage.connection():
                    pass

    def test_public_database_requires_tls(self):
        import cloud_storage
        with patch.dict(os.environ, {'DATABASE_URL':'postgresql://fixture.invalid/database'}):
            with self.assertRaisesRegex(RuntimeError,'TLS'):
                with cloud_storage.connection():
                    pass

    def test_reentrant_lock_opens_one_shared_transaction(self):
        from contextlib import contextmanager
        from unittest.mock import MagicMock
        conn = MagicMock()
        opened = []
        @contextmanager
        def connection():
            opened.append(True)
            yield conn
        with patch('cloud_storage.connection', connection):
            lock = SharedUploadLock()
            with lock:
                with lock:
                    self.assertEqual(len(opened),1)
            with lock:
                self.assertEqual(len(opened),2)
        self.assertEqual(conn.execute.call_count,2)

    def test_free_demo_capacity_rolls_back_insert(self):
        from unittest.mock import MagicMock
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value={'count':21,'text_size':10,'file_size':10}
        with patch.dict(os.environ, {'STORAGE_BACKEND':'cloud'}):
            with self.assertRaises(store.DocumentCapacityError):
                store.enforce_storage_budget(conn)


class CloudRunnerPreparationTests(unittest.TestCase):
    def test_cloud_chunk_builder_preserves_local_chunks_and_source_offsets(self):
        import prepare_cloud_chunks as builder
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); directory=root/'data/corpus'; directory.mkdir(parents=True)
            document={'id':'fixture-1','title':'Synthetic','text':'Budget is 1200 GEL. Project PERSIST7391.',
                      'source':'synthetic','config':'fixture','split':'test'}
            (directory/'documents.jsonl').write_text(json.dumps(document)+'\n')
            (directory/'manifest.json').write_text(json.dumps({'unique_passages':1,'corpus_sha256':'fixture'}))
            legacy=directory/'chunks_fixed_token.jsonl'; legacy.write_bytes(b'local-index-must-stay-unchanged')
            with patch.object(builder,'BASE_DIRECTORY',root), patch.object(builder,'verify_corpus') as verified, patch.object(builder,'OnnxMiniLM',return_value=FakeModel()):
                builder.main()
                verified.assert_called_once()
            self.assertEqual(legacy.read_bytes(),b'local-index-must-stay-unchanged')
            chunks=[json.loads(line) for line in (directory/'chunks_cloud.jsonl').read_text().splitlines()]
            self.assertTrue(chunks)
            for chunk in chunks:
                self.assertEqual(chunk['text'],document['text'][chunk['char_start']:chunk['char_end']])
            digest=hashlib.sha256()
            for chunk in chunks:
                digest.update(json.dumps(chunk,ensure_ascii=False,sort_keys=True).encode())
            manifest=json.loads((directory/'cloud_index_manifest.json').read_text())
            self.assertEqual(manifest['input_fingerprint'],digest.hexdigest())
            self.assertEqual(manifest['stored_chunks'],len(chunks))


if __name__ == '__main__':
    unittest.main()
