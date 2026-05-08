# MummSTER — Phase 1 Build Log

**Date:** 2026-05-06
**Status:** Phase 1 complete — LXC 124 deployed, pipeline running, Datasette live
**Next:** LXC 125 — query interface (Text-to-SQL, chat UI, thinking window, Claude API)

---

## Project Purpose

MummSTER is a string band scoring analysis platform for the Philadelphia Mummers Parade. It ingests historical scoring data from Google Sheets and 59 scanned/native PDF point sheets, normalizes it into a structured database, and exposes it for analysis. The long-term goal is a statistical layer with Monte Carlo simulation and a public-facing frontend — Phase 1 establishes the data foundation.

Data sourced and compiled by **TJ Ferry** and **Brian Hamburg**.

---

## Data Sources

| Source | Description |
|--------|-------------|
| Google Sheets (live pull) | Primary structured data — results, scores, parade info across 6 tabs |
| 59 PDFs | Historical point sheets downloaded from Google Drive links embedded in the sheet |
| Gap years — manual entry needed | 1964, 1967, 1999, 2001 — no PDFs recovered |
| 2021 | COVID-19 — no parade held, no data |

### Google Sheets Tabs

| Tab | GID |
|-----|-----|
| Main Results | 1847002595 |
| Custard's Last Stand | 639470266 |
| Viewer's Choice | 2085823882 |
| Lifetime Achievement | 1517009682 |
| Hall of Fame | 1711796058 |
| Parade Info | 1867154294 |

Column mapping was derived from the original `app.js` used by the Google Sheets frontend.

---

## Era Boundaries

| Era | Years |
|-----|-------|
| Pre-modern | before 1991 |
| Modern | 1991–2013 |
| Contemporary | 2014–present |

Boundaries confirmed from the Mummers website source code — **1991 and 2014 are facts from the source, not editorial opinion**.

---

## Architecture Decisions

### DuckDB over PostgreSQL

DuckDB was chosen as the primary analytical store. The dataset is static-ish (one parade per year), query patterns are analytical (aggregations, era comparisons), and the LXC is single-purpose. DuckDB's file-based model eliminates a server process, simplifies backup (copy one file), and is trivially regenerable from source. PostgreSQL would add operational overhead with no benefit at this data scale.

### Datasette for Data Review

Datasette provides a zero-config web UI for browsing and querying the data. Because Datasette's native DuckDB adapter has limitations, the pipeline exports a SQLite snapshot (`datasette.db`) that Datasette serves. DuckDB remains the source of truth; SQLite is a read-only presentation layer.

### Claude API for LLM Layer (Phase 2)

The query interface in LXC 125 will use the Claude API with a thinking window for Text-to-SQL translation and a chat UI. Phase 1 does not include the LLM layer.

---

## LXC 124 — What It Runs

| Property | Value |
|----------|-------|
| Proxmox host | ARTEMIS (192.168.1.99) |
| CTID | 124 |
| IP | 192.168.1.72 |
| URL | http://mummster.theronlab.home/ |
| Cores | 2 vCPU |
| RAM | 4 GB |
| Disk | 32 GB |

**Services running on LXC 124:**

- `mummster-datasette` — Datasette web UI on port 8001, proxied via NPM
- `mummster-pipeline.timer` — daily systemd timer for the full pipeline

**File paths:**

- DuckDB: `/opt/mummster/data/mummster.db`
- SQLite (Datasette): `/opt/mummster/data/datasette.db`
- PDFs: `/opt/mummster/data/pdfs/`
- Pipeline: `/opt/mummster/pipeline/`
- Logs: `/mnt/artemis-data/logs/mummster/`

---

## Pipeline

The pipeline runs daily via `mummster-pipeline.timer` and can be triggered manually via the broker:

```
broker run-mummster-pipeline
```

**What it does:**

1. Pulls all 6 Google Sheets tabs via the Sheets API
2. Downloads PDFs from Google Drive links embedded in the sheet
3. Extracts text — native `pdftotext` where possible, Tesseract OCR for scanned images
4. Normalizes and loads all records into DuckDB with `data_source` and `completeness_flag` columns
5. Exports a SQLite snapshot to `datasette.db` for Datasette serving

The pipeline is idempotent — safe to re-run. DuckDB can be fully regenerated from source.

---

## OCR Results

| Method | Count | Confidence |
|--------|-------|------------|
| `pdftotext` (native text layer) | 57 | 1.00 |
| Tesseract (scanned image) | 2 | 0.57 and 0.85 |

57 of 59 PDFs had embedded text and were extracted cleanly. 2 are scanned images processed by Tesseract. The lower-confidence PDF (0.57) needs manual review — the OCR output may have errors in numeric fields.

---

## Known Open Items

| Item | Notes |
|------|-------|
| OCR structured parsing | Raw OCR text is in DuckDB; parsing into judge/category scores not yet done |
| Judge scores | Point sheets contain per-judge breakdowns — not yet modeled in schema |
| Manual gap year entry | 1964, 1967, 1999, 2001 need data sourced and entered manually |
| Low-confidence PDF review | Tesseract 0.57 PDF needs human verification |
| Statistical layer | Era comparisons, band rankings, trend analysis — not yet built |
| Monte Carlo simulation | Planned for competitive scenario modeling |
| Public frontend | Phase 1 is internal only; public UI is a future phase |

---

## Next Session — LXC 125

LXC 125 is the query interface layer:

- Text-to-SQL translation using Claude API with a thinking window
- Chat UI for natural language queries against the MummSTER database
- Designed to sit alongside LXC 124 — reads from the same data store
- Claude API integration, not local model
