# Submission status — fill with actual evidence

The source snapshot is published at https://github.com/Saba-Davitashvili/AI-investigation. Public deployment and hosted acceptance remain pending. The source ZIP did not include the original Windows .git directory, so this new repository starts with the published snapshot; it does not recreate earlier local commits.

| Deliverable / acceptance | Status | Final evidence to add |
|---|---|---|
| Source repository and history | Snapshot published | https://github.com/Saba-Davitashvili/AI-investigation; original Windows history not included in source ZIP |
| Public hosted demo | Pending | Actual public HTTPS URL and reviewer access instructions |
| Hosted data survives restart | Not run | Document ID/version/search result before and after a real host restart |
| README and architecture | Written | README.md |
| Evaluation report and analysis | Written, historical run preserved | EVALUATION_REPORT.md and reports/answers_34a5f61598d5ab6c.json |
| AI usage disclosure | Written; candidate should verify personal contribution wording | AI_USAGE_REPORT.md |
| 50,000+ records | Reported local run: 50,001 passages / 60,822 chunks | Verify deployed counts; retain corpus/index manifests |
| Three formats / document lifecycle | Implemented and offline-tested | Real demo smoke check with disposable TXT/MD/PDF |
| Own retrieval/ranking component | Implemented | BM25 postings and reciprocal rank fusion |
| Two search configurations | Reported local comparison | Retain/rerun raw retrieval report if needed |
| Two chunking strategies | Reported 10-question comparison | Do not claim large-corpus comparison was run |
| Native tool calling and multi-source answers | Implemented; historical local examples passed | Run a live demo question |
| Missing/conflicting information | Manual examples passed | Run the 12-case automated extension and retain its report |
| 40-question answer evaluation | Completed historical run | 23/40 correct; no unresolved saved cases after resumption |
| Additional category evaluation | 12 cases provided, live execution pending | Run evaluate_extended.py; report failures honestly |
| Offline candidate tests | See reports/closeout/ | Do not confuse fake-embedding integration with a full-corpus benchmark |
| Frontend acceptance | Mock browser checks passed; local real-backend check pending | Open sources; upload/replace/delete; inspect a conflict |
| Secrets protected | .gitignore/.dockerignore and demo gate prepared | Verify no .env/keys/private backups are staged; configure HTTPS/access before external sharing |

## Install the candidate safely

Stop the API. Extract this ZIP into a separate folder. Copy the candidate files into the existing project folder, preserving .env, data/, indexes/ and .git. Do not delete those runtime/history directories. This package contains none of them. Then:

```powershell
cd C:\Users\Saba\ai-investigation-engine
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe -m uvicorn api:app
```

In a second terminal, if provider capacity is available:

```powershell
.\.venv\Scripts\python.exe evaluate_extended.py
```

Keep the original 40-question report as historical evidence. Source changes produce a different fingerprint for any new answer-evaluation run.

## Publish while preserving history

Inside the original local repository, inspect the existing remote before adding one:

```powershell
git remote -v
git status --short
git check-ignore .env
git ls-files .env "data/*" "indexes/*" "backups/*"
```

The last command should produce no private/runtime paths. Resolve any tracked secrets before publishing. Review staged names. Do not upload a full-folder archive containing .env or original private uploads.

```powershell
git add .
git diff --cached --name-only
git commit -m "Prepare investigation engine submission and deployment candidate"
```

Create an empty GitHub repository under your own account if needed. If origin is absent, add its actual URL; if it exists, verify it is the intended repository rather than overwriting it blindly. Push your actual current branch with its history. No repository URL, branch name or historic commits are fabricated by this package.

## Final handoff text

- GitHub: https://github.com/Saba-Davitashvili/AI-investigation
- Live demo: **not yet deployed — replace with real URL**
- Reviewer access: **share the demo credentials privately; never the provider key**
- Recorded answer result: 23/40 judge-correct (57.5%); 26/30 findings supported; 51/51 quotes valid.
- Extended suite: **replace with actual run counts**.
- Hosting restrictions / restart evidence: **replace with verified facts**.

Do not submit the placeholders as completed evidence.
