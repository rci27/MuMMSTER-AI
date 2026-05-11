# MummSTER — Phase 1 Build Log

**Status:** Complete
**Covers:** LXC 124 — data pipeline + Datasette data viewer

---

## What Phase 1 Built

Phase 1 was about getting the data into a single, queryable place. Before this phase, the Mummers String Band data existed in:

- A community-curated Google Sheet (6 tabs, ~1,960 main results rows + supporting tables)
- 59 scanned PDF point sheets sitting in a Google Drive folder
- An ad-hoc Excel workbook with cleaned canonical records (`sbdb.xlsx`, 12 tabs)

After Phase 1, all three sources are ingested into a single DuckDB database on LXC 124, with a Datasette web UI for direct exploration.

## Container

**LXC 124 — mummster**
- IP: `192.168.1.72`
- Hostname: `mummster.theronlab.home`
- Datasette port: `8001`
- Bind mount: `/mnt/artemis-data/mummster` → `/opt/mummster` (read-write)

## Pipeline Architecture

```
Google Sheet (gviz CSV endpoint, no auth)
    ↓
sheets.py — fetch 6 tabs
    ↓
[main_results, hall_of_fame, parade_info,
 lifetime_achievement, custards_last_stand, viewers_choice]
    ↓
DuckDB mummster.db

Google Drive PDFs
    ↓
drive.py — download 59 PDFs (cached)
    ↓
ocr.py — pdftotext → Tesseract fallback
    ↓
parse_scores.py — regex extraction (pre-modern)
vision_extract.py — Claude Vision API (modern + contemporary)
    ↓
normalize.py — field name standardization
    ↓
DuckDB parsed_scores, parsed_scores_summary

sbdb.xlsx (uploaded manually to imports/)
    ↓
import_sbdb.py — 12 tabs → sbdb_* tables
    ↓
db.py purge_legacy_tables — remove old non-sbdb_ tables

Final step:
db.py export_to_sqlite → datasette.db
generate_context.py → data_context.md
```

## Datasette

Runs as a separate long-running service on port 8001. Reads `datasette.db` (the SQLite export of DuckDB — Datasette is SQLite-only). Provides:

- Browsable web UI for every table
- Built-in SQL query interface
- JSON API at every endpoint (add `.json` to any URL)
- Shareable URLs for queries

Available at `http://mummster.theronlab.home`.

## Cost Guard

The vision extraction step is the only API-expensive part of the pipeline. A cost guard estimates total API spend before starting and aborts if the estimate exceeds **$2.00**. Override is `FORCE_VISION=true`. This prevented a runaway extraction during an early test run when the rate limiter wasn't yet in place.

## Annual Cadence

The pipeline is designed to run after each year's parade — once a year, plus on demand when corrections or new PDFs come in. Manual trigger via the broker: `run-mummster-pipeline`.

## Phase 1 Outcomes

- 1,960 main results rows from 1963–2026
- 71 Hall of Fame inductees
- 126 parade-info records from 1901–2026
- 24 Lifetime Achievement recipients
- 18 Custard's Last Stand records
- 15 Viewer's Choice records
- 34,000+ judge-level parsed_scores rows
- 59 parsed_scores_summary records
- 12 sbdb_* tables imported from the canonical workbook
- Datasette live and serving queries

## Phase 1 Limitations (Carried Into Phase 2)

- `parsed_scores.confidence` is a flat 0.50 — placeholder pending curation
- Contemporary era (2014–2026) has known Total Score misidentifications
- Some duplicate rows in `parsed_scores` from multiple pipeline runs
- 5 gap years with no extractable point sheet data (1964, 1967, 1999, 2001, 2021)

These were all known going into Phase 2, which addressed access and querying. Data curation is the long-term Phase 3+ effort.
