"""
DuckDB schema and write operations for the Mummster data foundation.
Every table written by this module includes data_source and completeness_flag.
Sheet tables with a detectable year column also include an era column.
"""

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger("mummster.db")

ERA_MODERN_START = 1991       # confirmed from site source code
ERA_CONTEMPORARY_START = 2014  # confirmed from site source code

# Column names (any case) that are treated as "year" for era derivation
_YEAR_COLUMN_ALIASES = {"year", "season", "yr"}

# Fraction of non-null/non-empty columns needed for each completeness tier
_COMPLETE_THRESHOLD = 0.75
_PARTIAL_THRESHOLD = 0.25

# DuckDB table for OCR results
OCR_TABLE = "ocr_results"

# Legacy sheet tables superseded by sbdb_* equivalents
_PURGE_LEGACY_TABLES = [
    "main_results",
    "hall_of_fame",
    "custards_last_stand",
    "viewers_choice",
    "lifetime_achievement",
    "parade_info",
]


def get_era(year) -> str | None:
    """Map a year value to an era string. Returns None if year is not parseable."""
    try:
        y = int(float(str(year).strip()))
    except (ValueError, TypeError):
        return None
    if y < ERA_MODERN_START:
        return "pre-modern"
    if y < ERA_CONTEMPORARY_START:
        return "modern"
    return "contemporary"


def _find_year_column(df: pd.DataFrame) -> str | None:
    """Return the first column whose name matches a known year alias, or None."""
    for col in df.columns:
        if col.strip().lower() in _YEAR_COLUMN_ALIASES:
            return col
    return None


def _completeness(row: pd.Series) -> str:
    """Compute completeness_flag for a row based on non-empty field ratio."""
    total = len(row)
    if total == 0:
        return "missing"
    filled = sum(
        1 for v in row
        if v is not None and str(v).strip() not in ("", "nan", "N/A", "n/a", "None")
    )
    ratio = filled / total
    if ratio >= _COMPLETE_THRESHOLD:
        return "complete"
    if ratio >= _PARTIAL_THRESHOLD:
        return "partial"
    return "missing"


def _enrich(df: pd.DataFrame, data_source: str) -> pd.DataFrame:
    """
    Add required fields to a DataFrame in-place.
    - data_source: constant string for this batch
    - completeness_flag: per-row heuristic
    - era: derived from year column if present
    - _synced_at: UTC timestamp
    """
    df = df.copy()

    # Skip meta-columns when computing completeness
    meta_cols = {"data_source", "completeness_flag", "era", "_synced_at"}
    data_cols = [c for c in df.columns if c not in meta_cols]

    df["data_source"] = data_source
    df["completeness_flag"] = df[data_cols].apply(_completeness, axis=1)

    year_col = _find_year_column(df)
    if year_col:
        df["era"] = df[year_col].apply(get_era)
    else:
        df["era"] = None

    df["_synced_at"] = datetime.now(timezone.utc).isoformat()
    return df


_BACKUP_RETENTION = 10  # keep last N timestamped backups


def backup_db(db_path: Path, backup_dir: Path) -> Path | None:
    """
    Create a timestamped copy of mummster.db in backup_dir before any writes.
    Enforces retention: deletes oldest backups beyond _BACKUP_RETENTION.
    Returns backup path, or None if the DB doesn't exist yet or on error.
    Call this at the very start of run_pipeline, before any table writes.
    """
    if not db_path.exists():
        log.info("backup_db: no DB at %s yet — skipping", db_path)
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"mummster_{ts}.db"

    try:
        shutil.copy2(str(db_path), str(dest))
        size_kb = dest.stat().st_size // 1024
        log.info("Backup created: %s  (%d KB)", dest.name, size_kb)
    except OSError as exc:
        log.error("Backup failed: %s", exc)
        return None

    existing = sorted(backup_dir.glob("mummster_*.db"))
    to_delete = existing[:-_BACKUP_RETENTION] if len(existing) > _BACKUP_RETENTION else []
    for old in to_delete:
        try:
            old.unlink()
            log.info("Backup deleted (retention): %s", old.name)
        except OSError as exc:
            log.warning("Could not delete backup %s: %s", old.name, exc)

    return dest


def init_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB database and ensure base tables exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {OCR_TABLE} (
            filename        TEXT,
            pdf_path        TEXT,
            text            TEXT,
            method          TEXT,
            confidence      DOUBLE,
            page_count      INTEGER,
            processed_at    TEXT,
            data_source     TEXT,
            completeness_flag TEXT,
            error           TEXT
        )
    """)

    log.debug("Database opened: %s", db_path)
    return conn


def write_sheet_tab(conn: duckdb.DuckDBPyConnection,
                    table_name: str,
                    df: pd.DataFrame,
                    data_source: str) -> int:
    """
    Write a sheet tab DataFrame to DuckDB.
    Replaces the table entirely on each sync (full refresh — idempotent).
    Returns number of rows written.
    """
    if df.empty:
        log.warning("Tab %r is empty — skipping", table_name)
        return 0

    enriched = _enrich(df, data_source)
    conn.register("_incoming", enriched)
    conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _incoming")
    conn.unregister("_incoming")

    row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    log.info("Table %-30s  %d rows written", f'"{table_name}"', row_count)
    return row_count


def write_sheet_tabs(conn: duckdb.DuckDBPyConnection,
                     tabs: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Write all sheet tabs. Returns {table_name: row_count}."""
    counts: dict[str, int] = {}
    for name, df in tabs.items():
        counts[name] = write_sheet_tab(conn, name, df, data_source=name)
    return counts


def purge_legacy_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Drop legacy sheet tables that have been fully replaced by sbdb_* equivalents.
    Safe to call repeatedly (IF EXISTS). Call only after confirming sbdb_ tables
    are present and populated.
    """
    for table in _PURGE_LEGACY_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        log.info("Purged legacy table (if existed): %s", table)


def already_ocr_done(conn: duckdb.DuckDBPyConnection) -> set[str]:
    """Return filenames already present in the OCR results table."""
    rows = conn.execute(f"SELECT DISTINCT filename FROM {OCR_TABLE}").fetchall()
    return {r[0] for r in rows}


def write_ocr_results(conn: duckdb.DuckDBPyConnection,
                      results: list[dict],
                      overwrite_filenames: set[str] | None = None) -> int:
    """
    Insert new OCR results. Skips rows whose filename is already present,
    unless the filename is in overwrite_filenames — those are deleted first
    and replaced with the new Tesseract result.
    Returns number of rows inserted.
    """
    if not results:
        return 0

    overwrite = overwrite_filenames or set()

    # Delete existing records for force-reprocessed files before re-inserting
    for fname in overwrite:
        conn.execute(f"DELETE FROM {OCR_TABLE} WHERE filename = ?", [fname])
        log.info("Deleted existing OCR record for force-reprocess: %s", fname)

    now = datetime.now(timezone.utc).isoformat()
    done = already_ocr_done(conn)
    new_results = [r for r in results if r["filename"] not in done]

    if not new_results:
        log.info("No new OCR results to insert")
        return 0

    rows = []
    for r in new_results:
        text = r.get("text", "") or ""
        completeness = (
            "complete" if text and not r.get("error")
            else "partial" if text
            else "missing"
        )
        rows.append({
            "filename":          r["filename"],
            "pdf_path":          r["path"],
            "text":              text,
            "method":            r.get("method"),
            "confidence":        r.get("confidence", 0.0),
            "page_count":        r.get("page_count", 0),
            "processed_at":      now,
            "data_source":       "pdf-ocr",
            "completeness_flag": completeness,
            "error":             r.get("error"),
        })

    df = pd.DataFrame(rows)
    conn.register("_ocr_incoming", df)
    conn.execute(f"INSERT INTO {OCR_TABLE} SELECT * FROM _ocr_incoming")
    conn.unregister("_ocr_incoming")

    log.info("Inserted %d new OCR result(s) into %s", len(rows), OCR_TABLE)
    return len(rows)


def export_to_sqlite(duckdb_path: Path, sqlite_path: Path) -> None:
    """
    Export all DuckDB tables to a SQLite file for Datasette.
    Called at the end of each pipeline run so Datasette always serves fresh data.
    """
    import sqlite3
    conn = duckdb.connect(str(duckdb_path), read_only=True)
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    try:
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        for table in tables:
            df = conn.execute(f"SELECT * FROM {table}").df()
            df.to_sql(table, sqlite_conn, if_exists="replace", index=False)
            log.info("Exported %-30s → SQLite  %d rows", table, len(df))
        sqlite_conn.commit()
        log.info("SQLite export complete: %s", sqlite_path)
    finally:
        sqlite_conn.close()
        conn.close()


def get_stats(conn: duckdb.DuckDBPyConnection) -> dict:
    """Return a summary of what's in the database."""
    tables = [
        r[0] for r in
        conn.execute("SHOW TABLES").fetchall()
    ]
    stats: dict = {"tables": {}}
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats["tables"][table] = count
    return stats
