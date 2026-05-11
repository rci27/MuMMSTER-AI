# Deployment

This document describes how the five containers are deployed, updated, and validated. It is *not* a turnkey setup guide — the deployment automation lives in a separate private repo because it contains host-specific paths, SSH keys, and the broker permission model. But this document describes the pattern in enough detail that you could reproduce it on your own infrastructure.

---

## The Broker Pattern

Deployment is centered on a single concept: the **broker**. It's a shell script on the Proxmox host (`/usr/local/sbin/ai-manager-broker`) that exposes a fixed list of named actions over SSH. A trusted automation user (`artemis-ai`) can invoke any allowed action; nothing else is permitted.

### Why a broker

A naive setup would give the automation user (or Claude Code) full root SSH access to the host. That's dangerous and hard to audit. The broker constrains automation to a known, reviewable set of actions:

- `deploy-mummster` — create LXC 124 from scratch
- `deploy-mummster-query` — create LXC 125
- `deploy-mummster-curation` — create LXC 126
- `deploy-sbdb-frontend` — create LXC 127
- `deploy-sbdb-query` — create LXC 128
- `update-mummster-source` — push latest source to LXC 124 and restart
- `update-mummster-query-source` — same for LXC 125
- `update-mummster-curation-source` — same for LXC 126
- `update-sbdb-frontend-source` — same for LXC 127 (triggers npm build)
- `update-sbdb-query-source` — same for LXC 128
- `validate-mummster` — health checks for LXC 124
- `validate-mummster-query` — health checks for LXC 125
- `validate-sbdb-frontend` — health checks for LXC 127
- `validate-sbdb-query` — health checks for LXC 128
- `run-mummster-pipeline` — execute the full pipeline on LXC 124
- `mummster-curation-log` / `sbdb-query-log` — tail service journals
- `export-state` — dump current container/service status for review

Any other command is denied with a log entry. The full source of the broker script lives in the private deployment repo.

### The deploy → update → validate cycle

For each container the pattern is identical:

1. **`deploy-X`** — one-time. Creates the LXC from a Debian 12 template, sets the bind mounts (read-only data directory mount), installs system dependencies, creates the Python venv (or runs `npm install`), pushes the initial source files, writes the systemd service unit, places the API key, starts the service.
2. **`update-X-source`** — repeatable. Pulls the latest source from this repo, stops the service, pushes source files into the container via `pct push`, runs dependency installs if `requirements.txt` or `package.json` changed, restarts the service.
3. **`validate-X`** — repeatable. Runs a 6-to-8 point health check: container is running, service is active, HTTP health endpoint returns 200, bind-mounted data is visible, API key is readable, source files are present, dependencies are installed.

This is the same pattern for all five containers. The only meaningful difference is what gets installed (Python vs. Node) and what gets restarted.

---

## The Source-of-Truth Flow

A change goes from your laptop to the live container like this:

```
Your machine (Windows or macOS)
   │
   │  edit a file under apps/, commit, git push
   ▼
GitHub (rci27/MuMMSTER-AI)
   │
   │  broker runs update-X-source
   │  → git fetch + git reset --hard origin/main
   ▼
ARTEMIS host
   │  /mnt/artemis-data/git/MuMMSTER-AI/   ← always matches GitHub main
   │
   │  pct push (file-by-file copy into the container)
   ▼
LXC X
   │  /opt/<app-name>/    ← receives copied source
   │
   │  systemctl restart <service>
   ▼
Service live with new code
```

Three hops: your machine → GitHub → ARTEMIS → LXC. Direct edits inside an LXC are not durable — the next `update-X-source` run will overwrite them, because the broker does a `git reset --hard origin/main` before pushing files in.

---

## Per-Container Deploy Notes

### LXC 124 — mummster-pipeline

- **System dependencies:** `python3`, `python3-venv`, `pdftotext` (poppler-utils), `tesseract-ocr`, `duckdb` Python bindings.
- **Bind mounts:** `/mnt/artemis-data/mummster` → `/opt/mummster` (read-write — this is the only container that writes to the data directory).
- **Service:** `mummster-pipeline.service`. Not a long-running service — invoked on-demand by `run-mummster-pipeline`.
- **Datasette:** runs as a separate `mummster-datasette.service`, long-running, port 8001.

### LXC 125 — mummster-query

- **System dependencies:** `python3`, `python3-venv`, WeasyPrint system libs (`libpango`, `libcairo`, etc.).
- **Bind mounts:** `/mnt/artemis-data/mummster/data` → `/opt/mummster/data` (read-only).
- **Service:** `mummster-query.service`, long-running, port 8002.
- **Secrets:** `/etc/artemis-secrets/anthropic.key` (mode 640, owner `root:mummster-data`). The service user `mummster-query` is in the `mummster-data` group.

### LXC 126 — mummster-curation

- **System dependencies:** `python3`, `python3-venv`. No WeasyPrint here.
- **Bind mounts:** `/mnt/artemis-data/mummster/data` → `/opt/mummster-curation/data` (read-only for source data, read-write for `curation.db`).
- **Service:** `mummster-curation.service`, long-running, port 8003.

### LXC 127 — sbdb-frontend

- **System dependencies:** `nodejs` 20, `npm`, `nginx`.
- **Bind mounts:** none — this container has no runtime DB access. All data is baked into the build at `npm run build` time.
- **Service:** nginx serves `/opt/sbdb-frontend/public/` on port 3000.
- **Build process:** during `update-sbdb-frontend-source`, after the source is copied in, the broker runs `npm install` (cached layer when unchanged) and then `npm run build`. The `gatsby-node.js` file calls Datasette's JSON API at `http://192.168.1.72:8001` to fetch all tables at build time and creates static pages for each band and captain.

### LXC 128 — sbdb-query

- **Identical to LXC 125** except:
  - CORS `allow_origins` includes the public domain
  - Service unit is `sbdb-query.service`, port 8004
- Same bind mount, same secrets pattern, same dependency list.

---

## Public Exposure

LXC 127 and 128 are the only public-facing services. Exposure is via a Cloudflare Tunnel:

```
Public internet
       │
       ▼
Cloudflare edge → tunnel → LXC running cloudflared
       │
       ├── sbdb-ai.theronlab.com           → LXC 127 nginx :3000
       └── sbdb-ai-query.theronlab.com     → LXC 128 uvicorn :8004
```

No firewall ports are opened on the host. The tunnel originates from inside the LAN out to Cloudflare, so the public connection is initiated outbound. Cloudflare then routes requests for the two hostnames back through the tunnel to the right container.

---

## Backups

Per the project notes:

- **Proxmox vzdump** runs nightly for LXC 124, 125, 126. LXC 127 and 128 should be added to the backup job (verification pending).
- **Synology mirror** replicates the Proxmox backup directory to a NAS for off-host redundancy. The mirror scope needs to cover the new containers.

For most failure scenarios, the cheapest recovery is to re-run the deploy scripts and replay the pipeline. LXC 127 is fully stateless — `deploy-sbdb-frontend` rebuilds it in about 10 minutes. LXC 128's only unique state is the Anthropic API key, which also exists on LXC 125. The data directory is the only thing that really needs careful backup, and it's a single DuckDB file.

---

## Reproducing on Your Own Infrastructure

If you wanted to set this up yourself, the rough steps are:

1. Install Proxmox VE on a reasonably capable machine (~32 GB RAM is comfortable; 16 GB is workable).
2. Create five LXCs from a Debian 12 template, with IPs and ports matching the table in [`ARCHITECTURE.md`](ARCHITECTURE.md) — or your own scheme.
3. Set up a shared data directory on the host and bind-mount it into LXC 124 read-write and into LXC 125/126/128 read-only.
4. Place your Anthropic API key at `/etc/artemis-secrets/anthropic.key` on each container that needs it (125, 128, and 124 for vision extraction).
5. Copy the contents of `apps/mummster-pipeline/` into `/opt/mummster/pipeline/` on LXC 124, install Python deps, run the pipeline.
6. Repeat for each app/container, following the pattern.

You don't need the broker — it's a convenience layer. You can run all the deploy steps manually with `pct exec` and `pct push`. The broker exists because manual deployment of five containers gets tedious.

The Google Sheet ID for the source data is in the project's data ingestion notes; you'd need either your own equivalent sheet or to point at the existing public one. Same for `sbdb.xlsx` — that's a community-curated workbook that lives in a shared Google Drive folder.
