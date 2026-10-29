"""BM25 sparse vectors computed by this project, scored by Qdrant dot product.

No corpus or postings are loaded into the web process. A small PostgreSQL
vocabulary supplies exact term IDs and document frequencies per collection.
"""
import math
import re
from collections import Counter

from qdrant_client import models

from search import tokenize


def term_counts(document):
    return Counter(word for word in re.findall(r"\w+", f"{document['title']} {document['text']}".lower()) if len(word) <= 256)


def corpus_statistics(documents):
    frequencies = Counter()
    total_length = 0
    count = 0
    for document in documents:
        words = term_counts(document)
        frequencies.update(words.keys())
        total_length += sum(words.values())
        count += 1
    vocabulary = {word: (i, frequencies[word]) for i, word in enumerate(sorted(frequencies))}
    return vocabulary, count, total_length / count if count else 0


def document_sparse(document, vocabulary, average_length, k1=1.5, b=0.75):
    words = term_counts(document)
    length = sum(words.values())
    adjustment = k1 * (1 - b + b * length / average_length) if average_length else k1
    weighted = sorted((vocabulary[word][0], frequency * (k1 + 1) / (frequency + adjustment))
                      for word, frequency in words.items())
    return models.SparseVector(indices=[i for i, _ in weighted], values=[v for _, v in weighted])


def query_sparse(query, vocabulary, count):
    weighted = sorted((vocabulary[word][0], math.log(1 + (count - vocabulary[word][1] + .5)
                                                    / (vocabulary[word][1] + .5)))
                      for word in tokenize(query) if word in vocabulary)
    return models.SparseVector(indices=[i for i, _ in weighted], values=[v for _, v in weighted])
