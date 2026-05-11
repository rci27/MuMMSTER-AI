#!/usr/bin/env python3
"""
Mummster data pipeline — main entry point.

Orchestration order:
  1. Fetch all Google Sheet tabs via gviz CSV
  2. Download PDFs from Drive links found in the sheet
  3. OCR any PDFs not yet processed
  4. Write everything to DuckDB

Run manually:   python3 /opt/mummster/pipeline/sync.py
Run via systemd: ExecStart=/usr/bin/python3 /opt/mummster/pipeline/sync.py
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import db
import drive
import ocr
import parse_scores
import sheets
import vision_extract

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_FILE = Path(os.environ.get("MUMMSTER_CONFIG", "/opt/mummster/config.env"))

# If present, xlsx import runs as an optional pre-step before the sheet fetch.
XLSX_IMPORT_PATH = Path("/opt/mummster/data/imports/sbdb.xlsx")

LOG_DIR = Path("/mnt/artemis-data/logs/mummster")
LOG_FILE = LOG_DIR / "pipeline.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] [mummster-pipeline] %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"


def _load_config(path: Path) -> dict[str, str]:
    """Parse a dotenv-style key=value file. Lines starting with # are ignored."""
    config: dict[str, str] = {}
    if not path.exists():
        return config
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        config[key.strip()] = val.strip()
    # Environment variables override the file
    for key in list(config):
        if key in os.environ:
            config[key] = os.environ[key]
    return config


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("mummster")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATEFMT)
    formatter.converter = time.gmtime  # force UTC in timestamps

    # Always log to stdout (captured by systemd journal)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # Try to write to the log file on the NAS mount
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("Cannot write to log file %s (%s) — stdout only", LOG_FILE, exc)

    return logger


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(config: dict[str, str], log: logging.Logger) -> dict:
    start_ts = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("Pipeline START  %s", start_ts.isoformat())

    sheet_id  = config["SHEET_ID"]
    db_path   = Path(config["DB_PATH"])
    pdf_dir   = Path(config["PDF_DIR"])

    tab_gids = {
        "main_results":       config["GID_MAIN_RESULTS"],
        "custards_last_stand": config["GID_CUSTARDS_LAST_STAND"],
        "viewers_choice":     config["GID_VIEWERS_CHOICE"],
        "lifetime_achievement": config["GID_LIFETIME_ACHIEVEMENT"],
        "hall_of_fame":       config["GID_HALL_OF_FAME"],
        "parade_info":        config["GID_PARADE_INFO"],
    }

    backup_dir = Path(config.get("BACKUP_DIR", str(db_path.parent / "backups")))

    stats: dict = {
        "started_at": start_ts.isoformat(),
        "sheet_rows": {},
        "xlsx_import": {},
        "pdfs_downloaded": 0,
        "pdfs_ocrd": 0,
        "parsed_records": 0,
        "vision_records": 0,
        "vision_cost_usd": 0.0,
        "backup_path": None,
        "errors": [],
    }

    # ------------------------------------------------------------------
    # Pre-step: Backup the database before any writes occur
    # ------------------------------------------------------------------
    backup = db.backup_db(db_path, backup_dir)
    if backup:
        stats["backup_path"] = str(backup)
        log.info("Pre-run backup: %s", backup.name)
    else:
        log.info("Pre-run backup: no existing DB to back up")

    conn = db.init_db(db_path)

    # ------------------------------------------------------------------
    # Optional pre-step: Import from Excel if sbdb.xlsx is present
    # ------------------------------------------------------------------
    if XLSX_IMPORT_PATH.exists():
        log.info("--- xlsx import: %s found — running import_sbdb", XLSX_IMPORT_PATH)
        try:
            import import_sbdb
            sqlite_path_str = config.get("SQLITE_PATH")
            xlsx_counts = import_sbdb.run_import(
                xlsx_path=XLSX_IMPORT_PATH,
                db_path=db_path,
                sqlite_path=Path(sqlite_path_str) if sqlite_path_str else import_sbdb.SQLITE_PATH,
            )
            stats["xlsx_import"] = xlsx_counts
            log.info("xlsx import complete: %d tables", len(xlsx_counts))
        except Exception as exc:
            msg = f"xlsx import failed: {exc}"
            log.error(msg)
            stats["errors"].append(msg)
    else:
        log.debug("xlsx import: %s not found — skipping", XLSX_IMPORT_PATH)

    # ------------------------------------------------------------------
    # Step 1: Fetch sheet tabs
    # ------------------------------------------------------------------
    log.info("--- Step 1/6: Fetching sheet tabs")
    try:
        tab_frames = sheets.fetch_all(sheet_id, tab_gids)
    except Exception as exc:
        msg = f"Sheet fetch failed: {exc}"
        log.error(msg)
        stats["errors"].append(msg)
        conn.close()
        _log_summary(log, stats, start_ts)
        return stats

    # ------------------------------------------------------------------
    # Step 2: Write sheet data to DuckDB
    # ------------------------------------------------------------------
    log.info("--- Step 2/6: Writing sheet data to DuckDB")
    try:
        counts = db.write_sheet_tabs(conn, tab_frames)
        stats["sheet_rows"] = counts
    except Exception as exc:
        msg = f"DB write (sheets) failed: {exc}"
        log.error(msg)
        stats["errors"].append(msg)

    # If xlsx import ran, purge any legacy tables that the sheet write may have
    # recreated (main_results, hall_of_fame, etc. are superseded by sbdb_*).
    if stats.get("xlsx_import"):
        db.purge_legacy_tables(conn)
        log.info("Legacy tables purged (xlsx import is active source of truth)")

    # ------------------------------------------------------------------
    # Step 3: Download PDFs from Drive links in the sheet
    # ------------------------------------------------------------------
    log.info("--- Step 3/6: Downloading PDFs")
    try:
        # Look for Drive URLs across all fetched tabs
        pdf_col = config.get("PDF_LINK_COLUMN", "").strip()
        url_cols = [pdf_col] if pdf_col else None
        all_urls: list[tuple[str, str]] = []
        for name, df in tab_frames.items():
            found = drive.find_drive_urls(df, url_cols=url_cols)
            if found:
                log.info("  Tab %r: %d Drive URL(s) found", name, len(found))
                all_urls.extend(found)

        # Deduplicate by filename (file ID)
        seen: set[str] = set()
        deduped = []
        for url, fname in all_urls:
            if fname not in seen:
                seen.add(fname)
                deduped.append((url, fname))

        expected = int(config.get("PDF_COUNT_EXPECTED", 0))
        log.info("Unique Drive URLs: %d (expected %d)", len(deduped), expected)

        downloaded_paths = drive.download_all(deduped, pdf_dir)
        stats["pdfs_downloaded"] = len(downloaded_paths)
    except Exception as exc:
        msg = f"PDF download failed: {exc}"
        log.error(msg)
        stats["errors"].append(msg)
        downloaded_paths = []

    # ------------------------------------------------------------------
    # Step 4: OCR new PDFs, write results to DuckDB
    # ------------------------------------------------------------------
    log.info("--- Step 4/6: OCR processing")
    try:
        # Load Tesseract reprocess queue — files flagged by parse quality gate
        reprocess_file = Path("/opt/mummster/pipeline/tesseract_reprocess.txt")
        force_tesseract: set[str] = set()
        if reprocess_file.exists():
            force_tesseract = {
                l.strip() for l in reprocess_file.read_text().splitlines() if l.strip()
            }
            if force_tesseract:
                log.info("Tesseract reprocess queue: %d file(s) — %s",
                         len(force_tesseract), sorted(force_tesseract))

        # Collect all PDFs in the directory (including any pre-existing ones)
        all_pdfs = sorted(pdf_dir.glob("*.pdf"))
        already_done = db.already_ocr_done(conn)
        ocr_results = ocr.process_all(all_pdfs, already_done,
                                      force_tesseract=force_tesseract)
        inserted = db.write_ocr_results(conn, ocr_results,
                                        overwrite_filenames=force_tesseract)
        stats["pdfs_ocrd"] = inserted

        # Clear the reprocess queue after successful processing
        if force_tesseract and reprocess_file.exists():
            reprocess_file.unlink()
            log.info("Tesseract reprocess queue cleared")
    except Exception as exc:
        msg = f"OCR step failed: {exc}"
        log.error(msg)
        stats["errors"].append(msg)

    # ------------------------------------------------------------------
    # Step 5: Parse structured scores from OCR text into parsed_scores
    # ------------------------------------------------------------------
    log.info("--- Step 5/6: Parsing structured scores")
    try:
        parse_stats = parse_scores.run_parse(conn, db_path, backup_dir)
        stats["parsed_records"] = parse_stats.get("records_written", 0)
        if parse_stats.get("errors"):
            for e in parse_stats["errors"]:
                log.warning("  parse error: %s", e)
                stats["errors"].append(e)
    except Exception as exc:
        msg = f"Score parse step failed: {exc}"
        log.error(msg)
        stats["errors"].append(msg)

    # ------------------------------------------------------------------
    # Step 6/6: Vision AI extraction for years below confidence threshold
    # ------------------------------------------------------------------
    log.info("--- Step 6/6: Vision AI extraction")
    try:
        vision_stats = vision_extract.run_vision_extract(
            conn=conn,
            pdf_dir=pdf_dir,
            api_key_path=config.get(
                "ANTHROPIC_KEY_PATH", vision_extract.ANTHROPIC_KEY_PATH_DEFAULT
            ),
            cost_limit=float(config.get(
                "VISION_COST_LIMIT_USD", str(vision_extract.COST_GUARD_LIMIT_USD)
            )),
            force_vision=config.get("FORCE_VISION", "").lower() in ("true", "1", "yes"),
        )
        stats["vision_records"]  = vision_stats.get("records_written", 0)
        stats["vision_cost_usd"] = vision_stats.get("estimated_cost_usd", 0.0)
        if vision_stats.get("errors"):
            for e in vision_stats["errors"]:
                log.warning("  vision error: %s", e)
                stats["errors"].append(e)
    except Exception as exc:
        msg = f"Vision extraction step failed: {exc}"
        log.error(msg)
        stats["errors"].append(msg)

    db_stats = db.get_stats(conn)
    conn.close()

    # Export DuckDB → SQLite so Datasette always serves current data
    sqlite_path_str = config.get("SQLITE_PATH")
    if sqlite_path_str:
        try:
            db.export_to_sqlite(db_path, Path(sqlite_path_str))
        except Exception as exc:
            msg = f"SQLite export failed: {exc}"
            log.error(msg)
            stats["errors"].append(msg)

    # Generate data context summary for the query interface system prompt
    _run_context_generator(db_path, log)

    _log_summary(log, stats, start_ts, db_stats)
    return stats


def _run_context_generator(db_path: Path, log: logging.Logger) -> None:
    gen_ctx = Path("/opt/mummster/pipeline/generate_context.py")
    if not gen_ctx.exists():
        log.debug("generate_context.py not present — skipping context generation")
        return
    log.info("--- Generating data context summary")
    try:
        result = subprocess.run(
            [sys.executable, str(gen_ctx), str(db_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log.info("Data context generated: %s", result.stdout.strip())
        else:
            log.warning(
                "Data context generation failed (exit %d): %s",
                result.returncode,
                (result.stderr or result.stdout)[:300],
            )
    except Exception as exc:
        log.warning("Could not run generate_context.py: %s", exc)


def _log_summary(log: logging.Logger, stats: dict,
                 start_ts: datetime, db_stats: dict | None = None) -> None:
    elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
    log.info("=" * 60)
    log.info("Pipeline COMPLETE  elapsed=%.1fs", elapsed)
    for tab, count in stats.get("sheet_rows", {}).items():
        log.info("  %-32s %d rows", tab, count)
    xlsx = stats.get("xlsx_import", {})
    if xlsx:
        log.info("  xlsx import:      %d tables", len(xlsx))
        for t, n in sorted(xlsx.items()):
            log.info("    %-34s %d rows", t, n)
    log.info("  Backup:           %s", stats.get("backup_path") or "none")
    log.info("  PDFs downloaded:  %d", stats.get("pdfs_downloaded", 0))
    log.info("  PDFs OCR'd:       %d", stats.get("pdfs_ocrd", 0))
    log.info("  Scores parsed:    %d", stats.get("parsed_records", 0))
    log.info("  Vision records:   %d  (est. cost $%.4f)",
             stats.get("vision_records", 0), stats.get("vision_cost_usd", 0.0))
    if db_stats:
        for table, count in db_stats.get("tables", {}).items():
            log.info("  DB %-28s %d rows", table, count)
    if stats.get("errors"):
        log.warning("  Errors (%d):", len(stats["errors"]))
        for err in stats["errors"]:
            log.warning("    - %s", err)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    log = _setup_logging()
    config = _load_config(CONFIG_FILE)

    required_keys = [
        "SHEET_ID", "GID_MAIN_RESULTS", "GID_CUSTARDS_LAST_STAND",
        "GID_VIEWERS_CHOICE", "GID_LIFETIME_ACHIEVEMENT",
        "GID_HALL_OF_FAME", "GID_PARADE_INFO",
        "DB_PATH", "PDF_DIR",
    ]
    missing = [k for k in required_keys if not config.get(k)]
    if missing:
        log.error("Missing required config keys: %s", ", ".join(missing))
        log.error("Config file: %s", CONFIG_FILE)
        sys.exit(1)

    try:
        stats = run_pipeline(config, log)
        sys.exit(1 if stats.get("errors") else 0)
    except KeyboardInterrupt:
        log.info("Pipeline interrupted by user")
        sys.exit(130)
    except Exception as exc:
        log.exception("Unhandled exception in pipeline: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
