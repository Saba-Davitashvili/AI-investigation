import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


def main():
    parameters = urlencode({
        "dataset": "hotpotqa/hotpot_qa",
        "config": "distractor",
        "split": "train",
        "offset": 0,
        "length": 10
    })

    url = f"https://datasets-server.huggingface.co/rows?{parameters}"

    print("Downloading HotpotQA sample...")

    with urlopen(url, timeout=60) as response:
        payload = json.load(response)

    documents = {}
    questions = []

    for item in payload["rows"]:
        row = item["row"]
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

            documents[document_id] = {
                "id": document_id,
                "title": title,
                "text": text,
                "sentences": sentences,
                "source": "hotpotqa/hotpot_qa",
                "config": "distractor",
                "split": "train"
            }

        questions.append({
            "id": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "type": row["type"],
            "supporting_facts": row["supporting_facts"]
        })

    output_directory = Path(__file__).parent / "data"
    output_directory.mkdir(exist_ok=True)

    files = {
        "sample_documents.json": list(documents.values()),
        "sample_questions.json": questions
    }

    for filename, content in files.items():
        path = output_directory / filename
        path.write_text(
            json.dumps(content, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    print(f"Saved {len(documents)} unique source passages.")
    print(f"Saved {len(questions)} evaluation questions.")


if __name__ == "__main__":
    main()