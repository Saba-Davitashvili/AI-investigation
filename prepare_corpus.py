import hashlib
import json
from itertools import islice


from config import BASE_DIRECTORY


DATASET = "hotpotqa/hotpot_qa"
REVISION = "14f0ace3c3fac7bd86149c616b5b05d8282e5c6a"
TARGET_DOCUMENTS = 50_000
EVALUATION_QUESTIONS = 40


def stream_split(split):
    from datasets import load_dataset
    filenames = (
        ["0000.parquet", "0001.parquet"]
        if split == "train"
        else ["0000.parquet"]
    )

    files = [
        (
            f"hf://datasets/{DATASET}@{REVISION}/"
            f"distractor/{split}/{filename}"
        )
        for filename in filenames
    ]

    return load_dataset(
        "parquet",
        data_files={"records": files},
        split="records",
        streaming=True
    )


def add_passages(row, split, documents):
    context = row["context"]

    for title, sentences in zip(
        context["title"],
        context["sentences"]
    ):
        text = " ".join(sentences).strip()

        if not text:
            continue

        identity = json.dumps(
            [title, text],
            ensure_ascii=False
        )
        document_id = hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()

        if document_id not in documents:
            documents[document_id] = {
                "id": document_id,
                "title": title,
                "text": text,
                "sentences": sentences,
                "source": DATASET,
                "revision": REVISION,
                "config": "distractor",
                "split": split,
                "origins": []
            }

        documents[document_id]["origins"].append({
            "split": split,
            "question_id": row["id"]
        })


def main():
    documents = {}
    evaluation = []

    print("Preparing validation questions and their passages...")

    for row in islice(
        stream_split("validation"),
        EVALUATION_QUESTIONS
    ):
        add_passages(row, "validation", documents)

        evaluation.append({
            "id": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "type": row["type"],
            "level": row["level"],
            "supporting_facts": row["supporting_facts"]
        })

    if len(evaluation) != EVALUATION_QUESTIONS:
        raise ValueError("Not enough evaluation questions.")

    print("Adding training passages...")
    training_rows = 0

    for row in stream_split("train"):
        add_passages(row, "train", documents)
        training_rows += 1

        if training_rows % 500 == 0:
            print(
                f"Read {training_rows} training questions; "
                f"collected {len(documents)} unique passages."
            )

        if len(documents) >= TARGET_DOCUMENTS:
            break

    if len(documents) < TARGET_DOCUMENTS:
        raise ValueError("Could not reach the corpus target.")

    output_directory = BASE_DIRECTORY / "data" / "corpus"
    output_directory.mkdir(parents=True, exist_ok=True)

    corpus_path = output_directory / "documents.jsonl"
    temporary_path = output_directory / "documents.jsonl.tmp"
    fingerprint = hashlib.sha256()

    with temporary_path.open("wb") as file:
        for document in documents.values():
            line = (
                json.dumps(document, ensure_ascii=False) + "\n"
            ).encode("utf-8")

            file.write(line)
            fingerprint.update(line)

    temporary_path.replace(corpus_path)

    (output_directory / "evaluation_questions.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    manifest = {
        "dataset": DATASET,
        "revision": REVISION,
        "selection": (
            "First 40 validation questions and their contexts, "
            "then training contexts in file order until at least "
            "50000 unique title-and-text pairs; finish each row."
        ),
        "training_question_rows_read": training_rows,
        "unique_passages": len(documents),
        "evaluation_questions": len(evaluation),
        "corpus_sha256": fingerprint.hexdigest()
    }

    (output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8"
    )

    print(f"\nUnique passages: {len(documents)}")
    print(f"Evaluation questions: {len(evaluation)}")
    print(f"Corpus fingerprint: {fingerprint.hexdigest()}")
    print(f"Saved to: {output_directory}")


if __name__ == "__main__":
    main()