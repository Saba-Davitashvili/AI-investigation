import argparse
import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from groq import RateLimitError

from answer_judge import judge_answer
from config import BASE_DIRECTORY


API_URL = "http://127.0.0.1:8000"
PAUSE_SECONDS = 30


def request_json(path, body=None):
    headers = {"Content-Type": "application/json"}
    password = os.getenv("DEMO_PASSWORD", "")
    if password:
        credentials = os.getenv("DEMO_USERNAME", "reviewer") + ":" + password
        headers["Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode()
    request = Request(
        os.getenv("EVALUATION_API_URL", API_URL).rstrip("/") + path,
        data=(
            json.dumps(body).encode("utf-8")
            if body is not None
            else None
        ),
        headers=headers,
        method="POST" if body is not None else "GET"
    )

    with urlopen(request, timeout=180) as response:
        return json.load(response)


def retry_rate_limits(operation):
    for attempt in range(4):
        try:
            return operation()

        except (HTTPError, RateLimitError) as error:
            is_rate_limit = (
                isinstance(error, RateLimitError)
                or error.code == 429
            )

            if not is_rate_limit or attempt == 3:
                raise

            delay = min(60, 15 * (2 ** attempt))
            print(f"Rate limited; retrying in {delay} seconds.")
            time.sleep(delay)


def save_report(path, report):
    report["updated_at"] = datetime.now(timezone.utc).isoformat()

    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temporary_path.replace(path)


def main():
    load_dotenv(BASE_DIRECTORY / ".env")
    global PAUSE_SECONDS
    PAUSE_SECONDS = max(0, int(os.getenv("EVALUATION_PAUSE_SECONDS", "30")))

    directory = BASE_DIRECTORY / "data" / "corpus"
    question_bytes = (
        directory / "evaluation_questions.json"
    ).read_bytes()
    questions = json.loads(question_bytes)
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.limit is not None:
        if not 1 <= args.limit <= len(questions):
            parser.error("Limit must be between 1 and the question count.")

        questions = questions[:args.limit]

    health = request_json("/health")
    uploads = request_json("/documents")

    manifest_bytes = (
        directory / "index_manifest.json"
    ).read_bytes()
    manifest = json.loads(manifest_bytes)

    if health.get("storage_backend") == "cloud":
        digest = hashlib.sha256()
        with (directory / "chunks_fixed_token.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    digest.update(json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True).encode())
        if health.get("corpus_fingerprint") != digest.hexdigest():
            raise ValueError("Cloud corpus fingerprint differs from the local evaluation corpus.")
    elif health["collection"] != manifest["collection"]:
        raise ValueError(
            "API collection does not match the local index manifest."
        )

    code_fingerprints = {}

    for filename in [
        "api.py",
        "config.py",
        "demo_security.py",
        "investigator.py",
        "answer_judge.py",
        "uploaded_index.py",
        "bm25_index.py",
        "semantic_search.py",
        "hybrid_search.py",
        "cloud_embeddings.py",
        "cloud_runtime.py",
        "cloud_search.py",
        "cloud_storage.py",
        "document_store.py",
        "evaluate_answers.py"
    ]:
        code_fingerprints[filename] = hashlib.sha256(
            (BASE_DIRECTORY / filename).read_bytes()
        ).hexdigest()

    configuration = {
        "selected_question_ids": [
            question["id"] for question in questions
        ],
        "questions_sha256": hashlib.sha256(
            question_bytes
        ).hexdigest(),
        "index_manifest_sha256": hashlib.sha256(
            manifest_bytes
        ).hexdigest(),
        "generator_model": os.getenv(
            "GROQ_MODEL", "openai/gpt-oss-120b"
        ),
        "judge_model": os.getenv(
            "GROQ_JUDGE_MODEL",
            os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        ),
        "uploaded_document_versions": sorted(
            (document["id"], document["version"])
            for document in uploads["documents"]
        ),
        "code_fingerprints": code_fingerprints,
        "api_configuration": health,
        "evaluation_version": 2
    }

    signature = hashlib.sha256(
        json.dumps(configuration, sort_keys=True).encode("utf-8")
    ).hexdigest()

    reports_directory = BASE_DIRECTORY / "reports"
    reports_directory.mkdir(exist_ok=True)

    report_path = (
        reports_directory / f"answers_{signature[:16]}.json"
    )

    if report_path.exists():
        report = json.loads(
            report_path.read_text(encoding="utf-8")
        )
        print("Resuming existing evaluation.")
    else:
        report = {
            "configuration": configuration,
            "question_count": len(questions),
            "cases": {}
        }

    print("Keep the API running.")
    print("Do not change documents, code or model settings during this run.")
    print(f"Report: {report_path}")

    for number, question in enumerate(questions, start=1):
        question_id = question["id"]

        case = report["cases"].setdefault(
            question_id,
            {
                "question": question["question"],
                "reference_answer": question["answer"]
            }
        )

        if "grade" in case:
            print(f"{number}/{len(questions)} already completed.")
            continue

        case.pop("error", None)
        stop_for_quota = False

        try:
            if "investigation" not in case:
                print(f"{number}/{len(questions)} investigating…")

                started = time.perf_counter()

                case["investigation"] = retry_rate_limits(
                    lambda: request_json(
                        "/investigate",
                        {"question": question["question"]}
                    )
                )

                case["investigation_seconds"] = (
                    time.perf_counter() - started
                )

                save_report(report_path, report)
                time.sleep(PAUSE_SECONDS)

            print(f"{number}/{len(questions)} grading…")

            case["grade"] = retry_rate_limits(
                lambda: judge_answer(
                    question["question"],
                    question["answer"],
                    case["investigation"]
                )
            )

            print(
                "Correct:",
                case["grade"]["answer_correct"]
            )

        except Exception as error:
            stop_for_quota = isinstance(error, RateLimitError) or (isinstance(error, HTTPError) and error.code == 429)
            case["error"] = {
                "type": type(error).__name__,
                "message": str(error)[:1000]
            }
            print(f"Case failed: {type(error).__name__}: {error}")

        save_report(report_path, report)
        if stop_for_quota:
            print("Provider quota is unavailable. Progress saved; resume after capacity recovers.")
            break
        time.sleep(PAUSE_SECONDS)

    cases = list(report["cases"].values())
    grades = [
        case["grade"]
        for case in cases
        if "grade" in case
    ]

    correct = sum(
        grade["answer_correct"]
        for grade in grades
    )
    supported = sum(
        grade["supported_findings"]
        for grade in grades
    )
    findings = sum(
        grade["finding_count"]
        for grade in grades
    )
    valid_citations = sum(
        grade["valid_quote_citations"]
        for grade in grades
    )
    citations = sum(
        grade["citation_count"]
        for grade in grades
    )

    summary = {
        "total_questions": len(questions),
        "graded_questions": len(grades),
        "failed_questions": sum(
            "error" in case for case in cases
        ),
        "pending_questions": len(questions) - len(grades) - sum("error" in case for case in cases),
        "correct_answers": correct,
        "accuracy_on_graded_questions": (
            correct / len(grades) if grades else None
        ),
        "correct_over_total_questions": (
            correct / len(questions)
        ),
        "finding_support_rate": (
            supported / findings if findings else None
        ),
        "citation_quote_validity": (
            valid_citations / citations if citations else None
        )
    }

    report["summary"] = summary
    save_report(report_path, report)

    print("\nANSWER EVALUATION SUMMARY")

    for name, value in summary.items():
        if isinstance(value, float):
            print(f"{name}: {value:.3f}")
        else:
            print(f"{name}: {value}")

    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()