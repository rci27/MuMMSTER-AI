# Codebase Overview

A file-by-file walkthrough of every meaningful Python and JavaScript module in the MummSTER system, organized by container.

---

## LXC 124 — Pipeline (`apps/mummster-pipeline/`)

### `sync.py`
The pipeline orchestrator. Runs the full ingestion-to-database flow in order: fetch Google Sheet tabs → download PDFs → run OCR → run text parser → run vision extractor → import `sbdb.xlsx` → export DuckDB to SQLite → regenerate `data_context.md`. Triggered by the broker's `run-mummster-pipeline` command. Everything else in this directory is called by this file directly or indirectly.

### `sheets.py`
Google Sheet fetcher. Reads the six tabs via the public `gviz` CSV endpoint — no Google API auth required. Returns parsed Pandas DataFrames.

### `drive.py`
PDF downloader. Pulls 59 point sheet PDFs from a shared Google Drive folder using public sharing links. Caches locally to avoid re-downloading on every run.

### `ocr.py`
PDF-to-text. Tries `pdftotext` first (fast, works on born-digital PDFs). Falls back to Tesseract OCR for scanned pages where `pdftotext` returns empty or garbage output.

### `parse_scores.py`
The text-based PDF parser. Uses regex and column-position heuristics to extract structured scoring data from OCR output. Reliable for pre-modern era (1963–1990) where the point sheet formats are simple. Struggles with modern formats; being superseded by `vision_extract.py` for complex years.

### `vision_extract.py`
The Claude Vision API extractor. Converts PDF pages to images and sends them to Claude with a structured extraction prompt. Returns JSON with band names, scores, judge names, and categories. More accurate than `parse_scores.py` for complex formats but costs API tokens per run. Includes a per-run cost guard, a rate limiter, streaming response handling for large extractions, and a JSON-recovery fallback for malformed model output.

### `normalize.py`
The shared field-name normalization dictionary. Maps raw field names exactly as they appear on point sheets to standard names — `"COS"` → `"Costume"`, `"production"` → `"Visual Performance"`, etc. Both `parse_scores.py` and `vision_extract.py` import from this single source of truth. Adding a new variation is a one-line dictionary update.

### `import_sbdb.py`
The Excel importer. Reads `sbdb.xlsx`, imports all twelve tabs as `sbdb_*` prefixed DuckDB tables, creates `sbdb_status_codes`, and calls `purge_legacy_tables()` to remove any old non-`sbdb_` versions. Also handles the DuckDB → SQLite export for Datasette compatibility.

### `db.py`
The database layer. Defines the DuckDB schema, handles table creation, owns the upsert logic for `parsed_scores`, manages the SQLite export, creates backups, and exposes `purge_legacy_tables`. Every database write in the pipeline goes through this file.

### `generate_context.py`
The data context summary generator. Runs at the end of every pipeline sync. Reads the DuckDB database and produces `data_context.md` — a markdown summary with concrete data examples (first prize winners by year, band records, era summaries, notable streaks, data quality breakdown). This file gets injected into the query interface's system prompt so the AI has real data context, not just schema definitions.

---

## LXC 125 — Internal Query Interface (`apps/mummster-query/`)

### `main.py`
The FastAPI web server. Routes:

| Method | Path                  | Purpose                                |
|--------|-----------------------|----------------------------------------|
| POST   | `/query`              | Start a new query, returns `query_id`  |
| GET    | `/stream/{query_id}`  | SSE stream of pipeline events          |
| POST   | `/export/{query_id}`  | Generate PDF of completed query        |
| GET    | `/health`             | Health check                           |
| GET    | `/`                   | Static HTML frontend                   |

Wires `schema.py` and `pipeline.py` together. Loads the API key at startup. Manages CORS. Serves the static frontend from `/static`.

### `schema.py`
Two jobs:

1. **Schema introspection.** At startup, queries the DuckDB metadata tables to discover every table name and every column definition. Caches the result.
2. **System prompt assembly.** Every query gets a system prompt that includes the discovered schema, era boundaries, SQL rules, band-name matching rules, gap-year rules, the "DuckDB syntax not PostgreSQL" reminder, and the full contents of `data_context.md`. This is the single source of truth for what the AI "knows" about the data.

Every fix to "how the AI understands the data" lives here. The system prompt is rebuilt each time `schema.py` is touched, which means there is no caching of the prompt itself — the schema introspection runs once at startup, but the prompt is assembled per-request.

### `pipeline.py`
The query execution engine. Async SSE generator that runs the full six-step query pipeline:

1. SQL generation (Claude Sonnet, extended thinking)
2. Validation (DuckDB EXPLAIN dry-run, auto-fix up to 2x)
3. Execution
4. Interpretation (Claude Haiku)
5. Chart spec (Claude Haiku)
6. Refinement suggestion (Claude Haiku)

Stores the completed query result in an in-memory `query_store` dict keyed by `query_id` so the PDF export can retrieve it later. Streams events to the browser via Server-Sent Events.

### `pdf_export.py`
WeasyPrint-based PDF generator. Takes a completed query result and renders an HTML template (gold/navy styled to match the site) into a PDF — full prose answer, embedded chart image, results table (capped at 100 rows), SQL preview, generation timestamp.

### `static/index.html`
The internal frontend. Two-panel layout: chat on the left, pipeline thinking panel on the right. Streaming thinking text, SQL preview, live step indicators, Chart.js rendering, results table in an accordion, refinement hint, PDF export button per answer. Dark navy + gold theme. Mobile-optimized with collapsible thinking panel.

---

## LXC 126 — Curation Tool (`apps/mummster-curation/`)

### `main.py`
FastAPI server for the curation interface. Serves the side-by-side PDF + editable grid view. Routes for fetching a year's extracted data, saving edits, and marking a year complete.

### `db.py`
Database layer for the separate `curation.db` DuckDB file. Holds raw extracted data in `curated_scores_raw` and overlays in `curated_scores`. Promotion logic that pushes curated data into the master `mummster.db` is here.

### `static/index.html`
The curation grid frontend. PDF viewer on the left, editable data grid on the right. Inline column-name editing, column delete buttons, per-row band-name editing, CSV export in column order.

---

## LXC 127 — Public Frontend (`apps/sbdb-frontend/`)

A Gatsby 5 + React 18 static site. Key files:

### `gatsby-node.js`
The build-time data loader. During `npm run build`, fetches every needed table from LXC 124's Datasette JSON API. Creates GraphQL nodes for each row. Generates one static page per band and per captain via `createPages`. After build, every page is plain HTML/CSS/JS — no runtime database calls.

### `gatsby-config.js`
Site metadata, plugin configuration. Tailwind, image optimization, SEO plugins.

### `src/pages/index.js`
Home page. Hero section, latest year full results table with all columns and YouTube thumbnails, captain name links, stats bar, AI teaser bar.

### `src/pages/results.js`
All-years results browser with year selector dropdown.

### `src/pages/bands.js`
Band grid with filter and search.

### `src/templates/band.js`
Template for `/bands/[slug]` pages. Placement history chart, full performance history table, theme list.

### `src/templates/captain.js`
Template for `/captains/[slug]` pages. Years active, appearances, first prizes, bands captained, sortable history table.

### `src/pages/parade.js`
Parade-day history. Four-card layout: parade day facts, annual awards, hall of fame, competition awards. Each card conditional on data being present for the selected year.

### `src/pages/search.js`
Cross-table global search. Searches bands, competition results, parade facts, awards.

### `src/pages/ask.js`
The AI query interface. Calls LXC 128 via SSE. Same query pipeline experience as the internal interface, with a public-facing disclaimer about AI accuracy and a "report an issue" mailto link.

---

## LXC 128 — Public Query API (`apps/sbdb-query/`)

A clone of `apps/mummster-query/` with two source differences:

- `main.py` — CORS `allow_origins` includes `https://sbdb-ai.theronlab.com`, and references to `mummster-query` are renamed to `sbdb-query` (logging, service name, etc.)
- `static/index.html` — unused at runtime (the Gatsby `/ask` page is the public UI), kept as a fallback

All other files (`schema.py`, `pipeline.py`, `pdf_export.py`) are byte-for-byte identical to LXC 125 at deploy time. This is intentional: changes to query behavior happen on LXC 125 first, get tested internally, and then propagate to LXC 128 via a re-sync.

---

## How the Files Work Together

### When a user asks a question

```
ask.js (Gatsby page) — user types question, clicks Ask
   │
   │  fetch POST /query → SSE GET /stream/{id}
   ▼
main.py (FastAPI, LXC 128) — receives request, creates query_id
   │
   │  starts async generator
   ▼
pipeline.py (LXC 128) — orchestrates the 6-step pipeline
   │
   ├── schema.py — builds system prompt with full domain context
   ├── Claude API (Sonnet) — SQL generation with extended thinking
   ├── DuckDB EXPLAIN — validates SQL, auto-fixes up to 2x
   ├── DuckDB execute — read-only query against mummster.db
   ├── Claude API (Haiku) — interpretation
   ├── Claude API (Haiku) — chart spec
   └── Claude API (Haiku) — refinement suggestion
   │
   │  each step emits an SSE event
   ▼
ask.js — renders streaming text, SQL preview, table, chart
```

### When the pipeline runs

```
broker run-mummster-pipeline (manual trigger or scheduled)
   │
   ▼
sync.py (LXC 124) — orchestrator
   │
   ├── sheets.py — fetch 6 Google Sheet tabs
   ├── drive.py — download 59 PDFs (cached)
   ├── ocr.py — extract text (pdftotext + Tesseract fallback)
   ├── parse_scores.py — regex extraction (pre-modern era)
   ├── vision_extract.py — Claude Vision API (modern + contemporary)
   ├── import_sbdb.py — import sbdb.xlsx → sbdb_* tables
   ├── db.py — DuckDB → SQLite export for Datasette
   └── generate_context.py — regenerate data_context.md
   │
   ▼
/mnt/artemis-data/mummster/data/
   ├── mummster.db (DuckDB master, used by query interface)
   ├── datasette.db (SQLite, used by Datasette viewer)
   └── data_context.md (markdown, injected into AI prompt)
```

After the pipeline finishes, the data is immediately available to LXC 125 and 128 (they read the file directly via bind mount). LXC 127's Gatsby site does *not* automatically rebuild — that requires running `update-sbdb-frontend-source` via the broker, which triggers a fresh `npm run build` against the updated Datasette data.
