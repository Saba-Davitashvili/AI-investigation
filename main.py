import json
from pathlib import Path

from search import search_documents, tokenize


def main():
    document_path = Path(__file__).parent / "documents.json"

    with document_path.open(encoding="utf-8") as file:
        documents = json.load(file)

    print(f"Loaded {len(documents)} documents.")

    query = input("Enter a search query: ").strip()

    if not tokenize(query):
        print("Please enter at least one word or number.")
        return

    results = search_documents(query, documents)

    for result in results:
        document = result["document"]

        print(f"\nSource: {document['id']} — {document['title']}")
        print(f"Score: {result['score']}")
        print(document["text"])

    print(f"\nTotal matches: {len(results)}")


if __name__ == "__main__":
    main()