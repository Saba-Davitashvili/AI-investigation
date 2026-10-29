import hashlib
import json
from datetime import datetime, timezone

from qdrant_client import QdrantClient

from evaluate_retrieval import calculate_metrics
from hybrid_search import fuse_rankings
from config import (
    BASE_DIRECTORY,
    COLLECTION_NAME,
    MODEL_NAME
)
from index_chunks import COLLECTIONS
from search import search_documents
from semantic_search import search_semantic


def main():
    from sentence_transformers import SentenceTransformer
    data_directory = BASE_DIRECTORY / "data"

    questions = json.loads(
        (data_directory / "sample_questions.json").read_text(
            encoding="utf-8"
        )
    )

    configurations = {
        "whole_passage": (
            COLLECTION_NAME,
            "sample_documents.json"
        ),
        "fixed_token": (
            COLLECTIONS["fixed_token"],
            "chunks_fixed_token.json"
        ),
        "sentence_boundary": (
            COLLECTIONS["sentence_boundary"],
            "chunks_sentence_boundary.json"
        )
    }

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL_NAME,
        "question_count": len(questions),
        "candidate_limit": 20,
        "rrf_k": 60,
        "measurement": "supporting source-title coverage",
        "configurations": {}
    }

    try:
        for name, (collection, filename) in configurations.items():
            input_bytes = (data_directory / filename).read_bytes()
            documents = json.loads(input_bytes)
            measurements = {"semantic": [], "hybrid": []}
            details = []

            stored_count = client.count(
                collection_name=collection,
                exact=True
            ).count

            if stored_count != len(documents):
                raise ValueError(
                    f"{name}: index count does not match input."
                )

            for question in questions:
                query = question["question"]
                expected = set(
                    question["supporting_facts"]["title"]
                )

                if not expected:
                    raise ValueError("Missing expected sources.")

                semantic = search_semantic(
                    query,
                    model,
                    client,
                    limit=20,
                    collection_name=collection
                )

                keyword = search_documents(query, documents)[:20]
                hybrid = fuse_rankings(
                    [keyword, semantic],
                    limit=20
                )

                for mode, results in [
                    ("semantic", semantic),
                    ("hybrid", hybrid)
                ]:
                    metrics = calculate_metrics(results, expected)
                    measurements[mode].append(metrics)

                    details.append({
                        "question_id": question["id"],
                        "question": query,
                        "mode": mode,
                        "expected_titles": sorted(expected),
                        "top_5_titles": [
                            result["document"]["title"]
                            for result in results[:5]
                        ],
                        "metrics": metrics
                    })

            summary = {}

            print(f"\n{name.upper()}")

            for mode, rows in measurements.items():
                summary[mode] = {
                    metric: sum(row[metric] for row in rows) / len(rows)
                    for metric in rows[0]
                }

                print(f"  {mode}")

                for metric, value in summary[mode].items():
                    print(f"    {metric}: {value:.3f}")

            report["configurations"][name] = {
                "collection": collection,
                "record_count": len(documents),
                "input_sha256": hashlib.sha256(
                    input_bytes
                ).hexdigest(),
                "summary": summary,
                "details": details
            }

    finally:
        client.close()

    report_directory = BASE_DIRECTORY / "reports"
    report_directory.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    output_path = report_directory / f"chunking_{timestamp}.json"

    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\nReport saved: {output_path}")


if __name__ == "__main__":
    main()