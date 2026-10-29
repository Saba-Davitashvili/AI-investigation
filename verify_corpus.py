import hashlib
import json

from config import BASE_DIRECTORY


def main():
    directory = BASE_DIRECTORY / "data" / "corpus"

    manifest = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )

    fingerprint = hashlib.sha256()
    document_ids = set()
    titles = set()
    count = 0

    with (directory / "documents.jsonl").open("rb") as file:
        for line in file:
            fingerprint.update(line)
            document = json.loads(line)

            if document["id"] in document_ids:
                raise ValueError("Duplicate document ID found.")

            if not document["text"].strip():
                raise ValueError("Empty passage found.")

            document_ids.add(document["id"])
            titles.add(document["title"])
            count += 1

    if fingerprint.hexdigest() != manifest["corpus_sha256"]:
        raise ValueError("Corpus fingerprint does not match.")

    if count != manifest["unique_passages"] or count < 50_000:
        raise ValueError("Corpus document count is incorrect.")

    questions = json.loads(
        (directory / "evaluation_questions.json").read_text(
            encoding="utf-8"
        )
    )

    if len(questions) != manifest["evaluation_questions"]:
        raise ValueError("Evaluation question count is incorrect.")

    for question in questions:
        required_titles = set(
            question["supporting_facts"]["title"]
        )

        if not required_titles:
            raise ValueError("Question has no supporting sources.")

        missing = required_titles - titles

        if missing:
            raise ValueError(f"Missing source titles: {missing}")

    print(f"Verified unique passages: {count}")
    print(f"Verified evaluation questions: {len(questions)}")
    print("Corpus fingerprint matches.")
    print("All evaluation source titles are present.")


if __name__ == "__main__":
    main()