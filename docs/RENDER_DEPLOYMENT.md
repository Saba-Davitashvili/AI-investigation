# Render free deployment candidate

## Status — not deployed

This is an additional cloud path. The existing local/Oracle path is preserved.
The cloud modules have local regression coverage, but no Render/Neon/Qdrant
Cloud account has been provisioned and no public URL or hosted persistence has
been verified. Do not submit this document as proof of an actual deployment.

## Architecture

Browser → Render HTTPS → one FastAPI process → Groq for planning/synthesis.

- PostgreSQL (Neon): original uploaded bytes, parsed text, metadata, stable IDs,
  versions, corpus vocabulary, document frequencies and index manifests.
- Qdrant Cloud: corpus/upload chunk payloads, 384-dimensional dense vectors,
  and sparse keyword vectors. Payloads and vector indexes use disk storage.
- Render: code and the public pinned MiniLM ONNX export. No persistent state is
  stored on Render's ephemeral disk. PyTorch, Transformers, the full corpus and
  full BM25 postings are not loaded by the cloud web process.
- Own BM25 term-frequency normalization is computed during indexing; own IDF
  weights are computed per query from exact vocabulary entries in PostgreSQL.
  Qdrant computes their sparse dot product. Own RRF combines rankings.
  Keyword tokens longer than 256 characters are ignored to bound vocabulary
  index entries; normal tokens retain the original BM25 formula.
- One shared PostgreSQL advisory transaction lock serializes upload rebuilds
  and retrieval across process/deploy overlap. This is a small shared demo,
  not a scalable tenant-isolated product.

The ONNX backend is pinned to model revision
1110a243fdf4706b3f48f1d95db1a4f5529b4d41, FP32 onnx/model.onnx,
attention-mask mean pooling and L2 normalization. Cloud seeding must use that
same backend; the previous local evaluation does not benchmark this change.

## Accounts and free limits

Create only free resources; decline paid upgrades. The following published
limits were checked on 29 October 2026 and can change:

- Render Free: 512 MB RAM, ephemeral disk, sleeps when idle; 750 workspace free
  instance hours/month. https://render.com/docs/free and https://render.com/pricing
- Qdrant Free: one node, 1 GB RAM, 4 GB disk; no card required. Suspends after
  one week of inactivity and can be deleted after four weeks. Keep backups.
  https://qdrant.tech/documentation/cloud/create-cluster/
- Neon Free: 0.5 GB storage/project, 100 CU-hours/project/month, 5 GB egress.
  Verify quotas in the account before seeding. This design stores vocabulary
  and uploads there, not all corpus vectors or duplicated corpus text.
  https://neon.com/pricing
- Groq calls consume the configured account's free token/request quotas.

A real embedding-only smoke test here measured about 246 MiB peak RSS. This is
not the peak memory of the hosted API. A second local smoke test imported
the API stack and encoded 80 long samples at length 256, reaching 293.6 MiB;
it did not exercise hosted requests, PostgreSQL, Qdrant Cloud or the LLM. Measure Render peak memory under upload,
search and investigation load before accepting the 512 MB deployment. Do not
silently pay for more RAM. If it exceeds the free limit, optimize the serving
runtime or use the prepared Always Free VM path.

The shared cloud demo limits uploads to 20 records, 300,000 total parsed JSON
characters, and 20 MiB total original bytes. Writes above those limits roll
back with HTTP 413. One file is still limited to 10 MiB. These limits protect
shared free storage and memory; the 50,000-document corpus is separate.

## Setup

1. Create a Neon Free project/database. Obtain its TLS connection string
   (`sslmode=require` or stronger). Keep it in the local `.env` and later in
   Render's server environment; never in GitHub or browser JavaScript.
2. Create a Qdrant Free cluster and a cluster API key. Record its HTTPS URL.
3. On the existing indexing PC, retain the local data/indexes. Install the
   cloud dependencies in a separate environment if preferred:

   ```powershell
   py -m venv .venv-cloud
   .\.venv-cloud\Scripts\python.exe -m pip install -r requirements-cloud.txt
   ```

4. Add DATABASE_URL, QDRANT_URL, QDRANT_API_KEY and
   QDRANT_CORPUS_COLLECTION=trace_corpus_cloud_v1 to `.env`. Keep
   STORAGE_BACKEND=local on the original PC unless deliberately switching its
   API to the cloud. Seed remotely from the existing verified chunk file:

   ```powershell
   .\.venv-cloud\Scripts\python.exe seed_cloud.py
   ```

   This re-embeds the corpus with the pinned cloud backend. It can take time;
   rerunning resumes missing points for identical input/settings. It refuses
   fewer than 50,000 sources, mismatched existing data, and does not delete an
   existing corpus. Use a NEW named collection to change inputs, within quotas.
   Do not run two seed processes against one collection.
5. Publish source as individual files in a separate GitHub repository, then
   create a Render Blueprint from `render.yaml`. Select only Free. The
   blueprint uses Dockerfile.render and requires the four secret variables.
   Its generated DEMO_PASSWORD is separate from GROQ_API_KEY. Retrieve the demo
   password privately from Render, and give only demo credentials to reviewers.
6. After startup, use the actual Render HTTPS URL. Set PUBLIC_ORIGIN to that
   exact origin if needed for browser write checks. Never invent a URL in the
   submission. `/readyz` is a public minimal health check; all data routes
   remain behind demo authentication.

Local uploads are not silently migrated. Re-upload intended demo files through
the new app; original PC files remain untouched. PostgreSQL is authoritative
for cloud uploads; Qdrant's upload collection is rebuilt on startup or after
CRUD. If indexing fails after storage commits, the API reports that state and
returns 503; restart repairs from persisted originals. During a failed rebuild,
retrieval fails explicitly instead of serving stale payloads.

## Hosted acceptance — required before calling it complete

Configure EVALUATION_API_URL to the real HTTPS URL, DEMO_USERNAME, and
DEMO_PASSWORD in the operator's local environment, then run:

```powershell
.\.venv-cloud\Scripts\python.exe hosted_acceptance.py before
```

Record the Render source commit and restart event, actually restart the
service, wait for readiness, then run:

```powershell
.\.venv-cloud\Scripts\python.exe hosted_acceptance.py after
.\.venv-cloud\Scripts\python.exe evaluate_extended.py
```

The two-phase check proves the same fixture ID/text/version is still available,
then verifies replacement/deletion in all three retrieval modes. It relies on
the operator actually performing the intervening hosted restart; attach the
Render restart evidence. Run source-backed, multi-document, insufficient and
conflict investigations with the real model, and inspect browser errors.
Also run the 40-question retrieval/answer evaluation against the hosted cloud
configuration; preserve the previous local report for comparison.

Cold starts, measured memory, latency, quotas and any failures belong in the
final deployment/evaluation report. None of these live checks has passed yet.
