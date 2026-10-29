from config import embedding_dimension
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from chunk_documents import (
    MAX_TOKENS,
    OVERLAP,
    chunk_document,
    validate_chunks
)
from config import BASE_DIRECTORY, MODEL_NAME
from verify_corpus import main as verify_corpus


BATCH_SIZE = 128
EMBEDDING_BATCH_SIZE = 32


def store_batch(client, model, collection, chunks):
    point_ids = [
        str(uuid5(NAMESPACE_URL, chunk["id"]))
        for chunk in chunks
    ]

    existing = client.retrieve(
        collection_name=collection,
        ids=point_ids,
        with_payload=False,
        with_vectors=False
    )

    existing_ids = {
        str(point.id)
        for point in existing
    }

    missing = [
        (point_id, chunk)
        for point_id, chunk in zip(point_ids, chunks)
        if point_id not in existing_ids
    ]

    if not missing:
        return 0

    texts = [
        f"{chunk['title']}\n{chunk['text']}"
        for _, chunk in missing
    ]

    vectors = model.encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        normalize_embeddings=True
    )

    points = [
        models.PointStruct(
            id=point_id,
            vector=vector.tolist(),
            payload=chunk
        )
        for (point_id, chunk), vector in zip(missing, vectors)
    ]

    client.upsert(
        collection_name=collection,
        points=points,
        wait=True
    )

    return len(points)


def main():
    from sentence_transformers import SentenceTransformer
    verify_corpus()

    directory = BASE_DIRECTORY / "data" / "corpus"
    manifest = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )

    print("\nLoading embedding model...")
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    configuration = {
        "corpus_sha256": manifest["corpus_sha256"],
        "model": MODEL_NAME,
        "model_max_sequence_length": model.max_seq_length,
        "strategy": "fixed_token",
        "max_tokens": MAX_TOKENS,
        "overlap": OVERLAP,
        "pipeline_version": 1
    }

    signature = hashlib.sha256(
        json.dumps(configuration, sort_keys=True).encode("utf-8")
    ).hexdigest()

    collection = f"corpus_fixed_{signature[:16]}"

    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    chunk_path = directory / "chunks_fixed_token.jsonl"
    temporary_path = directory / "chunks_fixed_token.jsonl.tmp"

    processed_documents = 0
    processed_chunks = 0
    newly_embedded = 0
    pending = []

    print(f"Collection: {collection}")
    print("Chunking and indexing corpus...")

    try:
        if not client.collection_exists(collection):
            client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=embedding_dimension(model),
                    distance=models.Distance.COSINE
                )
            )

        with (
            (directory / "documents.jsonl").open(
                encoding="utf-8"
            ) as source,
            temporary_path.open(
                "w", encoding="utf-8"
            ) as output
        ):
            for line in source:
                document = json.loads(line)

                chunks = chunk_document(
                    document,
                    model.tokenizer,
                    "fixed_token"
                )

                validate_chunks(chunks, [document], model)

                for chunk in chunks:
                    chunk["revision"] = document["revision"]
                    chunk["origins"] = document["origins"]

                    output.write(
                        json.dumps(chunk, ensure_ascii=False) + "\n"
                    )

                    pending.append(chunk)
                    processed_chunks += 1

                    if len(pending) >= BATCH_SIZE:
                        newly_embedded += store_batch(
                            client, model, collection, pending
                        )
                        pending = []

                processed_documents += 1

                if processed_documents % 500 == 0:
                    print(
                        f"Documents: {processed_documents}/"
                        f"{manifest['unique_passages']} | "
                        f"Chunks generated: {processed_chunks} | "
                        f"New vectors stored: {newly_embedded}"
                    )

            if pending:
                newly_embedded += store_batch(
                    client, model, collection, pending
                )

        stored_count = client.count(
            collection_name=collection,
            exact=True
        ).count

        if processed_documents != manifest["unique_passages"]:
            raise ValueError("Processed document count mismatch.")

        if stored_count != processed_chunks:
            raise ValueError(
                f"Expected {processed_chunks} vectors, "
                f"found {stored_count}."
            )

        temporary_path.replace(chunk_path)

        index_manifest = {
            "configuration": configuration,
            "collection": collection,
            "source_documents": processed_documents,
            "stored_chunks": stored_count,
            "complete": True
        }

        manifest_path = directory / "index_manifest.json"
        temporary_manifest = directory / "index_manifest.json.tmp"

        temporary_manifest.write_text(
            json.dumps(index_manifest, indent=2),
            encoding="utf-8"
        )
        temporary_manifest.replace(manifest_path)

        print("\nINDEXING COMPLETE")
        print(f"Source documents: {processed_documents}")
        print(f"Stored chunks: {stored_count}")
        print(f"Newly embedded this run: {newly_embedded}")
        print(f"Collection: {collection}")

    finally:
        client.close()


if __name__ == "__main__":
    main()