from qdrant_client import QdrantClient

from config import (
    BASE_DIRECTORY,
    COLLECTION_NAME,
    MODEL_NAME
)


def search_semantic(
    query,
    model,
    client,
    limit=5,
    collection_name=COLLECTION_NAME
):
    query_vector = model.encode(
        query,
        normalize_embeddings=True
    )

    response = client.query_points(
        collection_name=collection_name,
        query=query_vector.tolist(),
        limit=limit,
        with_payload=True
    )

    return [
        {
            "document": point.payload,
            "score": point.score
        }
        for point in response.points
    ]

def main():
    from sentence_transformers import SentenceTransformer
    query = input("Enter a research question: ").strip()

    if not query:
        print("Please enter a question.")
        return

    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    try:
        results = search_semantic(query, model, client)

        for position, result in enumerate(results, start=1):
            document = result["document"]

            print(f"\n{position}. {document['title']}")
            print(f"Similarity: {result['score']:.4f}")
            print(f"Source ID: {document['id']}")
            print(document["text"])

    finally:
        client.close()


if __name__ == "__main__":
    main()