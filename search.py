import math
import re
from collections import Counter


def tokenize(text):
    return set(re.findall(r"\w+", text.lower()))


def search_documents(query, documents):
    query_words = tokenize(query)

    if not query_words or not documents:
        return []

    word_counts = [
        Counter(
            re.findall(
                r"\w+",
                f"{document['title']} {document['text']}".lower()
            )
        )
        for document in documents
    ]

    lengths = [
        sum(counts.values())
        for counts in word_counts
    ]

    average_length = sum(lengths) / len(lengths)

    if average_length == 0:
        return []

    document_frequency = Counter()

    for counts in word_counts:
        document_frequency.update(counts.keys())

    k1 = 1.5
    b = 0.75
    results = []
    document_count = len(documents)

    for document, counts, length in zip(
        documents, word_counts, lengths
    ):
        score = 0.0

        for word in query_words:
            frequency = counts[word]

            if frequency == 0:
                continue

            containing_documents = document_frequency[word]

            rarity = math.log(
                1 + (
                    document_count - containing_documents + 0.5
                ) / (
                    containing_documents + 0.5
                )
            )

            length_adjustment = k1 * (
                1 - b + b * length / average_length
            )

            score += rarity * (
                frequency * (k1 + 1)
            ) / (
                frequency + length_adjustment
            )

        if score > 0:
            results.append({
                "document": document,
                "score": score
            })

    return sorted(
        results,
        key=lambda result: (
            -result["score"],
            result["document"]["id"]
        )
    )