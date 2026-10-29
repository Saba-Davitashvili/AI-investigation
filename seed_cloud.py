"""One-off corpus upload. Run on the indexing PC, never during web startup.

Does not overwrite an existing corpus collection. Interrupted uploads can resume
only when their input fingerprint and embedding backend exactly match.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv

from config import BASE_DIRECTORY
from cloud_embeddings import BACKEND_ID, OnnxMiniLM
from cloud_runtime import cloud_client, create_collection, write_batch
from cloud_search import corpus_statistics
import cloud_storage as storage


def records(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main():
    load_dotenv(BASE_DIRECTORY / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, default=BASE_DIRECTORY / "data/corpus/chunks_fixed_token.jsonl")
    args = parser.parse_args()
    path = args.chunks
    digest = hashlib.sha256()
    parents = set()
    for chunk in records(path):
        digest.update(json.dumps(chunk, ensure_ascii=False, sort_keys=True).encode())
        parents.add(chunk["parent_id"])
    if len(parents) < 50000:
        raise SystemExit("Refusing to seed fewer than 50,000 source documents.")
    fingerprint = digest.hexdigest()
    print("Counting corpus terms...")
    vocabulary, count, average = corpus_statistics(records(path))
    manifest = {"chunk_count": count, "source_documents": len(parents), "average_length": average,
                "backend": BACKEND_ID, "input_fingerprint": fingerprint}
    name = os.getenv("QDRANT_CORPUS_COLLECTION", "trace_corpus_cloud_v1")
    # Require a separate named cloud corpus; never replace the local/evaluation index.
    if not name.startswith("trace_corpus_cloud_"):
        raise SystemExit("Use a trace_corpus_cloud_ collection name for this migration.")
    storage.initialize_search_store()
    client = cloud_client()
    try:
        if client.collection_exists(name):
            old = storage.metadata(name, require_complete=False)
            if old != manifest:
                raise SystemExit("Existing cloud corpus has different input/settings. Choose a NEW collection name.")
            print("Resuming identical corpus upload.")
        else:
            storage.save_statistics(name, manifest, vocabulary)
            create_collection(client, name)
        model = OnnxMiniLM(os.getenv("ONNX_MODEL_DIRECTORY") or None)
        batch = []
        visited = 0
        for chunk in records(path):
            batch.append(chunk)
            if len(batch) == 32:
                upload_missing(client, name, model, batch, vocabulary, average)
                visited += len(batch)
                print(f"Visited {visited}/{count}", flush=True)
                batch = []
        if batch:
            upload_missing(client, name, model, batch, vocabulary, average)
        stored = client.count(name, exact=True).count
        if stored != count:
            raise RuntimeError("Cloud stored count mismatch; index remains incomplete.")
        storage.mark_complete(name)
        print(f"Verified {len(parents)} source documents and {stored} cloud chunks.")
    finally:
        client.close()


def upload_missing(client, name, model, batch, vocabulary, average):
    found = client.retrieve(name, ids=[str(uuid5(NAMESPACE_URL, chunk["id"])) for chunk in batch],
                            with_payload=False, with_vectors=False)
    existing = {str(point.id) for point in found}
    missing = [chunk for chunk in batch if str(uuid5(NAMESPACE_URL, chunk["id"])) not in existing]
    if missing:
        write_batch(client, name, model, missing, vocabulary, average)


if __name__ == "__main__":
    main()
