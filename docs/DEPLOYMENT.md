# Deployment and persistence

## Current state

Deployment files are prepared; no cloud account, VM, certificate or public URL has been created or verified by this closeout. Docker is unavailable in the closeout runtime, so the container build has not been executed. A deployment is complete only after the public endpoint and hosted restart test below succeed.

The existing architecture loads a Python embedding model, corpus text, BM25 postings and local Qdrant data. Small free web instances may not fit it. Do not assume that adding a Dockerfile makes every free host suitable.

## Preferred persistent free-hosting path

Use an Oracle Cloud Always Free Ubuntu VM, if account approval and regional capacity are available. The documentation checked on 29 October 2026 describes an Ampere allowance equivalent to 2 OCPUs/12 GB RAM and 200 GB combined boot/block storage. Provision only resources labeled Always Free eligible in the home region and stay inside the displayed account limits. Do not upgrade to paid resources to follow this guide.

Oracle generally requires phone/card identity verification and notes possible authorization holds. Capacity can be unavailable and idle resources can be reclaimed. These are deployment constraints, not guarantees of instant provisioning.

Sources:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm
- https://www.oracle.com/cloud/free/

Hugging Face's current Space-creation policy is a reason not to assume a new Docker Space is available on a free account. Its CPU hardware table and eligibility to create compute Spaces are separate issues: https://huggingface.co/docs/hub/spaces-overview.

### VM preparation

1. Create/verify your own free account. Keep payment details and private keys out of the repository and chat.
2. Create an Always Free eligible Ubuntu instance with sufficient available memory. Use an SSH public key you control. Keep the private key locally.
3. Allow inbound 80/443 for the web proxy; restrict SSH to your own IP. Do not expose the internal app port 8000 publicly.
4. Install Docker Engine and Compose using the official Ubuntu guide: https://docs.docker.com/engine/install/ubuntu/.
5. Upload/clone the source to a directory such as /home/ubuntu/trace. Create .env on the VM; never bake it into an image.

### Public hostname and TLS

Use a DNS hostname that points at the VM. If no domain is available, a hostname embedding the VM's public IPv4 under sslip.io can provide DNS without purchasing a domain. Verify resolution before proceeding; this external DNS service and certificate issuance can have availability/rate limits. Source: https://sslip.io/.

Set DEMO_HOST to the DNS name without a scheme, and PUBLIC_ORIGIN to its matching https:// URL. Caddy handles public certificates when DNS and inbound ports are correct. Source: https://caddyserver.com/docs/automatic-https.

Example variable names only; replace all placeholders:

```dotenv
APP_ENV=production
GROQ_API_KEY=your_server_side_provider_key
GROQ_MODEL=openai/gpt-oss-120b
DEMO_USERNAME=reviewer
DEMO_PASSWORD=your_unique_random_password_at_least_16_characters
DEMO_HOST=your_public_dns_hostname
PUBLIC_ORIGIN=https://your_public_dns_hostname
BOOTSTRAP_ON_START=false
```

If .env already exists, setup_demo_access.py preserves its provider key while setting demo access:

```bash
python setup_demo_access.py --production --host your_public_dns_hostname
```

The script needs the small Python dependencies installed when run outside the container. You may instead edit .env directly. The production entrypoint refuses to serve without the provider key and a non-placeholder password of at least 16 characters.

### Build, prepare data and start

From the VM source directory, prefix Docker commands with sudo if required by your installation:

```bash
docker compose build app
docker compose run --rm --no-deps app python prepare_corpus.py
docker compose run --rm --no-deps app python verify_corpus.py
docker compose run --rm --no-deps app python build_corpus_index.py
docker compose up -d
docker compose logs -f app
```

First build/download/embedding can take substantial time on a small CPU. The source package omits the corpus and vectors. These commands create them in persistent named volumes rather than silently demonstrating an empty or reduced corpus. Alternatively, deliberately set BOOTSTRAP_ON_START=true for first startup and inspect its progress logs.

To reuse the existing Windows data instead of regenerating it, stop all API/indexing processes first, make a consistent state backup, and migrate data/ and indexes/ into the corresponding container volumes. Do not archive databases while they are open. Portability of the local Qdrant directory across platforms/versions must be verified; regeneration from pinned source is the fallback.

Open https://your_public_dns_hostname. Authenticate using the separate demo credentials. Do not share the Groq key with reviewers.

### Architecture

- Public HTTPS terminates at Caddy, which proxies to the private app container.
- One Python process owns Qdrant local mode. Do not increase Uvicorn workers for this design.
- SQLite originals/metadata are under /app/data; vectors under /app/indexes; downloaded model files under /app/model-cache.
- Compose named volumes persist those three paths independently of the app image/container. Caddy also preserves certificate state.
- A shared Basic-auth gate protects all API/UI routes when configured. It is a single-reviewer demo mechanism, not per-user accounts or tenant isolation.
- Browser cross-site writes are rejected. API tools use Basic credentials explicitly.
- Application secrets are environment variables excluded by .gitignore/.dockerignore.
- The proxy limits request bodies to 11 MB; the parser separately enforces a 10 MiB file limit.

### Required hosted acceptance

Record the actual URL, UTC time, source commit and results:

1. Open the HTTPS URL from a separate network, such as phone mobile data; confirm authentication is required.
2. Authenticate, load /health and verify expected corpus counts.
3. Upload a disposable record; verify it in keyword search and inspect its source.
4. Restart the app container. Confirm the same ID/content/version and search passage persist.
5. Replace the record; confirm old text is absent from keyword and vector payloads.
6. Delete it; confirm its parent ID is absent from all search modes.
7. Run a source-backed investigation and an insufficient/conflict case with real provider capacity.

Do not mark hosted persistence passed merely because volumes appear in compose.yaml. Removing volumes, deleting the VM/storage or running a destructive volume-removal command deletes data.

### Backup

Stop the API before making a consistent backup. Locally:

```powershell
.\.venv\Scripts\python.exe backup_state.py
```

The private backup includes source documents and indexes but excludes .env; keep it private. On the VM, stop app, run a temporary app container executing backup_state.py to /tmp, copy the archive out with docker cp, remove that temporary container and restart app. This maintenance path has not been live-tested here.

## Immediate public preview fallback — not a substitute for persistent cloud hosting

If account provisioning cannot finish by the deadline, Cloudflare Quick Tunnel can expose the running local app without a Cloudflare account/domain. It is temporary: the PC, API and tunnel must stay running, and the hostname changes on a new tunnel. Disclose self-hosted preview architecture; do not call it a completed persistent cloud deployment. Source: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/.

After installing this source candidate into the existing project, enable the demo password:

```powershell
.\.venv\Scripts\python.exe setup_demo_access.py
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

Download the Windows amd64 cloudflared binary from the official release page: https://github.com/cloudflare/cloudflared/releases. Keep the API terminal running. In a second terminal run the downloaded executable (adjust its filename/path):

```powershell
.\cloudflared-windows-amd64.exe tunnel --url http://127.0.0.1:8000
```

Use only the actual HTTPS URL printed by that process. Test it on another network and confirm the password gate before sharing it. If browser writes are rejected due to an origin mismatch, set PUBLIC_ORIGIN to that exact HTTPS origin in .env and restart the API. Keep the laptop awake and the processes running for the review. This route has not been executed on the user's machine by the assistant.

## Cost/resource notes

No paid infrastructure purchase is required by the proposed Always Free design, but free-account verification, eligible capacity and future terms are outside the application's control. Query generation/judging consume provider token quotas; local embedding avoids a per-embedding API charge but consumes CPU/RAM. Running evaluation competes with live demos for the same provider allowance. A quota failure should remain explicit rather than be hidden as an answer.

## Publication checklist

Fill SUBMISSION_CHECKLIST.md with the real GitHub URL, real demo URL and measured restart evidence. Keep the free-tier restrictions and any preview-only compromise visible in the submission.
