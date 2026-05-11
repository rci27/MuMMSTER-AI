#!/usr/bin/env python3
"""
Import sbdb.xlsx into DuckDB and export sbdb_* tables to datasette.db.

Designed to run inside LXC 124 at /opt/mummster/pipeline/import_sbdb.py.
Source xlsx is pushed there by the broker action import-sbdb-data:
  ARTEMIS host: /mnt/artemis-data/mummster/imports/sbdb.xlsx
  CT 124 path:  /opt/mummster/data/imports/sbdb.xlsx  (default XLSX_PATH)

Idempotent: drops all existing sbdb_* tables on each run, then rewrites from
the xlsx. Does not touch parsed_scores, parsed_scores_summary, ocr_results,
or any curation tables.

Can be called from sync.py as a module:
    import import_sbdb
    counts = import_sbdb.run_import(xlsx_path=..., db_path=..., sqlite_path=...)

Or run standalone:
    python3 /opt/mummster/pipeline/import_sbdb.py
"""

import logging
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

try:
    import db as _db_module
except ImportError:
    _db_module = None

log = logging.getLogger("mummster.import_sbdb")

XLSX_PATH   = Path("/opt/mummster/data/imports/sbdb.xlsx")
DB_PATH     = Path("/opt/mummster/data/mummster.db")
SQLITE_PATH = Path("/opt/mummster/data/datasette.db")

# Exact tab names in the xlsx → DuckDB table names.
# Tabs not listed here are skipped:
#   "upcoming"                   — not needed
#   "winners"                    — derivable: WHERE Place = 1 on sbdb_main_results
#   "1st Prize Point Difference" — derivable via self-join Place=1 vs Place=2 by year
TAB_MAP: dict[str, str] = {
    "main":                        "sbdb_main_results",
    "captains":                    "sbdb_captains",
    "concepts":                    "sbdb_concepts",
    "point sheets":                "sbdb_point_sheets",
    "custards last stand winners": "sbdb_custards_last_stand",
    "viewers choice":              "sbdb_viewers_choice",
    "hall of fame inductees":      "sbdb_hall_of_fame",
    "achievement award winners":   "sbdb_lifetime_achievement",
    "presidents award":            "sbdb_presidents_award",
    "award of distinction":        "sbdb_award_of_distinction",
    "officer of the year":         "sbdb_officer_of_the_year",
    "parade info":                 "sbdb_parade_info",
}

STATUS_CODES = [
    "dq", "wd", "no-covid", "nc",
    "bd-j", "no-j", "np-j", "bs-j", "sp-j", "gp",
]


def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse whitespace (including embedded newlines) in column headers.
    Also coerces non-string headers (int, float) to str."""
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


def _drop_sbdb_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop all sbdb_* tables for a clean full replacement."""
    tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
    for table in tables:
        if table.startswith("sbdb_"):
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            log.info("Dropped: %s", table)


def _create_status_codes(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Create sbdb_status_codes and seed with known codes.
    Idempotent: existing definitions are preserved on re-run.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sbdb_status_codes (
            code        TEXT PRIMARY KEY,
            definition  TEXT
        )
    """)
    for code in STATUS_CODES:
        conn.execute(
            "INSERT INTO sbdb_status_codes (code, definition) VALUES (?, '') "
            "ON CONFLICT (code) DO NOTHING",
            [code],
        )
    log.info("sbdb_status_codes ready  (%d codes)", len(STATUS_CODES))


def _export_to_sqlite(conn: duckdb.DuckDBPyConnection, sqlite_path: Path) -> None:
    """
    Export all sbdb_* tables to SQLite (replaces each table in-place).
    Other tables in datasette.db (parsed_scores, ocr_results, etc.) are untouched.
    """
    tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
    sbdb_tables = sorted(t for t in tables if t.startswith("sbdb_"))

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    try:
        for table in sbdb_tables:
            df = conn.execute(f'SELECT * FROM "{table}"').df()
            df.to_sql(table, sqlite_conn, if_exists="replace", index=False)
            log.info("Exported → SQLite: %-32s  %d rows", table, len(df))
        sqlite_conn.commit()
        log.info("SQLite export complete: %s", sqlite_path)
    finally:
        sqlite_conn.close()


def run_import(
    xlsx_path: Path = XLSX_PATH,
    db_path: Path = DB_PATH,
    sqlite_path: Path = SQLITE_PATH,
) -> dict[str, int]:
    """
    Full import: drop sbdb_* tables, reload from xlsx, create status codes,
    export to SQLite, regenerate data_context.md.
    Returns {table_name: row_count}.
    """
    if not xlsx_path.exists():
        raise FileNotFoundError(f"xlsx not found: {xlsx_path}")

    log.info("Opening xlsx: %s", xlsx_path)
    xl = pd.ExcelFile(str(xlsx_path), engine="openpyxl")
    available = {s.lower(): s for s in xl.sheet_names}
    log.info("Tabs found: %s", list(xl.sheet_names))

    conn = duckdb.connect(str(db_path))
    try:
        _drop_sbdb_tables(conn)

        counts: dict[str, int] = {}
        for tab_name, table_name in TAB_MAP.items():
            actual = available.get(tab_name.lower())
            if actual is None:
                log.warning("Tab %r not found in xlsx — skipping", tab_name)
                continue

            df = pd.read_excel(str(xlsx_path), sheet_name=actual, dtype=str, engine="openpyxl")
            df.dropna(how="all", inplace=True)
            # Column names may be float(NaN) for empty headers — cast to str before filtering
            df = df.loc[:, ~df.columns.astype(str).str.match(r"^(Unnamed|nan)")]
            df = _normalize_headers(df)

            if df.empty:
                log.warning("Tab %r is empty after cleaning — skipping", tab_name)
                continue

            conn.register("_incoming", df)
            conn.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM _incoming')
            conn.unregister("_incoming")

            count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            counts[table_name] = count
            log.info(
                "Imported  %-32s  %4d rows  %d cols  (tab: %r)",
                table_name, count, len(df.columns), tab_name,
            )

        _create_status_codes(conn)
        counts["sbdb_status_codes"] = len(STATUS_CODES)

        _export_to_sqlite(conn, sqlite_path)

        # Purge legacy tables now that all sbdb_ tables are confirmed present
        if counts.get("sbdb_main_results", 0) > 0 and _db_module is not None:
            _db_module.purge_legacy_tables(conn)
        elif counts.get("sbdb_main_results", 0) > 0:
            log.warning("db module not available — skipping legacy table purge")
    finally:
        conn.close()

    _run_context_generator(db_path)
    return counts


def _run_context_generator(db_path: Path) -> None:
    gen_ctx = Path("/opt/mummster/pipeline/generate_context.py")
    if not gen_ctx.exists():
        log.debug("generate_context.py not found — skipping")
        return
    try:
        result = subprocess.run(
            [sys.executable, str(gen_ctx), str(db_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log.info("data_context.md updated: %s", result.stdout.strip())
        else:
            log.warning(
                "generate_context failed (exit %d): %s",
                result.returncode,
                (result.stderr or result.stdout)[:300],
            )
    except Exception as exc:
        log.warning("Could not run generate_context.py: %s", exc)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [import_sbdb] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    _setup_logging()
    xlsx_arg   = Path(sys.argv[1]) if len(sys.argv) > 1 else XLSX_PATH
    db_arg     = Path(sys.argv[2]) if len(sys.argv) > 2 else DB_PATH
    sqlite_arg = Path(sys.argv[3]) if len(sys.argv) > 3 else SQLITE_PATH

    try:
        counts = run_import(xlsx_path=xlsx_arg, db_path=db_arg, sqlite_path=sqlite_arg)
        print("\nImport summary:")
        for table, count in sorted(counts.items()):
            print(f"  {table:<36} {count:>5} rows")
        sys.exit(0)
    except Exception as exc:
        log.error("Import failed: %s", exc)
        sys.exit(1)
