# Code-defense map

This is a map for preparation, not a claim that the candidate already understands every module.

| Topic | Start here | Be able to explain |
|---|---|---|
| HTTP request | api.py | Request validation, status codes, startup resources, why one process owns local Qdrant |
| Input formats | document_reader.py | UTF-8 decoding, PDF extraction limitations, page/character offsets and limits |
| Stored lifecycle | document_store.py | Parameterized SQL, content-hash deduplication, stable IDs/version increments and rollback |
| Chunking | chunk_documents.py | 160-token windows, 32-token overlap, boundary heuristic, offset validation and truncation avoidance |
| Keyword algorithm | bm25_index.py | Postings, document frequency, IDF, saturation and length normalization |
| Vector retrieval | semantic_search.py | Embedding dimension, cosine distance, stored payloads, same model for index/query |
| Rank fusion | hybrid_search.py / uploaded_index.py | Why ranks are fused rather than adding incompatible raw scores |
| Investigation | investigator.py | Native tool plan, evidence-ID selection, Python quote restoration, one bounded repair |
| Evaluation | evaluate_corpus.py / evaluate_answers.py | Recall, all-source coverage, MRR, judge bias, failed-case denominators and resumability |
| Category tests | evaluate_extended.py | Expected-status/fact/source assertions and why substring checks are imperfect |
| Demo deployment | serve.py / compose.yaml / demo_security.py | Secrets, persistent volumes, TLS ingress and the difference between preview and hosted acceptance |

Practice without AI:

1. Locate where a missing query becomes HTTP 422; add a different length limit and verify it.
2. Change the default result limit; identify all callers where an explicit limit overrides it.
3. Trace one source from SQLite text through chunk offsets, vector payload, evidence ID and UI quote.
4. Explain why a fabricated evidence ID is rejected even when the finding sounds plausible.
5. Explain why 100% quote validity and 57.5% answer correctness can both be true.
6. Make a disposable replacement and explain how stale upload vectors disappear.
7. Describe the 14 answerable questions where the engine abstained, then propose a measurable follow-up-search experiment.

Do not memorize generated code as a substitute for running and modifying a small part independently.
