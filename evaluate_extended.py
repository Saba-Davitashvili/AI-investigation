"""Live, resumable category checks. Requires the running API and provider quota."""
import argparse
import hashlib
import json
import os
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from config import BASE_DIRECTORY


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def check_case(case, result):
    findings = result.get("findings", [])
    statement_text = normalize(" ".join(f["statement"] for f in findings))
    cited_files = set()
    references = []
    for finding in findings:
        for evidence in finding.get("evidence", []):
            source = result.get("sources", {}).get(evidence.get("source_id"))
            quote = evidence.get("quote", "")
            valid = bool(source and quote.strip() and quote in source.get("text", ""))
            references.append(valid)
            if source:
                cited_files.add(source["title"])
    checks = {
        "expected_status": result.get("status") == case["expected_status"],
        "expected_facts": all(any(normalize(value) in statement_text for value in group) for group in case["expected_fact_groups"]),
        "required_documents_cited": set(case["expected_cited_files"]).issubset(cited_files),
        "valid_quote_references": all(references),
        "limitations_present_when_needed": case["expected_status"] == "answered" or bool(result.get("limitations")),
        "evidence_present_when_needed": case["expected_status"] == "insufficient" or bool(references)
    }
    return {"checks": checks, "passed_all_assertions": all(checks.values()), "citation_count": len(references)}


def save(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main():
    load_dotenv(BASE_DIRECTORY / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("EVALUATION_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--pause", type=int, default=30)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--cleanup", action="store_true", help="Delete only fixture documents newly created by this invocation after evaluation")
    args = parser.parse_args()
    if args.pause < 0 or (args.limit is not None and not 1 <= args.limit <= 12):
        parser.error("Use a nonnegative pause and a limit from 1 to 12.")
    data_path = BASE_DIRECTORY / "qa" / "data" / "extended_cases.json"
    data = json.loads(data_path.read_text())
    cases = data["cases"][:args.limit] if args.limit else data["cases"]
    auth = (os.getenv("DEMO_USERNAME", "reviewer"), os.getenv("DEMO_PASSWORD")) if os.getenv("DEMO_PASSWORD") else None
    created = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), auth=auth, timeout=180) as client:
        health_response = client.get("/health")
        health_response.raise_for_status()
        health = health_response.json()
        print("Seeding synthetic fixtures; existing documents are not replaced.")
        for filename, text in data["documents"].items():
            response = client.post("/documents", files={"file": (filename, text.encode(), "text/plain")})
            response.raise_for_status()
            uploaded = response.json()
            if not uploaded["duplicate"]:
                created.append(uploaded["document"]["id"])
        inventory = client.get("/documents")
        inventory.raise_for_status()
        signature_data = {
            "fixtures_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "case_ids": [case["id"] for case in cases],
            "api_configuration": health,
            "source_sha256": {name: hashlib.sha256((BASE_DIRECTORY / name).read_bytes()).hexdigest() for name in ["investigator.py", "api.py", "uploaded_index.py", "cloud_embeddings.py", "cloud_runtime.py", "cloud_search.py", "cloud_storage.py", "document_store.py", "evaluate_extended.py"]},
            "uploaded_versions": sorted((d["id"], d["version"]) for d in inventory.json()["documents"]),
            "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        }
        signature = hashlib.sha256(json.dumps(signature_data, sort_keys=True).encode()).hexdigest()[:16]
        path = BASE_DIRECTORY / "reports" / ("extended_" + signature + ".json")
        path.parent.mkdir(exist_ok=True)
        report = json.loads(path.read_text()) if path.exists() else {"configuration": signature_data, "method": "Expected status, factual substring groups, required source titles and exact quote references. These assertions do not establish full semantic correctness.", "cases": {}}
        print("Report:", path)
        try:
            for case in cases:
                existing = report["cases"].get(case["id"], {})
                if "result" in existing:
                    print(case["id"], "already completed")
                    continue
                started = time.perf_counter()
                response = client.post("/investigate", json={"question": case["question"]})
                entry = {"case": case, "http_status": response.status_code, "seconds": time.perf_counter() - started}
                if response.is_success:
                    entry["result"] = response.json()
                    entry["assessment"] = check_case(case, entry["result"])
                    print(case["id"], entry["assessment"])
                else:
                    entry["error"] = response.text[:1500]
                    print(case["id"], "HTTP", response.status_code)
                report["cases"][case["id"]] = entry
                report["updated_at"] = datetime.now(timezone.utc).isoformat()
                save(path, report)
                if response.status_code == 429:
                    print("Quota reached. Progress saved; resume this command after capacity recovers.")
                    break
                time.sleep(args.pause)
        finally:
            if args.cleanup:
                for document_id in created:
                    deletion = client.delete("/documents/" + document_id)
                    if deletion.status_code not in {204, 404}:
                        print("Cleanup needs attention for", document_id, deletion.status_code)
        rows = list(report["cases"].values())
        report["summary"] = {
            "planned": len(cases),
            "completed": sum("result" in row for row in rows),
            "passed_assertions": sum(row.get("assessment", {}).get("passed_all_assertions", False) for row in rows),
            "unresolved_http_errors": sum("error" in row for row in rows),
            "planned_categories": dict(Counter(case["category"] for case in cases))
        }
        save(path, report)
        print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
