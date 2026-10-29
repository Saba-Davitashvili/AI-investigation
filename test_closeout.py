"""Offline regression tests. No model downloads or provider calls."""
import json
import os
import re
import tempfile
import unittest
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import document_store as store
from document_reader import read_document, DocumentReadError
from investigator import prepare_evidence, materialize_result, investigate, InvestigationError


class EvidencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.sources = {"S1": {"title": "Synthetic", "text": "პროექტი QA.\r\nBudget is 1200 GEL."}}

    def test_excerpts_are_exact_substrings_with_unicode_and_crlf(self):
        registry, _ = prepare_evidence(self.sources)
        self.assertTrue(registry)
        for evidence in registry.values():
            self.assertIn(evidence["quote"], self.sources[evidence["source_id"]]["text"])

    def test_materialization_copies_the_selected_original_text(self):
        registry, _ = prepare_evidence(self.sources)
        draft = {"status": "answered", "findings": [{"statement": "Budget is 1200 GEL.", "evidence_ids": ["S1:E2", "S1:E2"]}], "limitations": []}
        result = materialize_result(json.dumps(draft), registry, self.sources)
        self.assertEqual(result.findings[0].evidence[0].quote, "Budget is 1200 GEL.")
        self.assertEqual(len(result.findings[0].evidence), 1)

    def test_invented_evidence_id_is_rejected(self):
        registry, _ = prepare_evidence(self.sources)
        draft = {"status": "answered", "findings": [{"statement": "Unknown", "evidence_ids": ["S999:E1"]}], "limitations": []}
        with self.assertRaises(InvestigationError):
            materialize_result(json.dumps(draft), registry, self.sources)

    def test_pipeline_uses_a_fresh_synthesis_prompt_and_native_tool_plan(self):
        planning = NS(choices=[NS(message=NS(tool_calls=[NS(function=NS(name="search_sources", arguments='{"queries":["synthetic budget"]}'))]))], usage=NS(total_tokens=10))
        answer = NS(choices=[NS(message=NS(content=json.dumps({"status": "answered", "findings": [{"statement": "Budget is 1200 GEL.", "evidence_ids": ["S1:E2"]}], "limitations": []})))], usage=NS(total_tokens=20))
        client = MagicMock()
        client.chat.completions.create.side_effect = [planning, answer]
        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        doc = {"id": "chunk-1", "parent_id": "doc-1", "title": "Synthetic", "text": self.sources["S1"]["text"], "char_start": 0, "char_end": 35}
        with patch("investigator.Groq", factory), patch("investigator.load_dotenv"), patch.dict(os.environ, {"GROQ_API_KEY": "offline-test-placeholder"}):
            result = investigate("What is the budget?", lambda query, limit: [{"document": doc, "score": 1}])
        self.assertEqual(result["total_tokens"], 30)
        first, second = client.chat.completions.create.call_args_list
        self.assertIn("tools", first.kwargs)
        self.assertNotIn("tools", second.kwargs)
        self.assertEqual(second.kwargs["messages"][0]["role"], "system")
        self.assertNotIn("Call search_sources", second.kwargs["messages"][0]["content"])

    def test_unknown_native_tool_is_not_executed(self):
        planning = NS(choices=[NS(message=NS(tool_calls=[NS(function=NS(name="delete_everything", arguments="{}"))]))], usage=None)
        client = MagicMock()
        client.chat.completions.create.return_value = planning
        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        retrieve = MagicMock()
        with patch("investigator.Groq", factory), patch("investigator.load_dotenv"), patch.dict(os.environ, {"GROQ_API_KEY": "offline-test-placeholder"}):
            with self.assertRaises(InvestigationError):
                investigate("What happened?", retrieve)
        retrieve.assert_not_called()


class DocumentStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = patch.object(store, "DATABASE_PATH", Path(self.temp.name) / "documents.sqlite3")
        self.override.start()
        store.initialize_store()

    def tearDown(self):
        self.override.stop()
        self.temp.cleanup()

    def save(self, name, text):
        content = text.encode()
        return store.save_document(read_document(name, content), content)

    def test_identical_bytes_are_deduplicated_across_names(self):
        first = self.save("a.txt", "Synthetic first")
        second = self.save("different.txt", "Synthetic first")
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["document"]["id"], second["document"]["id"])
        self.assertEqual(len(store.list_documents()), 1)

    def test_replacement_preserves_id_and_creation_time_after_reopen(self):
        first = self.save("a.txt", "Budget 1200")['document']
        content = b"Budget 1800"
        updated = store.replace_document(first["id"], read_document("a.txt", content), content)
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["created_at"], first["created_at"])
        self.assertEqual(store.get_document(first["id"])["text"], "Budget 1800")

    def test_conflicting_replacement_rolls_back(self):
        first = self.save("a.txt", "First")['document']
        self.save("b.txt", "Second")
        with self.assertRaises(store.DuplicateDocumentError):
            store.replace_document(first["id"], read_document("a.txt", b"Second"), b"Second")
        self.assertEqual(store.get_document(first["id"])["text"], "First")
        self.assertEqual(store.get_document(first["id"])["version"], 1)

    def test_deletion_removes_the_record(self):
        doc = self.save("a.txt", "Delete this synthetic fixture")['document']
        self.assertTrue(store.delete_document(doc["id"]))
        self.assertIsNone(store.get_document(doc["id"]))
        self.assertFalse(store.delete_document(doc["id"]))


class FileExtractionTests(unittest.TestCase):
    def test_utf8_text_and_markdown(self):
        for name in ["notes.txt", "notes.md"]:
            with self.subTest(name=name):
                self.assertEqual(read_document(name, "# მოთხოვნები".encode())["text"], "# მოთხოვნები")

    def test_unsupported_empty_binary_and_invalid_utf8_are_rejected(self):
        for name, content in [("x.jpg", b"image"), ("x.txt", b""), ("x.txt", b"a\x00b"), ("x.txt", b"\xff\xfe")]:
            with self.subTest(name=name, content=content):
                with self.assertRaises(DocumentReadError):
                    read_document(name, content)

    def test_text_pdf_extracts_two_pages_with_correct_offsets(self):
        writer = PdfWriter()
        for text in ["Synthetic page one.", "Synthetic page two."]:
            page = writer.add_blank_page(width=612, height=792)
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(("BT /F1 12 Tf 72 700 Td (" + text + ") Tj ET").encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
        output = BytesIO()
        writer.write(output)
        result = read_document("evidence.pdf", output.getvalue())
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(len(result["pages"]), 2)
        for number, page in enumerate(result["pages"], 1):
            self.assertEqual(page["page_number"], number)
            self.assertIn("page", result["text"][page["char_start"]:page["char_end"]])

    def test_filename_path_components_are_removed(self):
        result = read_document(r"C:\fake\notes.txt", b"Synthetic")
        self.assertEqual(result["filename"], "notes.txt")


class Vector(list):
    def tolist(self):
        return list(self)


class FakeModel:
    """Deterministic adapter for plumbing tests; not a semantic-search benchmark."""
    max_seq_length = 256

    def get_embedding_dimension(self):
        return 4

    def tokenizer(self, text, **kwargs):
        offsets = [match.span() for match in re.finditer(r"\S+", text)]
        return {"input_ids": list(range(len(offsets))), "offset_mapping": offsets}

    def encode(self, texts, **kwargs):
        vector = lambda: Vector([0.0, 1.0, 0.0, 0.0])
        return vector() if isinstance(texts, str) else [vector() for _ in texts]


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from qdrant_client import QdrantClient, models
        from bm25_index import BM25Index
        from uploaded_index import UploadedIndex
        import api
        self.api = api
        self.temp = tempfile.TemporaryDirectory()
        self.override = patch.object(store, "DATABASE_PATH", Path(self.temp.name) / "documents.sqlite3")
        self.override.start()
        self.env = patch.dict(os.environ, {"APP_ENV": "local", "DEMO_PASSWORD": "", "PUBLIC_ORIGIN": ""})
        self.env.start()
        previous = api.app.router.lifespan_context
        self.previous = previous

        @asynccontextmanager
        async def lifespan(app):
            store.initialize_store()
            app.state.model = FakeModel()
            app.state.client = QdrantClient(":memory:")
            app.state.collection = "test_corpus"
            doc = {"id": "base-chunk", "parent_id": "base-doc", "title": "Baseline", "text": "General synthetic research passage.", "char_start": 0, "char_end": 35}
            app.state.client.create_collection(collection_name="test_corpus", vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE))
            app.state.client.upsert(collection_name="test_corpus", points=[models.PointStruct(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload=doc)])
            app.state.keyword_index = BM25Index([doc])
            app.state.source_count = 1
            app.state.chunk_count = 1
            app.state.upload_index = UploadedIndex(app.state.client, app.state.model)
            app.state.upload_index.refresh()
            try:
                yield
            finally:
                app.state.client.close()

        api.app.router.lifespan_context = lifespan
        self.client_context = TestClient(api.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.api.app.router.lifespan_context = self.previous
        self.env.stop()
        self.override.stop()
        self.temp.cleanup()

    def test_upload_replace_delete_remove_stale_keyword_and_vector_payloads(self):
        response = self.client.post("/documents", files={"file": ("synthetic.txt", b"Project ALPHA7391 budget is 1200 GEL.", "text/plain")})
        self.assertEqual(response.status_code, 201)
        document_id = response.json()["document"]["id"]
        self.assertTrue(response.json()["indexed"])
        response = self.client.get("/search", params={"q": "ALPHA7391", "mode": "keyword"})
        self.assertEqual(response.json()["results"][0]["document"]["parent_id"], document_id)
        response = self.client.put("/documents/" + document_id, files={"file": ("synthetic.txt", b"Project ALPHA7391 budget is 1800 GEL.", "text/plain")})
        self.assertEqual(response.json()["document"]["version"], 2)
        for mode in ["keyword", "semantic", "hybrid"]:
            response = self.client.get("/search", params={"q": "ALPHA7391", "mode": mode, "limit": 20})
            own = [r["document"] for r in response.json()["results"] if r["document"]["parent_id"] == document_id]
            self.assertTrue(own)
            self.assertTrue(all("1800" in d["text"] and "1200" not in d["text"] for d in own))
        self.assertEqual(self.client.delete("/documents/" + document_id).status_code, 204)
        for mode in ["keyword", "semantic", "hybrid"]:
            response = self.client.get("/search", params={"q": "ALPHA7391", "mode": mode, "limit": 20})
            self.assertFalse(any(r["document"]["parent_id"] == document_id for r in response.json()["results"]))

    def test_validation_statuses_and_duplicate_upload(self):
        self.assertEqual(self.client.get("/search").status_code, 422)
        self.assertEqual(self.client.get("/search?q=alpha&limit=0").status_code, 422)
        self.assertEqual(self.client.post("/documents", files={"file": ("bad.exe", b"synthetic")}).status_code, 422)
        file = {"file": ("same.txt", b"Identical synthetic file", "text/plain")}
        first = self.client.post("/documents", files=file)
        second = self.client.post("/documents", files=file)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["document"]["id"], second.json()["document"]["id"])
        self.assertEqual(self.client.get("/documents/missing").status_code, 404)

    def test_demo_gate_and_cross_origin_write_rejection(self):
        with patch.dict(os.environ, {"DEMO_PASSWORD": "synthetic-test-password", "DEMO_USERNAME": "reviewer", "PUBLIC_ORIGIN": "https://trace.example"}):
            self.assertEqual(self.client.get("/").status_code, 401)
            self.assertEqual(self.client.get("/health", auth=("reviewer", "wrong")).status_code, 401)
            self.assertEqual(self.client.get("/health", auth=("reviewer", "synthetic-test-password")).status_code, 200)
            response = self.client.delete("/documents/missing", auth=("reviewer", "synthetic-test-password"), headers={"Origin": "https://other.example"})
            self.assertEqual(response.status_code, 403)

    def test_production_without_demo_password_fails_closed(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "DEMO_PASSWORD": ""}):
            self.assertEqual(self.client.get("/health").status_code, 503)


if __name__ == "__main__":
    unittest.main()
