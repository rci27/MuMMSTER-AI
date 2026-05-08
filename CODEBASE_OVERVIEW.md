# MummSTER Codebase Overview

**Last updated:** 2026-05-07
**Repo:** `project-artemis-automation`
**Audience:** Developer onboarding reference — file-by-file descriptions without having to read the code.

---

## System Map

```
LXC 124 — mummster (192.168.1.72)       LXC 125 — mummster-query (192.168.1.74)
  /opt/mummster/pipeline/                 /opt/mummster-query/app/
    sync.py          orchestrator           main.py        FastAPI server
    db.py            database layer         schema.py      prompt assembly
    import_sbdb.py   Excel importer         pipeline.py    query engine
    vision_extract.py  Vision AI extractor
    parse_scores.py  text parser
    normalize.py     field dictionary
    generate_context.py  context writer
```

Data flows left to right: pipeline writes to `mummster.db` (DuckDB) and exports
`datasette.db` (SQLite). LXC 125 reads `mummster.db` via a read-only bind mount.

---

## LXC 124 — Data Pipeline

### `sync.py` — Pipeline Orchestrator

**Role:** Entry point for every pipeline run. Orchestrates all steps in order and
collects statistics. Called by the `mummster-pipeline` systemd service (daily timer)
and manually via the `run-mummster-pipeline` broker action.

**What it does:**

```
Pre-step (optional): if /opt/mummster/data/imports/sbdb.xlsx exists →
  import_sbdb.run_import()  — loads all sbdb_ tables from Excel

Step 1/6: Fetch Google Sheets tabs via gviz CSV (legacy — 6 tabs)
Step 2/6: Write sheet tabs to DuckDB, then immediately purge legacy table names
          (purge only runs if xlsx import ran — xlsx is now source of truth)
Step 3/6: Download PDFs from Google Drive links found in sheet data
          (59 PDFs, all cached; subsequent runs are near-instant)
Step 4/6: OCR new PDFs — pdftotext (native) or Tesseract (scanned fallback)
          Results written to ocr_results table
Step 5/6: Parse structured scores from OCR text → parsed_scores table
          Era-aware: different logic for pre-modern / modern / contemporary
Step 6/6: Vision AI extraction for years below confidence threshold
          Calls Claude API with PDF page images; ~$0.05–$0.10 per year
Post:     Export DuckDB → SQLite (datasette.db)
          Generate data_context.md via generate_context.py
```

**Config:** Reads `/opt/mummster/config.env` (dotenv format). Required keys:
`SHEET_ID`, `DB_PATH`, `PDF_DIR`. Optional: `BACKUP_DIR`, `ANTHROPIC_KEY_PATH`,
`VISION_COST_LIMIT_USD`, `PDF_LINK_COLUMN`.

**Key module-level constant:** `XLSX_IMPORT_PATH = Path("/opt/mummster/data/imports/sbdb.xlsx")` —
the presence of this file determines whether the optional pre-step runs.

**TAB_MAP:** Also defined at module level — maps Google Sheet tab names to legacy
DuckDB table names (still fetched for PDF link discovery, immediately purged after write).

---

### `db.py` — Database Layer

**Role:** All DuckDB read/write operations. No business logic — pure database interactions.
Every module that touches the database goes through this file.

**Key functions:**

| Function | What it does |
|----------|-------------|
| `init_db(db_path)` | Opens (or creates) the DuckDB file. Creates `ocr_results` table if absent. Returns connection. |
| `backup_db(db_path, backup_dir)` | Copies the DuckDB file to a timestamped backup before any writes. Enforces 10-backup retention. Returns backup path or None. |
| `write_sheet_tab(conn, table_name, df, data_source)` | Writes a DataFrame to DuckDB as a `CREATE OR REPLACE TABLE`. Runs `_enrich()` first to add pipeline metadata columns. |
| `write_sheet_tabs(conn, tabs)` | Batch version — iterates a `{table_name: DataFrame}` dict. |
| `write_ocr_results(conn, results, overwrite_filenames)` | Appends OCR results; skips already-processed filenames unless in `overwrite_filenames`. |
| `purge_legacy_tables(conn)` | Drops the 6 legacy sheet tables (`main_results`, `hall_of_fame`, etc.) that were replaced by `sbdb_*` equivalents. Safe to call repeatedly (IF EXISTS). |
| `export_to_sqlite(duckdb_path, sqlite_path)` | Exports all DuckDB tables to SQLite via pandas `.to_sql()`. This is what Datasette serves. |
| `get_stats(conn)` | Returns `{table_name: row_count}` for all tables — used in pipeline summary logging. |

**`_enrich()` — pipeline metadata:** Every sheet table gets four added columns:
- `data_source` — the source tab name or "pdf-extracted"
- `completeness_flag` — per-row heuristic: `"complete"` (≥75% fields filled), `"partial"` (≥25%), `"missing"` (<25%)
- `era` — derived from year column: `"pre-modern"` / `"modern"` / `"contemporary"` / null
- `_synced_at` — UTC ISO timestamp

**`_PURGE_LEGACY_TABLES`:** Module-level list of the 6 table names dropped by `purge_legacy_tables()`.

---

### `import_sbdb.py` — Excel Importer

**Role:** Loads the validated Excel workbook (`sbdb.xlsx`) into DuckDB, replacing all
`sbdb_*` tables on every run. The primary source for all competition data since May 2026.

**What it does (in order):**
1. Opens `sbdb.xlsx` using openpyxl via pandas `ExcelFile`
2. Drops all existing `sbdb_*` tables from DuckDB (`_drop_sbdb_tables`)
3. For each of the 12 tabs in `TAB_MAP`: reads the sheet, normalizes headers
   (collapses whitespace/newlines, coerces non-string column names to str),
   drops Unnamed/NaN columns, writes to DuckDB as `CREATE OR REPLACE TABLE`
4. Creates `sbdb_status_codes` table and seeds 10 status code rows with `ON CONFLICT DO NOTHING` — preserves existing definitions
5. Exports all `sbdb_*` tables to `datasette.db` SQLite (only updates those tables, leaves others intact)
6. Calls `db.purge_legacy_tables(conn)` to remove any legacy tables recreated by the sheet fetch step
7. Runs `generate_context.py` via subprocess to regenerate `data_context.md`

**TAB_MAP:** Maps the 12 source tab names (as displayed in Excel) to `sbdb_` DuckDB table names.
Skipped tabs: `upcoming`, `winners`, `1st Prize Point Difference` (all derivable from sbdb_main_results).

**Idempotent:** Re-running produces identical results. Status code definitions entered by
hand via SQL UPDATE are preserved on re-run because of the `ON CONFLICT DO NOTHING` seeding.

**Called from:** `sync.py` pre-step (when xlsx present) AND can be run standalone:
`python3 import_sbdb.py [xlsx_path [db_path [sqlite_path]]]`

---

### `vision_extract.py` — Vision AI Extractor

**Role:** Extracts structured scoring data from PDF page images by sending them to the
Claude API with a vision prompt. Handles years and eras where text-based parsing failed
or produced low-confidence results.

**When it runs:** Step 6/6 of the pipeline. A year is queued for vision extraction if:
- It has no records in `parsed_scores` at all, OR
- Its records have average `parse_confidence` below `CONFIDENCE_THRESHOLD` (0.8)
- Special case: year 1968 is always included (marked `manual-entry-required` by parse_scores; vision re-extracts it)

**What it does:**
1. Queries `parsed_scores` to build the extraction queue — years below threshold
2. For each queued year: converts the PDF to a 150 DPI PNG image using pdf2image
3. Encodes the image as base64 and sends to `claude-sonnet-4-6` with a structured extraction prompt
4. Parses the JSON response — extracts band names, category scores, judge scores
5. Fuzzy-matches band names against known bands from `sbdb_main_results`
6. Normalizes field names via `normalize.normalize_field()`
7. Upserts records into `parsed_scores` (replaces existing if new confidence is higher)

**Cost control:**
- Rate limited to 5 API calls per minute
- Estimated cost logged per year (~$0.05–$0.10 per PDF)
- `COST_GUARD_LIMIT_USD` (default $10.00/run) aborts extraction if exceeded
- `force_vision=True` config flag bypasses cost guard

**Era handling:** Sends the same prompt regardless of era. The model reads the visual
structure of the document and adapts automatically.

**Known limitation:** Some pre-1963 years and heavily degraded scans still fail. Vision
extraction quality depends on scan resolution and document legibility.

---

### `parse_scores.py` — Text-Based Score Parser

**Role:** Extracts structured judge-level and category-level scores from OCR text in
`ocr_results`, writing results to `parsed_scores`. Handles three distinct era formats
through separate parsing logic.

**Three era parsers:**

| Era | Years | Format characteristics |
|-----|-------|----------------------|
| Era 1 (pre-modern) | before 1991 | Fixed-width rows; Music/Presentation/Costume; prize money column present; inconsistent headers |
| Era 2 (modern) | 1991–2013 | Tabular format; 5 scoring categories; more consistent but variable column ordering |
| Era 3 (contemporary) | 2014+ | Structured tables; 4 categories; judge matrix format from 2022 onward |

**Safety guarantees:**
- DuckDB backup created before any writes
- `parsed_scores` is append-only with upsert logic: existing records are only replaced if the new `parse_confidence` is strictly higher
- Each year is wrapped in a transaction — failure rolls back that year only
- Year 1968 is always skipped (`SKIP_YEARS = {1968}`) and flagged `manual-entry-required`

**`VISION_REQUIRED_YEARS`:** A hardcoded set of pre-modern years (1963–1981) where
`pdftotext` succeeds byte-count-wise but returns garbage (scanned images with no
real text). These years receive `parse_error = 'vision-extraction-required'` and
are not run through the era1 parser — `vision_extract.py` handles them instead.

**`parse_confidence`:** A 0.0–1.0 value computed per record based on how well the
extracted totals match the expected totals from `sbdb_main_results`. Used by
`vision_extract.py` to decide which years need re-extraction.

**Known issues (documented in source):**
- Years 1983–1989 parse at confidence 0.50 — suspected prize money column offset
- Era 2 (1991–2013) parse failures: 37 of 59 years; scoring format too variable for reliable regex extraction

---

### `normalize.py` — Field Name Dictionary

**Role:** Provides a single lookup table (`FIELD_NORMALIZATION`) and two utility
functions that ensure consistent field names across all era parsers and the vision
extractor. Prevents naming fragmentation in `parsed_scores`.

**`FIELD_NORMALIZATION` dict (~15 entries):** Maps lowercase variants to canonical names:
- `"ge music"` / `"arrangement"` → `"General Effect Music"`
- `"ge visual"` → `"General Effect Visual"`
- `"production"` → `"Visual Performance"`
- `"performance"` → `"Visual Performance"`
- `"total"` / `"grand total"` → `"Total Score"`
- `"position"` / `"order"` → `"marching_order"`
- Era-specific category names for Music, Presentation, Costume

**`normalize_field(name)`:** Case-insensitive lookup. Returns the canonical name if
found; otherwise returns the input stripped of whitespace. Used by both `parse_scores.py`
and `vision_extract.py` to normalize column headers and category labels before writing.

**`normalize_band_name(name)`:** Simple whitespace strip. Placeholder for more
sophisticated fuzzy normalization if needed in future.

---

### `generate_context.py` — Data Context Writer

**Role:** Introspects `mummster.db` and writes a structured markdown summary to
`data_context.md`. This file is loaded into the query interface's system prompt on
every service restart, giving the AI model concrete knowledge of the actual data
rather than relying solely on the static schema description.

**Called from:** `sync.py` (post-step via subprocess) and `import_sbdb.py` (direct subprocess).
Can also be run standalone: `python3 generate_context.py [db_path [out_path]]`.

**Output sections (7 total):**

| Section | Content |
|---------|---------|
| Dataset Overview | Year range, band count, total records, last sync timestamp |
| First Prize Winners | Full year-by-year table of first-prize winning bands |
| Band Records | All bands with >5 appearances: win counts, top-3 counts, best/worst place, active years |
| Era Summaries | Per-era stats: years with data, average bands per year, dominant bands |
| Notable Records | Most appearances, longest consecutive winning streaks, longest top-3 streaks |
| Data Quality | completeness_flag breakdown, PDF coverage, data source breakdown |
| Score Distributions | Mean/std/range per scoring category per era |

**Queries `sbdb_main_results`** (not the legacy `main_results`) for all statistics.
`GAP_YEARS = {1964, 1967, 1999, 2001, 2021}` are excluded from streak and aggregation
calculations. Column names are discovered dynamically using candidate lists (`YEAR_CANDIDATES`,
`BAND_CANDIDATES`, etc.) so the generator works even if column names shift slightly.

---

## LXC 125 — Query Interface

### `main.py` — FastAPI Web Server

**Role:** HTTP API and static file server. Handles request lifecycle — accepts questions,
manages in-flight query state, streams responses, serves the frontend, and handles PDF export.

**Routes:**

| Method | Path | What it does |
|--------|------|-------------|
| `GET /` | Index | Serves `static/index.html` (single-page frontend) |
| `POST /query` | Create query | Validates the question, generates a UUID, stores it in `_pending`, returns `{"query_id": "..."}` |
| `GET /stream/{query_id}` | Execute + stream | Pops the question from `_pending`, calls `run_query_pipeline()`, streams all SSE events to the client |
| `POST /export/{query_id}` | PDF export | Retrieves completed result from `query_store`, calls `generate_pdf()`, returns binary PDF |
| `GET /health` | Health check | Returns 200 OK — used by Uptime Kuma and `update-mummster-query-source` health check |

**Two-step API design:** `POST /query` just registers the question and returns a query ID.
The actual work happens only when the client opens the SSE stream via `GET /stream/{query_id}`.
This prevents the POST from blocking and allows the browser to receive streaming updates.

**SSE streaming:** Every pipeline step emits structured SSE events. The frontend renders
them incrementally — thinking tokens appear as the model reasons, SQL appears as it's
generated, results appear before interpretation is complete. Event types: `status`,
`thinking_stream`, `sql`, `sql_fix`, `validation`, `results`, `interpretation`, `chart`,
`refinement`, `warning`, `clarification_needed`, `complete`, `pipeline_error`.

**State:** `_pending` dict holds unstarted queries (question strings keyed by UUID).
`query_store` (imported from `pipeline.py`) holds completed query results for PDF export.

---

### `schema.py` — Database Introspection and Prompt Assembly

**Role:** Builds the system prompt that the Claude API receives with every query. Combines
live database introspection with static domain knowledge and a freshly loaded context
summary. The system prompt is the most important determinant of answer quality.

**Three components assembled by `get_system_prompt()`:**

**1. Live schema (cached at startup):** `_introspect_schema()` connects to `mummster.db`,
reads every table's column definitions and row counts from `information_schema.columns`,
and formats them as markdown tables. Cached in-process (`_schema_cache`) — refreshes only
on service restart. Result: the model sees the exact column names and types it will query.

**2. `_DOMAIN_CONTEXT` (static string, ~300 lines):** Encodes everything a human expert
knows about this dataset that is not derivable from the schema alone:
- Table inventory: description and purpose of all 16 tables
- Era boundaries and scoring category differences (pre-modern/modern/contemporary)
- Band histories for key bands (Fralinger, Ferko, Aqua, SPHA, Hegeman)
- Data quality rules (completeness_flag, data_source values)
- Gap year rules (1964/1967/1999/2001 have placement data; 2021 has nothing)
- Cross-era analysis rules (what is and isn't comparable)
- Marching order effect rules (tertile analysis required)
- Person profile response format (tribute tone, multi-table lookup)
- SQL rules: band name LIKE matching, 2021 mandatory exclusion, sbdb_ as primary source,
  prize money discontinuation after 2008, database coverage 1901–2026
- SQL sanity checks (four verification rules before finalizing any query)

**3. Live data context:** Loads `data_context.md` written by `generate_context.py`.
Contains current first-prize tables, band records, era summaries, score distributions —
concrete facts about the actual data updated after every pipeline run.

---

### `pipeline.py` — Query Execution Engine

**Role:** Orchestrates the full query lifecycle from natural language question to streamed
answer. Makes 4–8 Claude API calls per query depending on complexity. All output is
streamed to the caller as Server-Sent Events.

**Routing — three execution paths:**

```
Question arrives
    │
    ├─ _prize_is_ambiguous() → True
    │    Emit clarification_needed + interpretation with the clarifying question.
    │    No SQL generated. No API call.
    │
    ├─ _needs_deep_analysis() OR _involves_marching_order() OR _involves_person_tenure()
    │    → _run_multi_query_pipeline()
    │         Step 1: Decompose into 3–5 sub-questions (Claude API, extended thinking)
    │         Step 2: For each sub-question: generate SQL + EXPLAIN validate + execute
    │         Step 3: Synthesize all results into structured narrative (Claude API)
    │         Step 4: Suggest one follow-up question (Claude API)
    │
    └─ Otherwise
         → _run_single_query_pipeline()
              Step 1: Generate SQL (Claude API, extended thinking, streaming)
              Step 2: EXPLAIN validate; auto-fix up to 2 attempts if invalid
              Step 3: Execute — fetchdf() → JSON-serialize
              Step 4: Interpret results (Claude API, up to 200 rows passed)
              Step 5: Generate Chart.js spec if appropriate (Claude API)
              Step 6: Suggest one follow-up question (Claude API)
```

**Detection regexes:**

| Regex | Triggers on | Extra behavior |
|-------|------------|----------------|
| `_DEEP_ANALYSIS_RE` | "trend", "compare", "year by year", "percentile", "average", etc. | Standard multi-query decomposition |
| `_MARCHING_ORDER_RE` | "marching order", "draw position", "performance slot", etc. | Requires tertile analysis in decomposition |
| `_PERSON_TENURE_RE` | "captain", "tenure", "how long was X", "tell me about", "hall of fame", award names | 5-step person profile decomposition |
| `_PLACEMENT_QUESTION_RE` | "place", "win", "rank", "average finish", "best finish", etc. | Post-execution: warns if parsed_scores used |
| `_PRIZE_MONEY_RE` / `_PRIZE_POSITION_RE` | Prize money vs. finishing position disambiguation | No SQL — returns clarifying question |

**Interpretation persona:** All interpretation and synthesis prompts address the model
as a "Mummers historian" — not a "data analyst." The directive is: always go deep on the
first answer, never give a minimal response and suggest a follow-up, proactively include
years/placements/themes/context for tenure questions.

**Conversation history:** Last 5 exchanges stored in `_conversation_history`. Included
in SQL generation and interpretation messages as prior context. Shared across all requests
(single-user homelab app — no session isolation).

**Post-execution sanity checks:**
- If a placement/win question used `parsed_scores`: emit warning (parsed_scores only covers
  ~21 of 59 years — using it for win counts produces wrong answers)
- If zero rows returned on a year+band question that used `parsed_scores`: emit warning
  pointing to `sbdb_main_results`

---

## How The Files Work Together

### Flow 1: User asks a question

```
Browser POST /query {"question": "How long was Ron Ferry captain of Fralinger?"}
    │
    └─ main.py: generates UUID, stores in _pending, returns query_id

Browser GET /stream/{query_id}  (opens SSE connection)
    │
    └─ main.py: pops question, calls run_query_pipeline(query_id, question)
        │
        └─ pipeline.py: _involves_person_tenure("...captain...") → True
            │
            ├─ Step decompose: sends question to Claude with _PERSON_TENURE_DECOMPOSE_EXTRA
            │   Claude returns: ["Find years Ron Ferry appears in sbdb_captains",
            │                    "Find Fralinger's placement each of those years",
            │                    "Find Fralinger's historical average placement",
            │                    "Check all award tables for Ron Ferry",
            │                    "Find Fralinger's concepts for those years"]
            │
            ├─ For each sub-question: pipeline.py generates SQL using schema.py system prompt
            │   schema.py provides: live schema (column names/types) + _DOMAIN_CONTEXT
            │   (LIKE matching rules, table inventory) + data_context.md (current stats)
            │
            ├─ DuckDB read-only: executes each SQL, collects results
            │
            └─ Synthesis: sends all 5 result sets to Claude with _PERSON_TENURE_SYNTHESIS_EXTRA
                Claude writes tribute-format narrative with year-by-year detail
                → Streamed to browser as SSE "interpretation" event

Browser receives streaming events:
  status → thinking_stream → sql (×5) → results (×5) → interpretation → refinement → complete
```

### Flow 2: Pipeline run (daily or manual)

```
Broker: run-mummster-pipeline
    → pct exec 124 -- systemctl start mummster-pipeline
        → sync.py main()
            │
            ├─ Pre-step: sbdb.xlsx present → import_sbdb.run_import()
            │   - Opens Excel, drops all sbdb_* from DuckDB
            │   - Reads 12 tabs, writes sbdb_main_results... sbdb_parade_info
            │   - Seeds sbdb_status_codes (ON CONFLICT DO NOTHING)
            │   - Exports sbdb_* to datasette.db SQLite
            │   - Calls db.purge_legacy_tables() → drops main_results etc.
            │   - Runs generate_context.py → writes data_context.md
            │
            ├─ Steps 1-2: Fetches 6 legacy Google Sheet tabs via gviz CSV
            │   db.write_sheet_tabs() → writes main_results, hall_of_fame, etc.
            │   db.purge_legacy_tables() → immediately removes them again
            │   (Only purpose: surfacing Google Drive PDF links for step 3)
            │
            ├─ Step 3: drive.py scans fetched frames for Drive URLs → downloads
            │   59 PDFs to /opt/mummster/data/pdfs/ (cached; skips existing)
            │
            ├─ Step 4: ocr.py runs pdftotext (57 PDFs) or Tesseract (2 scanned PDFs)
            │   db.write_ocr_results() → appends to ocr_results table
            │
            ├─ Step 5: parse_scores.run_parse()
            │   Reads ocr_results, era-detects each year, runs era1/2/3 parser
            │   normalize.py used throughout for consistent field names
            │   Upserts to parsed_scores (only improves; never degrades confidence)
            │
            ├─ Step 6: vision_extract.run_vision_extract()
            │   Queries parsed_scores for years below CONFIDENCE_THRESHOLD (0.8)
            │   For each: convert PDF → PNG → base64 → Claude API → JSON
            │   normalize.py used for field names; fuzzy match band names
            │   Upserts results into parsed_scores
            │
            └─ Post: db.export_to_sqlite() → all DuckDB tables → datasette.db
                     generate_context.py → refreshes data_context.md
                     (LXC 125 picks up new data_context.md on next service restart)
```

---

## Key Design Decisions

### DuckDB over PostgreSQL

DuckDB is an embedded analytical database — no server process, no port, no connection
management. It lives as a single file. For this workload (batch writes once daily,
read-only queries on demand), it is dramatically simpler than PostgreSQL: no `pg_hba.conf`,
no users, no tablespaces, no index management. The analytical query style (aggregations,
window functions, percentile calculations) is exactly what DuckDB is optimized for.
The tradeoff is no concurrent writes — acceptable since only one pipeline runs at a time.

The SQLite export for Datasette exists because Datasette doesn't support DuckDB directly
as a live backend in a way that's stable for production use. DuckDB is the analytical
store; SQLite is the serving layer.

### The `sbdb_` Prefix

The prefix (`string band database`) namespaces all tables that come from the authoritative
Excel workbook. It distinguishes them from:
- Legacy sheet tables (`main_results`, `hall_of_fame`, etc.) that are now purged
- PDF pipeline tables (`parsed_scores`, `ocr_results`) that have a different data lineage
- Internal tables (`sbdb_status_codes`) that are seeded by code rather than imported

The prefix makes `SHOW TABLES` output immediately readable — one glance and you know
which tables are the current authoritative source vs. which are pipeline-generated detail.
It also makes the purge logic unambiguous: `DROP TABLE IF EXISTS` anything starting with
`sbdb_`, then reload from xlsx.

### Vision AI over Traditional OCR

Traditional OCR (Tesseract) reads pixels and produces character sequences. It cannot
understand document structure. When a 1970s point sheet has irregular spacing, handwritten
annotations, or pre-printed form borders that overlap with numbers, Tesseract produces
garbage.

Vision AI (Claude Sonnet 4-6 with image input) looks at the document the way a human
would — it understands that a table has rows and columns, that a number to the right of
a band name is probably that band's score, and that a header row at the top labels the
columns. It returns structured JSON rather than raw text.

The tradeoff is cost (~$0.05–$0.10 per year-PDF vs. zero for pdftotext). This is
managed via the confidence threshold: only years below 0.8 average confidence get Vision
AI treatment. Contemporary era PDFs (2014+) parse reliably with text-based methods and
never need vision extraction.

### Separate LXCs for Pipeline and Query Interface

The pipeline (LXC 124) is CPU-intensive during OCR and vision extraction, runs on a
schedule, and has no availability requirement (a failed run is a delayed update, not an
outage). The query interface (LXC 125) is always-on, latency-sensitive, and handles
user-facing HTTP requests.

Separating them means:
- Pipeline failures don't affect query interface availability
- Resource contention during a pipeline run doesn't degrade query response time
- The pipeline can be redeployed or debugged without touching the query interface
- The query interface accesses the database read-only via a bind mount — it cannot
  accidentally corrupt data during a pipeline run

The DuckDB file is shared between them via a host bind mount
(`/mnt/artemis-data/mummster/data`). LXC 124 has read-write access; LXC 125 has
read-only access. There is no race condition because the pipeline exports a complete
SQLite snapshot at the end — Datasette and the query interface both read from stable,
consistent snapshots rather than a database being actively written.
