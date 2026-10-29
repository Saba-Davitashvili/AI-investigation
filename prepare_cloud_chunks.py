"""Build cloud chunks on a hosted runner without changing a local index."""
import hashlib
import json
import os

from chunk_documents import chunk_document, validate_chunks
from cloud_embeddings import BACKEND_ID, OnnxMiniLM
from config import BASE_DIRECTORY, MODEL_NAME
from verify_corpus import main as verify_corpus


def main():
    verify_corpus()
    directory = BASE_DIRECTORY / 'data' / 'corpus'
    source_manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    model = OnnxMiniLM(os.getenv('ONNX_MODEL_DIRECTORY') or None)
    destination = directory / 'chunks_cloud.jsonl'
    temporary = destination.with_suffix('.tmp')
    count = 0
    digest = hashlib.sha256()
    with (directory / 'documents.jsonl').open(encoding='utf-8') as sources, temporary.open('w', encoding='utf-8') as output:
        for line in sources:
            document = json.loads(line)
            chunks = chunk_document(document, model.tokenizer, 'fixed_token')
            validate_chunks(chunks, [document], model)
            for chunk in chunks:
                output.write(json.dumps(chunk,ensure_ascii=False)+'\n')
                digest.update(json.dumps(chunk,ensure_ascii=False,sort_keys=True).encode())
                count += 1
    temporary.replace(destination)
    manifest = {'complete': True, 'source_documents':source_manifest['unique_passages'],
                'stored_chunks':count, 'collection':os.getenv('QDRANT_CORPUS_COLLECTION','trace_corpus_cloud_v1'),
                'configuration':{'model':MODEL_NAME,'embedding_backend':BACKEND_ID},
                'input_fingerprint':digest.hexdigest(), 'source_corpus_sha256':source_manifest['corpus_sha256'],
                'scope':'Validated chunk file only; cloud vector seeding is a separate step.'}
    (directory / 'cloud_index_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f"Prepared {count} cloud chunks from {manifest['source_documents']} source documents.")


if __name__=='__main__':
    main()
