import math
import re
from collections import Counter, defaultdict
from heapq import nsmallest

from search import tokenize


class BM25Index:
    def __init__(self, documents, k1=1.5, b=0.75):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.lengths = []
        self.postings = defaultdict(list)

        for position, document in enumerate(documents):
            text = f"{document['title']} {document['text']}"

            counts = Counter(
                re.findall(r"\w+", text.lower())
            )

            self.lengths.append(sum(counts.values()))

            for word, frequency in counts.items():
                self.postings[word].append(
                    (position, frequency)
                )

        self.average_length = (
            sum(self.lengths) / len(self.lengths)
            if self.lengths
            else 0
        )

    def search(self, query, limit=20):
        if self.average_length == 0 or limit <= 0:
            return []

        scores = defaultdict(float)
        document_count = len(self.documents)

        for word in tokenize(query):
            postings = self.postings.get(word, [])

            if not postings:
                continue

            rarity = math.log(
                1 + (
                    document_count - len(postings) + 0.5
                ) / (
                    len(postings) + 0.5
                )
            )

            for position, frequency in postings:
                adjustment = self.k1 * (
                    1 - self.b
                    + self.b * self.lengths[position]
                    / self.average_length
                )

                scores[position] += (
                    rarity * frequency * (self.k1 + 1)
                    / (frequency + adjustment)
                )

        best_positions = nsmallest(
            limit,
            scores,
            key=lambda position: (
                -scores[position],
                self.documents[position]["id"]
            )
        )

        return [
            {
                "document": self.documents[position],
                "score": scores[position]
            }
            for position in best_positions
        ]