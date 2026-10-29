# AI usage report

## Disclosure

This project was built with substantial assistance from ChatGPT/Codex. Most Python modules and the frontend were drafted by the assistant. The candidate began with manual QA/Postman experience and no prior Python coding experience. The report should not imply independent authorship or proficiency that has not been demonstrated.

## Where assistance was used

| Area | Assistance |
|---|---|
| Project breakdown | Interpreted requirements, proposed milestones and selected a minimal architecture |
| Python implementation | Drafted ingestion, deduplication, chunking, BM25/postings, rank fusion, Qdrant integration, API and SQLite code |
| RAG workflow | Drafted tool schema, planning/generation prompts, structured models, source selection and validators |
| Debugging | Interpreted errors, suggested edits, explained setup, indentation, missing classes/imports and multipart requests |
| Evaluation | Drafted retrieval metrics, resumable answer runner, same-model judge, added category fixtures and analysis |
| UI | Drafted the original frontend and a later redesigned interface guided by an installed UI/UX audit skill |
| Closeout | Inspected the supplied archive, removed shadowed duplicate definitions, separated config imports, added demo access protection, tests, deployment files and documentation |

Exact authoring-assistant model identifiers were not recorded consistently, so no precise model-version claim is made here.

## Candidate's observed contribution

The candidate installed/configured the Windows environment, created and edited local files from instructions, ran ingestion and indexing, configured a provider key locally, executed tests and evaluation, used Postman/Swagger, reported error traces, corrected selected fixture-file contents, checked document lifecycle behavior and provided the actual source/report archive.

The conversation does not establish substantial independently designed algorithm/code changes. Before submission, the candidate should add any genuinely independent work they can substantiate rather than inventing examples to satisfy this section.

## AI inside the product

- Generation/planning: Groq-hosted openai/gpt-oss-120b in the recorded evaluation.
- Embeddings: sentence-transformers/all-MiniLM-L6-v2 locally.
- Automated judge: the configured Groq model; the recorded setup uses the same default model family as the generator.
- The product makes a native search tool call. It is not a multi-agent system.

User questions and retrieved excerpts are sent to the configured model provider. API keys stay in server configuration. Public-demo credentials are distinct from the provider key.

## Validation and limitations

The completed historical 40-question run and its original outputs are retained. Exact quote copying was moved from model text generation into Python after repeated validation failures. That protects quote fidelity, not factual entailment. Same-model judging can be biased, and an inconsistent judgment was found during closeout.

Offline tests and mocked browser checks do not replace live deployment/evaluation. The added category suite has not been claimed passed without a live run. Documentation distinguishes actual measurements, candidate tests, hypotheses and pending work.

## Interview responsibility

The candidate remains responsible for understanding and defending the code. Completing the artifact with AI does not establish readiness to modify it unaided. Review docs/CODE_WALKTHROUGH.md and practice locating and changing code without AI before the interview. This report must remain truthful even if that preparation is incomplete.

## Cloud deployment continuation

AI also implemented the optional ONNX/Qdrant/PostgreSQL serving path, Render configuration, cloud seed/resume script, cloud regression tests, and two-phase hosted acceptance script. Local test results do not establish a deployed service. These changes require independent understanding and live validation before submission.
