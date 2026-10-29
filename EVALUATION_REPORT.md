# Evaluation report

## Evidence and scope

Primary artifact: reports/answers_34a5f61598d5ab6c.json, supplied from the user's completed local run. Its original configuration, per-question outputs, judge explanations and fingerprints are preserved. This report does not recast historical results as a new evaluation of the closeout candidate.

The local corpus ingestion/indexing logs reported 50,001 unique source passages and 60,822 fixed-token chunks. Those large artifacts were not in the uploaded source ZIP and were not regenerated in this closeout environment.

## Method

Forty HotpotQA validation questions were selected by deterministic file order. Supporting context passages are part of the corpus, as required for retrieval, while question/answer records remain outside the index. These examples support multi-hop/comparison evaluation but are not representative of every possible user question. The same development examples were reused while diagnosing implementation failures; this is not an untouched final holdout.

Retrieval metrics match retrieved passage titles to gold supporting titles. Recall@K measures the fraction of required titles in the first K results. All-sources@5 measures complete title-set coverage. MRR@20 measures the reciprocal rank of the first relevant title. These measures do not establish that the chunk contains the exact supporting sentence; duplicate chunks from one source can occupy multiple positions.

Answer correctness is a binary LLM judgment against the reference answer. Finding support is judged against verified quoted excerpts, without treating the gold answer as evidence. Exact quote validity checks source existence and exact substring presence. This is a provenance/quotation metric, not semantic Citation Accuracy.

Generator and judge use the same default model, openai/gpt-oss-120b through Groq. This creates correlated-bias risk. Manual adjudication is needed for ambiguous references and inconsistent judgments.

## Recorded answer results

| Measure | Result |
|---|---:|
| Planned / graded questions | 40 / 40 |
| Unresolved cases at final save | 0 |
| Judge-correct answers | 23 / 40 = 57.5% |
| Supported findings | 26 / 30 = 86.7% |
| Valid exact quote references | 51 / 51 = 100% |
| Answered / insufficient / conflicting statuses | 25 / 14 / 1 |
| Successful responses that used output repair | 1 |
| Recorded generator tokens | 82,894 |
| Recorded judge tokens | 31,626 |

Recorded token totals describe successful saved responses and judge results. They do not account for every discarded attempt, provider rejection or earlier experiment. The run paused after hitting a daily token allowance, then resumed. Zero unresolved failures is not a first-attempt reliability or uptime claim.

## Retrieval comparison reported during local development

The following values were supplied in local terminal outputs. Their raw retrieval report files were not included in the uploaded source ZIP. Rerun evaluate_corpus.py to generate those artifacts for the current configuration.

| Configuration | Recall@2 | Recall@5 | All sources@5 | MRR@20 | Mean seconds | p95 seconds |
|---|---:|---:|---:|---:|---:|---:|
| Own BM25 keyword | .550 | .762 | .525 | .871 | .059 | .089 |
| Semantic | .500 | .688 | .425 | .870 | .078 | .085 |
| BM25 + semantic hybrid | .613 | .762 | .550 | .899 | .137 | .164 |

Hybrid improved complete source coverage by one question over keyword search and five over semantic search in this 40-question experiment. These differences are small-sample observations, not statistically established superiority. Latencies are sequential local measurements excluding startup, not cloud or concurrent-load measurements.

For the earlier 100-passage / 10-question comparison, whole-passage, fixed-token and sentence-boundary semantic search tied at Recall@5 .750 and all-sources@5 .600. Whole-passage hybrid measured .700/.500; both chunked hybrid variants also measured .700/.500. Fixed-token was chosen as a straightforward starting point, not because it proved universally superior. Chunking comparison at 50,000+ records remains unmeasured.

## What failed and why

Seventeen of forty answers were not judged correct:

- **Fourteen abstentions on answerable questions.** Examples include the office held by the actor in Kiss and Tell, the organization behind 2014 S/S, and Ralph Hefferline's university city. The pipeline correctly avoided guessing, but failed to assemble enough evidence for the known answer. One planned search round and only three retained passages per query are likely bottlenecks; these are hypotheses requiring retrieval traces, not proven causes for every case.
- **One disputed conflict response.** The Kerensky/civil-war example returned conflicting dates rather than the expected October 1922 answer. Inspect source context, whether different endpoints are being compared, and the dataset's intended interpretation before declaring either the sources or reference wrong.
- **Two answered cases marked incorrect.** The real-estate comparison disagreed with the gold answer. The French pilot example has a judge inconsistency: answer_correct is false, but the explanation says the returned name is the correct fuller identity and the reference is incomplete. Retain the original 23/40 score until a documented human adjudication is performed.

See reports/failure_analysis.csv for all seventeen question IDs, questions, references, statuses and judge explanations.

## Engineering correction during development

Earlier local runs had repeated 502 errors when the LLM rewrote quotes. A bounded textual repair did not adequately solve it. The revised design assigns IDs to exact source excerpts and asks the model to select IDs. Python then restores original quote text. Search planning and answer generation use separate prompts so the final stage is not instructed to invoke a missing tool.

The user-reported original baseline was 17/40 correct with 16 unresolved failures. A subsequent textual-repair run was 12/40 correct with 24 unresolved failures. The final uploaded run is 23/40 after completion/resumption. These are historical development comparisons with retries and implementation changes, not a controlled single-variable model experiment. Exact quote validity improved by construction, while semantic support still measured below 100%.

## Added category suite: provided, not executed live

qa/data/extended_cases.json contains 12 cases: 3 simple, 3 multi-document, 3 unanswered and 3 contradictory. Nine synthetic documents cover project metadata, incident/change linking, and unresolved timeout, budget and date conflicts. evaluate_extended.py seeds the fixtures, checkpoints results, stops on quota errors and produces category counts.

Its assertions check status, expected factual marker groups, required cited filenames and exact quote references. Marker matching can miss valid paraphrases or accept a fact mentioned under negation; therefore it is not reported as semantic correctness. The suite needs a live run and manual spot-check. Do not claim that all 52 designed questions have been executed.

## Closeout candidate verification

The initial candidate passed 32 offline unit/integration tests. The cloud continuation adds 13 tests, for 45 passing tests in the latest recorded run. These include source-ID materialization, unknown-tool rejection, original quote validation, SQLite deduplication/replacement/deletion, generated two-page PDF extraction, API status handling, stale upload keyword/vector removal, demo authentication and cross-origin write rejection. API integration uses real local SQLite and in-memory Qdrant with a fake embedding adapter and tiny corpus; it does not benchmark production embeddings or the full dataset. Test output is under reports/closeout/.

Frontend checks previously passed 32 browser scenarios with synthetic intercepted API responses. See qa/ux/frontend-audit.md for coverage and unrun screen-reader/cross-browser checks.

The full Linux/ARM Docker build, live cloud deployment, real-host restart persistence, extended live cases and candidate full-corpus/LLM rerun remain unverified.

## Prioritized improvements

1. Finish the extended-category live run and manually review a sample of supported/unsupported findings plus the inconsistent judge case.
2. Trace failed retrievals; add follow-up searches based on newly discovered entity names, with explicit search/token budgets.
3. Add source diversification and evidence-sentence coverage measurements; test candidate depth as a controlled configuration.
4. Independently judge or manually label claim/citation support. Report semantic citation accuracy separately from exact quote validity.
5. Move large collections to Qdrant server mode and replace whole-upload-library rebuilds with incremental versioned updates.
6. Pin model revisions, compare reranking alternatives, then measure concurrent load and hosted resource use.

These improvements are proposed work, not implemented results.

## Cloud continuation checks

The additional tests verify sparse BM25 dot-product scores against the existing BM25 implementation using real local Qdrant, vocabulary determinism, stale upload removal, local index reopen, explicit dependency failures, parameter binding, TLS configuration checks and the shared lock boundary. PostgreSQL metadata is simulated in these tests; live Neon SQL and hosted persistence remain unverified. A separate process imported the API and ran the actual pinned ONNX model over 80 length-256 samples: peak RSS 293.6 MiB, with no Torch/Transformers imports. This is a synthetic local memory smoke test, not a hosted memory or quality benchmark. See reports/closeout/cloud-memory-smoke.json.
