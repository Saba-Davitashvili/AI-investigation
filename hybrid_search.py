import json

from qdrant_client import QdrantClient

from config import (
    BASE_DIRECTORY,
    COLLECTION_NAME,
    MODEL_NAME
)
from search import search_documents, tokenize
from semantic_search import search_semantic


def fuse_rankings(rankings, limit=5, k=60):
    combined = {}

    for ranking in rankings:
        for position, result in enumerate(ranking, start=1):
            document = result["document"]
            document_id = document["id"]

            if document_id not in combined:
                combined[document_id] = {
                    "document": document,
                    "score": 0.0
                }

            combined[document_id]["score"] += 1 / (k + position)

    ordered = sorted(
        combined.values(),
        key=lambda result: (-result["score"], result["document"]["id"])
    )

    return ordered[:limit]


def main():
    from sentence_transformers import SentenceTransformer
    query = input("Enter a research question: ").strip()

    if not tokenize(query):
        print("Please enter at least one word or number.")
        return

    document_path = (
        BASE_DIRECTORY / "data" / "sample_documents.json"
    )

    with document_path.open(encoding="utf-8") as file:
        documents = json.load(file)

    keyword_results = search_documents(query, documents)[:20]

    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    try:
        semantic_results = search_semantic(
            query,
            model,
            client,
            limit=20
        )
    finally:
        client.close()

    results = fuse_rankings([
        keyword_results,
        semantic_results
    ])

    for position, result in enumerate(results, start=1):
        document = result["document"]

        print(f"\n{position}. {document['title']}")
        print(f"Fusion score: {result['score']:.6f}")
        print(f"Source ID: {document['id']}")
        print(document["text"])


if __name__ == "__main__":
    main()