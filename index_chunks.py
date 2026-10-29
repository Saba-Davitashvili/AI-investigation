from config import embedding_dimension
import json
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from config import BASE_DIRECTORY, MODEL_NAME


BATCH_SIZE = 32

COLLECTIONS = {
    "fixed_token": "hotpot_fixed_token_v1",
    "sentence_boundary": "hotpot_sentence_boundary_v1"
}


def main():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    try:
        for strategy, collection_name in COLLECTIONS.items():
            input_path = (
                BASE_DIRECTORY / "data" / f"chunks_{strategy}.json"
            )

            chunks = json.loads(
                input_path.read_text(encoding="utf-8")
            )

            if not chunks:
                raise ValueError(f"No chunks found for {strategy}")

            if not client.collection_exists(collection_name):
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=embedding_dimension(model),
                        distance=models.Distance.COSINE
                    )
                )

            print(f"\nIndexing {strategy}: {len(chunks)} chunks")

            for start in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[start:start + BATCH_SIZE]

                texts = [
                    f"{chunk['title']}\n{chunk['text']}"
                    for chunk in batch
                ]

                vectors = model.encode(
                    texts,
                    normalize_embeddings=True
                )

                points = [
                    models.PointStruct(
                        id=str(uuid5(NAMESPACE_URL, chunk["id"])),
                        vector=vector.tolist(),
                        payload=chunk
                    )
                    for chunk, vector in zip(batch, vectors)
                ]

                client.upsert(
                    collection_name=collection_name,
                    points=points,
                    wait=True
                )

                completed = start + len(batch)
                print(f"Indexed {completed}/{len(chunks)}")

            stored_count = client.count(
                collection_name=collection_name,
                exact=True
            ).count

            if stored_count != len(chunks):
                raise ValueError(
                    f"Count mismatch: expected {len(chunks)}, "
                    f"found {stored_count}. "
                    "Collection may contain older chunks."
                )

            print(f"Verified stored chunks: {stored_count}")

    finally:
        client.close()


if __name__ == "__main__":
    main()