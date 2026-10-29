# Start here

The code, redesigned frontend, reports and deployment candidates are published at https://github.com/Saba-Davitashvili/AI-investigation. GitHub Actions passed the 45-test offline suite on Python 3.13. Actual hosting and hosted acceptance are still pending.

## 1. Install into the existing project

Stop the API. Back up the current source. Copy this package into C:\Users\Saba\ai-investigation-engine, replacing source files while keeping the existing .env, data, indexes and .git. The ZIP contains none of those runtime/history directories.

Run in the project terminal:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe setup_demo_access.py
.\.venv\Scripts\python.exe -m uvicorn api:app
```

The access setup preserves your provider key and prints a newly generated demo password locally. Keep it private. Open http://127.0.0.1:8000 and authenticate with the demo username/password.

## 2. Finish the added category checks

Keep the API running. In a second project terminal:

```powershell
.\.venv\Scripts\python.exe evaluate_extended.py
```

This seeds nine synthetic documents and executes twelve simple/multi-source/unanswered/conflicting cases. It spends provider tokens. Save the result and inspect failures. No passing live result for this suite has been invented.

## 3. Publish a real demo

Read docs/DEPLOYMENT.md. It provides the persistent free-VM path plus an explicitly temporary, self-hosted public-preview fallback. Neither is already deployed by this ZIP. Do not label the temporary preview as completed persistent cloud hosting.

## 4. Publish source and submit

Keep your original Git history. Follow SUBMISSION_CHECKLIST.md to publish the intended repository without .env, data, indexes or backups. Include README.md, EVALUATION_REPORT.md and AI_USAGE_REPORT.md. Fill the real repository URL, real demo URL and measured restart evidence. Share only the demo login with reviewers, never the provider key.

## Evidence already included

- Completed historical answer run: 23/40 correct (57.5%).
- Finding support: 26/30 (86.7%, LLM judged).
- Exact quote validity: 51/51; this is not semantic citation accuracy.
- Candidate: 45 offline tests passed; integration tests use fake embeddings, simulated PostgreSQL metadata and mocked provider responses. A separate real ONNX smoke test is recorded.
- Frontend: 32 mocked-API browser checks passed; live acceptance remains.

Current candidate source changes do not retroactively re-evaluate the original baseline report.

## Render alternative

See docs/RENDER_DEPLOYMENT.md for the additional small cloud runtime. It requires provisioned free Render, Neon and Qdrant accounts, corpus seeding and live acceptance; these have not been completed.

For setup without installing anything on your PC, use the “Entirely cloud-hosted setup” section in docs/RENDER_DEPLOYMENT.md and the manual Prepare cloud corpus Actions workflow. Account provisioning and private secret configuration remain required.
