import hashlib
import json
import math
from datetime import datetime, timezone
from time import perf_counter

from qdrant_client import QdrantClient

from bm25_index import BM25Index
from evaluate_retrieval import calculate_metrics
from hybrid_search import fuse_rankings
from config import BASE_DIRECTORY, MODEL_NAME
from semantic_search import search_semantic


def main():
    from sentence_transformers import SentenceTransformer
    directory = BASE_DIRECTORY / "data" / "corpus"

    manifest = json.loads(
        (directory / "index_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    question_bytes = (
        directory / "evaluation_questions.json"
    ).read_bytes()
    questions = json.loads(question_bytes)

    with (directory / "chunks_fixed_token.jsonl").open(
        encoding="utf-8"
    ) as file:
        documents = [json.loads(line) for line in file]

    if len(documents) != manifest["stored_chunks"]:
        raise ValueError("Chunk count does not match manifest.")

    print("Building keyword index...")
    keyword_index = BM25Index(documents)

    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    measurements = {
        "keyword": [],
        "semantic": [],
        "hybrid": []
    }

    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    try:
        count = client.count(
            collection_name=manifest["collection"],
            exact=True
        ).count

        if count != manifest["stored_chunks"]:
            raise ValueError("Vector count does not match manifest.")

        for number, question in enumerate(questions, start=1):
            query = question["question"]
            expected = set(
                question["supporting_facts"]["title"]
            )

            if not expected:
                raise ValueError("Question has no expected sources.")

            started = perf_counter()
            keyword = keyword_index.search(query, limit=20)
            keyword_seconds = perf_counter() - started

            started = perf_counter()
            semantic = search_semantic(
                query,
                model,
                client,
                limit=20,
                collection_name=manifest["collection"]
            )
            semantic_seconds = perf_counter() - started

            started = perf_counter()
            hybrid = fuse_rankings(
                [keyword, semantic],
                limit=20
            )
            fusion_seconds = perf_counter() - started

            configurations = [
                ("keyword", keyword, keyword_seconds),
                ("semantic", semantic, semantic_seconds),
                (
                    "hybrid",
                    hybrid,
                    keyword_seconds
                    + semantic_seconds
                    + fusion_seconds
                )
            ]

            for mode, results, seconds in configurations:
                measurements[mode].append({
                    "question_id": question["id"],
                    "question": query,
                    "expected_titles": sorted(expected),
                    "metrics": calculate_metrics(results, expected),
                    "latency_seconds": seconds,
                    "top_5": [
                        {
                            "id": result["document"]["id"],
                            "parent_id": result["document"]["parent_id"],
                            "title": result["document"]["title"],
                            "score": result["score"]
                        }
                        for result in results[:5]
                    ]
                })

            print(f"Evaluated {number}/{len(questions)}")

    finally:
        client.close()

    summaries = {}

    for mode, rows in measurements.items():
        metrics = {
            name: sum(row["metrics"][name] for row in rows) / len(rows)
            for name in rows[0]["metrics"]
        }

        latencies = sorted(
            row["latency_seconds"] for row in rows
        )

        metrics["mean_latency_seconds"] = (
            sum(latencies) / len(latencies)
        )
        metrics["p95_latency_seconds"] = latencies[
            math.ceil(0.95 * len(latencies)) - 1
        ]

        summaries[mode] = metrics

        print(f"\n{mode.upper()}")

        for name, value in metrics.items():
            print(f"  {name}: {value:.3f}")

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question_count": len(questions),
        "questions_sha256": hashlib.sha256(
            question_bytes
        ).hexdigest(),
        "index_manifest": manifest,
        "candidate_limit": 20,
        "rrf_k": 60,
        "measurement": "supporting source-title coverage",
        "latency_method": (
            "Sequential local requests, excluding startup; "
            "hybrid time sums keyword, semantic and fusion times. "
            "No explicit warmup."
        ),
        "summary": summaries,
        "details": measurements
    }

    report_directory = BASE_DIRECTORY / "reports"
    report_directory.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    output_path = report_directory / f"corpus_{timestamp}.json"

    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\nReport saved: {output_path}")


if __name__ == "__main__":
    main()