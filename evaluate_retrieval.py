import json

from qdrant_client import QdrantClient

from hybrid_search import fuse_rankings
from config import (
    BASE_DIRECTORY,
    COLLECTION_NAME,
    MODEL_NAME
)
from search import search_documents
from semantic_search import search_semantic


def calculate_metrics(results, expected_titles):
    retrieved_titles = [
        result["document"]["title"]
        for result in results
    ]

    first_relevant_rank = next(
        (
            position
            for position, title in enumerate(
                retrieved_titles, start=1
            )
            if title in expected_titles
        ),
        None
    )

    found_at_2 = expected_titles & set(retrieved_titles[:2])
    found_at_5 = expected_titles & set(retrieved_titles[:5])

    return {
        "recall_at_2": len(found_at_2) / len(expected_titles),
        "recall_at_5": len(found_at_5) / len(expected_titles),
        "all_sources_at_5": float(found_at_5 == expected_titles),
        "mrr_at_20": (
            1 / first_relevant_rank
            if first_relevant_rank is not None
            else 0.0
        )
    }


def main():
    from sentence_transformers import SentenceTransformer
    data_directory = BASE_DIRECTORY / "data"

    documents = json.loads(
        (data_directory / "sample_documents.json").read_text(
            encoding="utf-8"
        )
    )
    questions = json.loads(
        (data_directory / "sample_questions.json").read_text(
            encoding="utf-8"
        )
    )

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    measurements = {"semantic": [], "hybrid": []}

    try:
        for number, question in enumerate(questions, start=1):
            query = question["question"]
            expected_titles = set(
                question["supporting_facts"]["title"]
            )

            if not expected_titles:
                raise ValueError("Question has no supporting sources.")

            semantic = search_semantic(
                query, model, client, limit=20
            )
            keyword = search_documents(query, documents)[:20]
            hybrid = fuse_rankings(
                [keyword, semantic], limit=20
            )

            for name, results in [
                ("semantic", semantic),
                ("hybrid", hybrid)
            ]:
                measurements[name].append(
                    calculate_metrics(results, expected_titles)
                )

            print(f"Evaluated {number}/{len(questions)}")

    finally:
        client.close()

    for name, rows in measurements.items():
        print(f"\n{name.upper()}")

        for metric in rows[0]:
            average = sum(row[metric] for row in rows) / len(rows)
            print(f"{metric}: {average:.3f}")


if __name__ == "__main__":
    main()