# mummster-pipeline (LXC 124)

The data ingestion and processing pipeline. Pulls from Google Sheets, downloads PDFs, runs OCR + Claude Vision extraction, imports the canonical Excel workbook, exports to SQLite for Datasette.

See [`docs/CODEBASE_OVERVIEW.md`](../../docs/CODEBASE_OVERVIEW.md) for a file-by-file walkthrough.

## Files

| File                  | Purpose                                              |
|-----------------------|------------------------------------------------------|
| `sync.py`             | Pipeline orchestrator — runs the full flow           |
| `sheets.py`           | Google Sheet fetcher (gviz CSV)                      |
| `drive.py`            | PDF downloader                                       |
| `ocr.py`              | pdftotext + Tesseract OCR                            |
| `parse_scores.py`     | Regex-based PDF text parser                          |
| `vision_extract.py`   | Claude Vision API extractor                          |
| `normalize.py`        | Field name normalization dictionary                  |
| `import_sbdb.py`      | Excel workbook importer                              |
| `db.py`               | Database layer + SQLite export                       |
| `generate_context.py` | data_context.md generator                            |
| `requirements.txt`    | Python dependencies                                  |

## Runtime

- Python 3.11
- DuckDB
- pdftotext (`poppler-utils`)
- Tesseract OCR
- Anthropic Python SDK for vision

## Trigger

Manual via broker: `run-mummster-pipeline`. Annual cadence after each year's parade, plus on-demand when corrections come in.

## Cost guard

The vision step aborts if estimated API cost exceeds **$2.00**. Override: `FORCE_VISION=true`.

## Data location

- Reads: Google Sheet, Google Drive PDFs, `/opt/mummster/imports/sbdb.xlsx`
- Writes: `/opt/mummster/data/mummster.db` (DuckDB), `/opt/mummster/data/datasette.db` (SQLite), `/opt/mummster/data/data_context.md`
