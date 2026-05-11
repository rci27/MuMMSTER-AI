# Architecture

This document describes the full MummSTER AI architecture — every container, every service, every data path. It's the document to read first if you want to understand how the system works end-to-end.

---

## Host

The entire system runs on a single Proxmox VE host:

- **ARTEMIS** — Intel i7-12700, 64 GB RAM, on a private LAN at `192.168.1.99`.

Proxmox is a Debian-based hypervisor that runs lightweight Linux containers (LXCs). Each LXC is essentially a sandboxed userspace on top of the host kernel — much lighter than a VM, much more isolated than a Docker container.

The MummSTER stack uses five LXCs. Each container has one job. Nothing is shared except read-only access to the database file.

```
ARTEMIS (Proxmox host)
│
├── /mnt/artemis-data/                      ← host-mounted storage (used for bind mounts)
│   ├── mummster/data/mummster.db           ← DuckDB master database
│   ├── mummster/data/datasette.db          ← SQLite export for Datasette
│   └── mummster/imports/sbdb.xlsx          ← canonical Excel workbook (curated)
│
├── LXC 124 — mummster              (192.168.1.72)
├── LXC 125 — mummster-query        (192.168.1.74)
├── LXC 126 — mummster-curation     (192.168.1.75)
├── LXC 127 — sbdb-frontend         (192.168.1.76)
└── LXC 128 — sbdb-query            (192.168.1.77)
```

---

## Container Inventory

| LXC | Name              | IP            | Port  | Purpose                                          | Exposure       |
|-----|-------------------|---------------|-------|--------------------------------------------------|----------------|
| 124 | mummster          | 192.168.1.72  | 8001  | Data pipeline + Datasette data viewer            | LAN / Tailscale |
| 125 | mummster-query    | 192.168.1.74  | 8002  | Internal natural-language query interface         | LAN / Tailscale |
| 126 | mummster-curation | 192.168.1.75  | 8003  | Point sheet curation tool                         | LAN / Tailscale |
| 127 | sbdb-frontend     | 192.168.1.76  | 3000  | Public Gatsby/React static site                   | Public (Cloudflare) |
| 128 | sbdb-query        | 192.168.1.77  | 8004  | Public AI query API                               | Public (Cloudflare) |

---

## LXC 124 — mummster (Data Pipeline + Datasette)

**The source of truth for everything else.** This container ingests data from all sources, processes it, and produces the canonical database file that every other container reads from.

### Stack
- Python 3.11
- DuckDB (analytical database — fast columnar SQL on a single file)
- SQLite (for Datasette compatibility)
- Datasette (Simon Willison's read-only data viewer)
- Tesseract OCR (fallback when `pdftotext` can't extract text from a PDF)
- Claude Vision API (for high-quality structured extraction from PDF point sheets)
- Google Sheets `gviz` CSV endpoint (no auth needed for read access on public sheets)

### What it does

The pipeline runs end-to-end (annual cadence, manually triggerable) in this order:

1. **Fetch Google Sheet tabs.** Six tabs pulled via the `gviz` endpoint as CSV — main results, Hall of Fame, parade info, Lifetime Achievement, Custard's Last Stand, Viewer's Choice.
2. **Download PDFs.** 59 point sheet PDFs from a shared Google Drive folder.
3. **Run OCR.** `pdftotext` first (fast, works on born-digital PDFs). Tesseract fallback for scanned pages.
4. **Run text parser** (`parse_scores.py`). Regex-based extraction. Reliable for pre-modern era (1963–1990).
5. **Run vision extractor** (`vision_extract.py`). Claude Vision API on PDF page images. Better for complex modern formats.
6. **Import `sbdb.xlsx`** (`import_sbdb.py`). Twelve tabs of curated data import as `sbdb_*` prefixed tables. These are the authoritative records.
7. **Export DuckDB → SQLite** for the Datasette viewer.
8. **Generate `data_context.md`** — a markdown summary file with real data examples (top bands, era summaries, gap years, score distributions) that gets injected into the query interface's system prompt.

A cost guard aborts the pipeline if the estimated Vision API cost exceeds **$2.00**. The override is `FORCE_VISION=true`.

### Datasette

Datasette wraps the SQLite export in a read-only web UI at `http://mummster.theronlab.home`:

- Every table has its own browsable URL.
- Every URL has a `.json` variant for machine-readable access.
- A built-in SQL query editor at `/datasette?sql=...`.

This is the lightweight viewer used for spot checks and direct SQL exploration. It is not the AI interface.

### Source location
Source code: [`apps/mummster-pipeline/`](../apps/mummster-pipeline/).

---

## LXC 125 — mummster-query (Internal AI Interface)

**The natural-language query interface, internal-only.** This is where the original AI work happens. LXC 128 is a CORS-open clone for public exposure — but development and testing happens here first.

### Stack
- FastAPI + Uvicorn (Python ASGI)
- Claude API (Sonnet 4.6 for SQL generation, Haiku 4.5 for interpretation/chart/refinement)
- DuckDB (read-only access to `mummster.db` via bind mount from host)
- WeasyPrint (PDF export of full query responses)

### Query pipeline

```
User question
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [1] SQL generation                                          │
│     Model: claude-sonnet-4-6                                 │
│     Tokens: 8,000   Extended thinking budget: 5,000          │
│     System prompt assembled by schema.py — includes          │
│     full table inventory, era boundaries, SQL rules,         │
│     band-name matching rules, gap-year rules, the            │
│     "DuckDB not PostgreSQL" reminder, and the current        │
│     contents of data_context.md.                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [2] Validation                                              │
│     EXPLAIN dry-run against DuckDB.                          │
│     If invalid: auto-fix with claude-sonnet-4-6 (4,000       │
│     tokens, no thinking) — up to 2 attempts.                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [3] Execution                                               │
│     conn.execute(sql).fetchdf() — read-only.                 │
│     Result is a Pandas DataFrame, capped at 100 rows         │
│     for PDF export but unlimited in the JSON response.       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [4] Interpretation                                          │
│     Model: claude-haiku-4-5-20251001                         │
│     Tokens: 1,500                                            │
│     Plain-English explanation grounded in the rows.          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [5] Chart spec                                              │
│     Model: claude-haiku-4-5-20251001                         │
│     Tokens: 1,500                                            │
│     Returns a Chart.js JSON spec, or null.                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [6] Refinement                                              │
│     Model: claude-haiku-4-5-20251001                         │
│     Tokens: 200                                              │
│     One-sentence follow-up suggestion.                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
SSE-streamed to the browser.
```

### Conversation memory

Conversation history is held **in-process only** — the last 5 exchanges live in a Python dict in the FastAPI worker. Nothing is written to disk. Restarting the service clears history for everyone.

This is intentional: the system has no user accounts, no auth, no per-session isolation in its current form. The next planned upgrade is browser-generated session IDs so two users on the same instance don't see each other's context.

### Routes

| Method | Path                  | Purpose                                |
|--------|-----------------------|----------------------------------------|
| POST   | `/query`              | Start a new query, returns query_id    |
| GET    | `/stream/{query_id}`  | SSE stream of pipeline events          |
| POST   | `/export/{query_id}`  | Generate PDF of completed query        |
| GET    | `/health`             | Health check                           |
| GET    | `/`                   | Static HTML frontend                   |

### Source location
Source code: [`apps/mummster-query/`](../apps/mummster-query/).

---

## LXC 126 — mummster-curation (Curation Tool)

**The human-in-the-loop tool for fixing point sheet data.** Currently a prototype that supports 1977 only; multi-year support is in the roadmap.

### Stack
- FastAPI + Uvicorn
- DuckDB (separate `curation.db` for raw extracted data + curated overlays)

### What it does

The curation tool presents a side-by-side view: the original PDF page on the left, an editable data grid on the right. The user can:

- Edit any cell to correct an extraction error
- Rename columns inline
- Delete columns that shouldn't have been extracted
- Edit band names
- Mark a year as "complete" — promotes the curated data into the authoritative tables

The output goes into `sbdb_*` tables, which take precedence over the raw `parsed_scores` extraction.

### Why a separate tool

The pipeline's vision extraction does about 80% of the work. The remaining 20% — header confusion, column-misidentification on radically different formats, OCR errors in low-quality scans — is faster to fix by a human reviewing the original PDF than by trying to make the AI extractor more clever. The curation tool is the bridge between raw extraction and trustworthy data.

### Source location
Source code: [`apps/mummster-curation/`](../apps/mummster-curation/).

---

## LXC 127 — sbdb-frontend (Public Static Site)

**The public face of MummSTER.** A Gatsby 5 + React 18 static site that fetches all its data **at build time** from LXC 124's Datasette API, then serves pre-rendered HTML via nginx.

### Stack
- Gatsby 5 (static site generator)
- React 18
- Chart.js (for the inline stats charts)
- nginx (serves the built site)
- Cloudflare Tunnel (public exposure without opening firewall ports)

### Why static

Build-time data fetching means:
- **No runtime database load** — every page is plain HTML/CSS/JS at serve time.
- **Cheap to scale** — nginx serving static files handles arbitrary load.
- **No public DB exposure** — Datasette stays on the LAN; only Cloudflare-fronted Gatsby HTML is public.
- **Rebuilds when data changes** — pushing a code change or running the pipeline triggers a fresh build via the deployment automation.

### Pages

| Path                    | Content                                                       |
|-------------------------|---------------------------------------------------------------|
| `/`                     | Home — latest year results table, hero, stats bar             |
| `/results`              | All-years results browser with year selector                  |
| `/bands`                | Band grid with filter and search                              |
| `/bands/[slug]`         | Per-band profile with placement history chart                 |
| `/captains/[slug]`      | Per-captain profile with banded performance history           |
| `/parade`               | Parade-day history (weather, mayor, awards by year)           |
| `/search`               | Global cross-table search                                     |
| `/ask`                  | AI query interface (calls LXC 128 from the browser via fetch) |

### Source location
Source code: [`apps/sbdb-frontend/`](../apps/sbdb-frontend/).

---

## LXC 128 — sbdb-query (Public AI Query API)

**A CORS-open clone of LXC 125.** Same code, same model tiering, same query pipeline — but with CORS configured for the public domain so the browser-side Gatsby site can call it directly.

### What's different from LXC 125

- `CORS allow_origins` includes `https://sbdb-ai.theronlab.com`
- Service unit name is `sbdb-query.service` instead of `mummster-query.service`
- Internal hostname is `sbdb-ai-query.theronlab.com`, fronted by the Cloudflare tunnel
- Same bind mount to `/opt/mummster/data/mummster.db` (read-only)

Everything else — `schema.py`, `pipeline.py`, `main.py`, `pdf_export.py` — is identical to LXC 125 at deploy time.

### Why a clone instead of just opening LXC 125 publicly

Two reasons:

1. **Isolation.** If a public misuse pattern stresses the public API, LXC 125 keeps working internally for development and admin use.
2. **Future divergence.** Public-facing changes (rate limiting, per-session IDs, abuse mitigation) belong in LXC 128. LXC 125 stays simple as the dev/test environment.

### Source location
Source code: [`apps/sbdb-query/`](../apps/sbdb-query/).

---

## Networking

### Internal (LAN-only)
- `mummster.theronlab.home` → LXC 124 (Datasette)
- `mummster-query.theronlab.home` → LXC 125
- LXC 126 reached by IP only — no internal DNS, prototype tool

### Public (Cloudflare Tunnel)
- `sbdb-ai.theronlab.com` → LXC 127 (Gatsby site)
- `sbdb-ai-query.theronlab.com` → LXC 128 (AI query API)

The Cloudflare Tunnel terminates on a separate edge LXC on the same host (not part of this stack) and routes hostname-based traffic to the right backend container.

The static site uses standard `fetch()` from the browser to hit the AI API. CORS is configured on LXC 128 to allow the Gatsby origin.

---

## Data Flow

### When the pipeline runs

```
Google Sheet ────────────────┐
PDF folder on Drive ─────────┤
sbdb.xlsx (uploaded) ────────┘
            │
            ▼
       LXC 124 sync.py
       ├── fetch sheet tabs
       ├── download PDFs
       ├── OCR
       ├── parse_scores.py
       ├── vision_extract.py
       ├── import_sbdb.py
       ├── export DuckDB → SQLite
       └── generate_context.py
            │
            ▼
   /mnt/artemis-data/mummster/data/
   ├── mummster.db        (DuckDB master)
   ├── datasette.db       (SQLite for viewer)
   └── data_context.md    (context for AI prompts)
            │
   ┌────────┼────────────────────┬────────────────┐
   ▼        ▼                    ▼                ▼
 LXC 124  LXC 125              LXC 127          LXC 128
Datasette mummster-query   sbdb-frontend       sbdb-query
                          (build-time fetch)   (runtime query)
```

### When a user asks a question on the public site

```
Browser at sbdb-ai.theronlab.com/ask
   │
   │  POST /query { "question": "..." }
   ▼
LXC 128 sbdb-query (FastAPI)
   │
   │  schema.py builds prompt
   │  pipeline.py runs steps 1-6
   │  Streams SSE back
   ▼
Browser renders streaming response
```

The browser never touches the database directly. It never touches LXC 124. The Datasette API is build-time-only (Gatsby's `gatsby-node.js` fetches it during `npm run build`, never at runtime). Only the AI API is hit at runtime, and that runs read-only against the DuckDB file.

---

## Deployment

Deployment is handled by a "broker" pattern in a separate private repo. The broker is a small SSH-callable script on the Proxmox host that exposes a set of named actions (`deploy-mummster-query`, `update-sbdb-frontend-source`, `validate-mummster-curation`, etc.). Each action is a shell script that:

1. Pulls the latest source from this repo
2. Stops the relevant container service
3. Pushes updated source files into the container via `pct push`
4. Runs `npm install` / `pip install` as needed
5. Restarts the service
6. Runs a validation check

This means deploying a change is a single SSH call. The deployment automation itself is not in this public repo because it contains host-specific paths and credentials.

For more on the deployment model see [`docs/DEPLOYMENT.md`](DEPLOYMENT.md).
