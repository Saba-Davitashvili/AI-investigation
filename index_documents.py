import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models


from config import BASE_DIRECTORY, MODEL_NAME, COLLECTION_NAME


def main():
    from sentence_transformers import SentenceTransformer
    document_path = (
        BASE_DIRECTORY / "data" / "sample_documents.json"
    )

    with document_path.open(encoding="utf-8") as file:
        documents = json.load(file)

    print(f"Loaded {len(documents)} passages.")
    print("Loading embedding model...")

    model = SentenceTransformer(MODEL_NAME, device="cpu")

    texts = [
        f"{document['title']}\n{document['text']}"
        for document in documents
    ]

    print("Creating embeddings...")

    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    try:
        if not client.collection_exists(COLLECTION_NAME):
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=vectors.shape[1],
                    distance=models.Distance.COSINE
                )
            )

        points = [
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, document["id"])),
                vector=vector.tolist(),
                payload=document
            )
            for document, vector in zip(documents, vectors)
        ]

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True
        )

        count = client.count(
            collection_name=COLLECTION_NAME,
            exact=True
        ).count

        print(f"Vector dimensions: {vectors.shape[1]}")
        print(f"Stored passages: {count}")

    finally:
        client.close()


if __name__ == "__main__":
    main()