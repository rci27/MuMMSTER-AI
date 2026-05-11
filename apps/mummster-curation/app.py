"""
Mummster curation tool — FastAPI backend.
Multi-year, multi-page support, formula storage, year-complete workflow, CSV upload.
"""

import asyncio
import base64
import csv
import io
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ── Paths ─────────────────────────────────────────────────────────────────────

INSTALL_DIR   = Path("/opt/mummster-curation")
DATA_DIR      = INSTALL_DIR / "data"
STATIC_DIR    = INSTALL_DIR / "static"
PAGES_DIR     = DATA_DIR / "pages"
PDF_DIR       = DATA_DIR / "pdfs"
DB_PATH       = DATA_DIR / "curation.db"
COMPLETED_DIR = DATA_DIR / "completed"
ANTHROPIC_KEY = Path("/etc/artemis-secrets/anthropic.key")

MUMMSTER_DB_CANDIDATES = [
    Path("/opt/mummster/data/mummster.db"),
    Path("/opt/mummster-curation/data/mummster.db"),
]
MUMMSTER_DB = next((p for p in MUMMSTER_DB_CANDIDATES if p.exists()), None)

MODEL     = "claude-sonnet-4-6"
GAP_YEARS = {1964, 1967, 1999, 2001, 2021}

# ── LXC 124 (mummster pipeline) connectivity ──────────────────────────────────

LXC124_IP      = os.environ.get("LXC124_IP", "192.168.1.72")
LXC124_USER    = os.environ.get("LXC124_USER", "root")
LXC124_DB      = os.environ.get("LXC124_DB", "/opt/mummster/data/mummster.db")
LXC124_PDF_DIR = os.environ.get("LXC124_PDF_DIR", "/opt/mummster/data/pdfs")
SSH_KEY_PATH   = Path("/home/curator/.ssh/id_ed25519")
_CURATOR_HOME  = SSH_KEY_PATH.parent.parent  # /home/curator
SSH_OPTS = [
    "-T",  # no pseudo-tty
    "-i", str(SSH_KEY_PATH),
    "-o", f"UserKnownHostsFile={SSH_KEY_PATH.parent / 'known_hosts'}",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
    "-o", "BatchMode=yes",
]
# Ensure HOME is set so SSH resolves ~ paths correctly when running as a service
_SSH_ENV = {**os.environ, "HOME": str(_CURATOR_HOME)}

EXTRACT_PROMPT = """\
This image is ONE PAGE of a multi-page scoring sheet. Extract ONLY the main per-band scoring table visible on this page. Ignore any captains' prize lists, awards lists, footnotes, or supplemental sections. If a section is clearly NOT the main per-band scoring table (e.g. a ranked list of captain names, an awards roster, a footer note, a single-column prize list), do not extract entries from it. Return only bands that have a complete row of scores in the main table on this page. If this page contains no main scoring table, return an empty rows array.

Return JSON in this format: { "columns": ["Band", "col1_name", "col2_name", ...], "rows": [ {"band": "band name", "col1_name": value, "col2_name": value, ...}, ... ] }. Use the exact column label text as it appears even if abbreviated. Do not skip any columns or bands that appear in the main scoring table.\
"""

SUPPLEMENTAL_PROMPT_TEMPLATE = (
    "This image is page {page} of a multi-page scoring sheet (where page 1 contained the main "
    "band scoring table, already extracted separately). Extract whatever structured data appears "
    "on this page — could be a ranked list of captains, an awards roster, judge identities, "
    "footnotes, or any tabular content. Return JSON in the format "
    '{{"columns": [...], "rows": [{{"band": "...", "col1": ..., "col2": ...}}, ...]}}. '
    "The 'band' field can hold any primary identifier for each row — band name, captain name, "
    "award category, etc. — whatever makes sense for the content. If multiple distinct sections "
    "appear on this page, choose the most prominent structured one. If no structured data is "
    "present, return empty rows."
)

PAGES_DIR.mkdir(parents=True, exist_ok=True)
COMPLETED_DIR.mkdir(parents=True, exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Mummster Curation Tool")
app.mount("/pages", StaticFiles(directory=str(PAGES_DIR)), name="pages")


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    _convert_all_pdfs()
    _init_db()


def _get_year_pages_dir(year: int) -> Path:
    year_dir = PAGES_DIR / str(year)
    if year_dir.exists() and list(year_dir.glob("page_*.png")):
        return year_dir
    if list(PAGES_DIR.glob("page_*.png")):
        return PAGES_DIR
    return year_dir


def _convert_all_pdfs() -> None:
    if not PDF_DIR.exists():
        return
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        stem = pdf_path.stem
        if stem.isdigit():
            year = int(stem)
            out_dir = PAGES_DIR / str(year)
        else:
            year = 1977
            out_dir = PAGES_DIR
        existing = list(out_dir.glob("page_*.png"))
        if existing:
            print(f"Pages already converted for {year} ({len(existing)} images)")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(str(pdf_path), dpi=150)
            for i, img in enumerate(images, 1):
                img.save(str(out_dir / f"page_{i:03d}.png"), "PNG")
            print(f"Converted {len(images)} pages from {pdf_path.name} → {out_dir}")
        except Exception as exc:
            print(f"PDF conversion failed for {pdf_path.name}: {exc}")


def _get_available_years() -> list[int]:
    years: set[int] = set()
    for d in PAGES_DIR.iterdir():
        if d.is_dir() and d.name.isdigit():
            y = int(d.name)
            if y not in GAP_YEARS and list(d.glob("page_*.png")):
                years.add(y)
    if list(PAGES_DIR.glob("page_*.png")):
        years.add(1977)
    if PDF_DIR.exists():
        for f in PDF_DIR.glob("*.pdf"):
            if f.stem.isdigit():
                y = int(f.stem)
                if y not in GAP_YEARS:
                    years.add(y)
    return sorted(years) if years else [1977]


def _get_bands(year: int) -> list[str]:
    if MUMMSTER_DB:
        try:
            conn = duckdb.connect(str(MUMMSTER_DB), read_only=True)
            rows = conn.execute(
                "SELECT DISTINCT Band FROM sbdb_main_results WHERE Year = ? ORDER BY Band",
                [str(year)],
            ).fetchall()
            conn.close()
            if rows:
                return [r[0] for r in rows if r[0]]
        except Exception:
            pass
    json_file = DATA_DIR / f"bands_{year}.json"
    if json_file.exists():
        try:
            return json.loads(json_file.read_text())
        except Exception:
            pass
    try:
        conn = duckdb.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT DISTINCT band FROM curated_scores_raw "
            "WHERE year = ? AND column_name = 'Band Name' AND page_number = 1 ORDER BY band",
            [year],
        ).fetchall()
        conn.close()
        if rows:
            return [r[0] for r in rows if r[0]]
    except Exception:
        pass
    return []


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS curated_scores_raw (
            year        INTEGER,
            band        TEXT,
            column_name TEXT,
            value       TEXT,
            page_number INTEGER DEFAULT 1,
            created_at  TEXT,
            updated_at  TEXT,
            col_order   INTEGER DEFAULT 0
        )
    """)
    for migration in [
        "ALTER TABLE curated_scores_raw ADD COLUMN col_order INTEGER DEFAULT 0",
        "ALTER TABLE curated_scores_raw ADD COLUMN formula TEXT",
        "ALTER TABLE curated_scores_raw ADD COLUMN page_number INTEGER DEFAULT 1",
    ]:
        try:
            conn.execute(migration)
        except Exception:
            pass
    try:
        conn.execute("UPDATE curated_scores_raw SET page_number = 1 WHERE page_number IS NULL")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS year_status (
            year             INTEGER PRIMARY KEY,
            status           TEXT NOT NULL DEFAULT 'in_progress',
            completed_at     TEXT,
            completed_csv_path TEXT
        )
    """)
    conn.close()
    COMPLETED_DIR.mkdir(parents=True, exist_ok=True)


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _build_csv_content(year: int) -> tuple[str, list[dict], int]:
    """Return (csv_string, page_summaries, total_cell_count).

    CSV columns: year, band, page_number, then a union of all data columns across
    all pages. Rows for a page that lacks a given column get a blank cell.
    """
    conn = duckdb.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT band, column_name, value, col_order, page_number FROM curated_scores_raw "
        "WHERE year = ? ORDER BY page_number, col_order, band",
        [year],
    ).fetchall()
    total_cells = conn.execute(
        "SELECT COUNT(*) FROM curated_scores_raw "
        "WHERE year = ? AND column_name != 'Band Name' AND value IS NOT NULL AND value != ''",
        [year],
    ).fetchone()[0]
    conn.close()

    # page_data[pnum] = {"col_order": {col: order}, "band_data": {band: {col: val}}}
    page_data: dict[int, dict] = {}
    for band, col, val, order, pnum in rows:
        if pnum is None:
            pnum = 1
        if pnum not in page_data:
            page_data[pnum] = {"col_order": {}, "band_data": defaultdict(dict)}
        if col != "Band Name" and col not in page_data[pnum]["col_order"]:
            page_data[pnum]["col_order"][col] = order
        if col != "Band Name":
            page_data[pnum]["band_data"][band][col] = val or ""

    # Union of all data columns, ordered by page then col_order within each page
    all_cols: list[str] = []
    col_seen: set[str] = set()
    for pnum in sorted(page_data.keys()):
        page_cols = sorted(
            page_data[pnum]["col_order"].keys(),
            key=lambda c: page_data[pnum]["col_order"][c],
        )
        for col in page_cols:
            if col not in col_seen:
                all_cols.append(col)
                col_seen.add(col)

    buf = io.StringIO()
    buf.write(",".join(f'"{c}"' for c in ["year", "band", "page_number"] + all_cols) + "\n")

    page_summaries: list[dict] = []
    for pnum in sorted(page_data.keys()):
        pd = page_data[pnum]
        page_cols_set = set(pd["col_order"].keys())
        for band in sorted(pd["band_data"].keys()):
            row_vals = [str(year), band, str(pnum)]
            for col in all_cols:
                row_vals.append(pd["band_data"][band].get(col, "") if col in page_cols_set else "")
            buf.write(",".join(f'"{v}"' for v in row_vals) + "\n")
        page_summaries.append({
            "page": pnum,
            "bands": len(pd["band_data"]),
            "cols": len(pd["col_order"]),
        })

    return buf.getvalue(), page_summaries, total_cells


def _get_year_status(year: int) -> str:
    try:
        conn = duckdb.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT status FROM year_status WHERE year = ?", [year]
        ).fetchone()
        conn.close()
        return row[0] if row else "in_progress"
    except Exception:
        return "in_progress"


# ── LXC 124 remote helpers ────────────────────────────────────────────────────

# Python script executed remotely on LXC 124 via SSH stdin.
# Queries mummster.db for year→file_id, verifies each PDF exists on disk,
# then prints tab-separated (year, filename) pairs.
_REMOTE_YEAR_MAP_SCRIPT = """\
import duckdb, re, os, sys

DB  = "/opt/mummster/data/mummster.db"
DIR = "/opt/mummster/data/pdfs"

try:
    conn = duckdb.connect(DB, read_only=True)
    rows = conn.execute(
        'SELECT DISTINCT "Year", "Point Sheet" FROM sbdb_main_results '
        'WHERE "Point Sheet" IS NOT NULL ORDER BY "Year"'
    ).fetchall()
    conn.close()
except Exception as e:
    print(f"DB_ERROR:{e}", file=sys.stderr)
    sys.exit(1)

for year_str, url in rows:
    m = re.search(r"id=([^&\\s]+)", url)
    if not m:
        continue
    fid = m.group(1).strip()
    if os.path.exists(os.path.join(DIR, fid + ".pdf")):
        print(f"{year_str}\\t{fid}.pdf")
"""


def _get_remote_year_map() -> tuple[dict[int, str], str | None]:
    """Return ({year_int: filename_on_lxc124}, error_or_none).

    Runs a Python script on LXC 124 via SSH stdin to avoid shell-quoting issues.
    """
    try:
        result = subprocess.run(
            ["ssh"] + SSH_OPTS + [f"{LXC124_USER}@{LXC124_IP}", "python3"],
            input=_REMOTE_YEAR_MAP_SCRIPT,
            capture_output=True, text=True, timeout=60,
            env=_SSH_ENV,
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            return {}, err or f"Remote query failed (exit {result.returncode})"
        year_map: dict[int, str] = {}
        for line in result.stdout.splitlines():
            parts = line.strip().split("\t")
            if len(parts) == 2:
                try:
                    year_map[int(parts[0])] = parts[1]
                except ValueError:
                    pass
        return year_map, None
    except subprocess.TimeoutExpired:
        return {}, f"Pipeline server ({LXC124_IP}) did not respond within 60s"
    except FileNotFoundError:
        return {}, "ssh not found — openssh-client not installed?"
    except Exception as exc:
        return {}, str(exc)


def _scp_pdf(remote_src: str, local_pdf: Path) -> str | None:
    """SCP a single file from LXC 124. Returns error string or None on success."""
    try:
        result = subprocess.run(
            ["scp", "-q"] + SSH_OPTS + [remote_src, str(local_pdf)],
            capture_output=True, text=True, timeout=180,
            env=_SSH_ENV,
        )
        if result.returncode != 0:
            return (result.stderr or "").strip() or f"scp exited {result.returncode}"
        return None
    except subprocess.TimeoutExpired:
        return "Transfer timed out (>180s)"
    except FileNotFoundError:
        return "scp not found — openssh-client not installed?"
    except Exception as exc:
        return str(exc)


def _convert_pdf_year(pdf_path: Path, out_dir: Path) -> tuple[int, str | None]:
    """Convert a PDF to per-page PNG images. Returns (page_count, error_or_none)."""
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(str(pdf_path), dpi=150)
        for i, img in enumerate(images, 1):
            img.save(str(out_dir / f"page_{i:03d}.png"), "PNG")
        return len(images), None
    except Exception as exc:
        return 0, str(exc)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text())


@app.get("/api/years")
def api_years() -> dict:
    return {"years": _get_available_years()}


@app.get("/api/year_statuses")
def api_year_statuses() -> dict:
    try:
        conn = duckdb.connect(str(DB_PATH))
        rows = conn.execute("SELECT year, status FROM year_status").fetchall()
        conn.close()
        return {"statuses": {r[0]: r[1] for r in rows}}
    except Exception:
        return {"statuses": {}}


@app.get("/api/info")
def api_info(year: int = 1977) -> dict:
    pages_dir = _get_year_pages_dir(year)
    pages     = sorted(pages_dir.glob("page_*.png"))
    bands     = _get_bands(year)
    status    = _get_year_status(year)

    try:
        rel     = pages_dir.relative_to(PAGES_DIR)
        rel_str = str(rel).replace("\\", "/")
        pages_url_prefix = rel_str + "/" if rel_str not in (".", "") else ""
    except ValueError:
        pages_url_prefix = ""

    try:
        conn = duckdb.connect(str(DB_PATH))
        page_rows = conn.execute(
            "SELECT page_number, COUNT(DISTINCT band) as bands, COUNT(DISTINCT column_name) as cols "
            "FROM curated_scores_raw WHERE year = ? AND column_name != 'Band Name' "
            "GROUP BY page_number ORDER BY page_number",
            [year],
        ).fetchall()
        total_cells = conn.execute(
            "SELECT COUNT(*) FROM curated_scores_raw "
            "WHERE year = ? AND column_name != 'Band Name' AND value IS NOT NULL AND value != ''",
            [year],
        ).fetchone()[0]
        conn.close()
        pages_with_data = [{"page": r[0], "bands": r[1], "cols": r[2]} for r in page_rows]
    except Exception:
        pages_with_data = []
        total_cells     = 0

    return {
        "year":              year,
        "page_count":        len(pages),
        "bands":             bands,
        "status":            status,
        "pages_url_prefix":  pages_url_prefix,
        "pages_with_data":   pages_with_data,
        "total_cells":       total_cells,
        "main_scoring_page": 1,
    }


@app.get("/api/data")
def api_data(year: int = 1977, page: int = 1) -> dict:
    conn = duckdb.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT band, column_name, value, col_order, formula FROM curated_scores_raw "
        "WHERE year = ? AND page_number = ? ORDER BY col_order, band, column_name",
        [year, page],
    ).fetchall()
    conn.close()

    columns:  list[str] = []
    col_seen: set[str]  = set()
    cells:    dict[str, str] = {}
    formulas: dict[str, str] = {}
    bands:    list[str] = []
    band_seen: set[str] = set()

    for band, col, val, _order, formula in rows:
        if band not in band_seen:
            band_seen.add(band)
            bands.append(band)
        if col != "Band Name" and col not in col_seen:
            columns.append(col)
            col_seen.add(col)
        cells[f"{band}|{col}"] = val or ""
        if formula:
            formulas[f"{band}|{col}"] = formula

    return {"columns": columns, "cells": cells, "formulas": formulas, "bands": bands}


@app.post("/api/data")
async def api_save(request: Request) -> dict:
    body        = await request.json()
    year        = int(body.get("year", 1977))
    columns     = body.get("columns", [])
    rows        = body.get("rows", [])
    page_number = int(body.get("page_number", 1))
    formulas    = body.get("formulas", {})
    now         = datetime.now(timezone.utc).isoformat()

    if _get_year_status(year) == "complete":
        return {"error": f"Year {year} is marked complete. Unlock first to save."}

    records: list[tuple] = []
    for row in rows:
        band = (row.get("Band Name") or "").strip()
        if not band:
            continue
        records.append((year, band, "Band Name", band, page_number, now, now, 0, None))
        for ci, col in enumerate(columns, 1):
            formula = formulas.get(f"{band}|{col}")
            records.append((year, band, col, row.get(col, ""), page_number, now, now, ci, formula))

    conn = duckdb.connect(str(DB_PATH))
    conn.execute(
        "DELETE FROM curated_scores_raw WHERE year = ? AND page_number = ?",
        [year, page_number],
    )
    if records:
        conn.executemany(
            "INSERT INTO curated_scores_raw "
            "(year, band, column_name, value, page_number, created_at, updated_at, col_order, formula) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            records,
        )
    conn.close()
    return {"status": "saved", "records": len(records)}


@app.post("/api/rename_column")
async def api_rename_column(request: Request) -> dict:
    body        = await request.json()
    year        = int(body.get("year", 1977))
    page_number = int(body.get("page", 1))
    old_name    = body.get("old_name", "").strip()
    new_name    = body.get("new_name", "").strip()

    if not old_name or not new_name:
        return {"status": "error", "message": "old_name and new_name required"}
    if new_name == "Band Name":
        return {"status": "error", "message": '"Band Name" is reserved'}
    if old_name == new_name:
        return {"status": "ok", "message": "no change"}
    if _get_year_status(year) == "complete":
        return {"status": "error", "message": f"Year {year} is marked complete. Unlock first."}

    now  = datetime.now(timezone.utc).isoformat()
    conn = duckdb.connect(str(DB_PATH))
    existing = conn.execute(
        "SELECT COUNT(*) FROM curated_scores_raw "
        "WHERE year = ? AND page_number = ? AND column_name = ?",
        [year, page_number, new_name],
    ).fetchone()[0]
    if existing:
        conn.close()
        return {"status": "error", "message": f'"{new_name}" already exists for {year} page {page_number}'}

    affected = conn.execute(
        "SELECT COUNT(*) FROM curated_scores_raw "
        "WHERE year = ? AND page_number = ? AND column_name = ?",
        [year, page_number, old_name],
    ).fetchone()[0]
    conn.execute(
        "UPDATE curated_scores_raw SET column_name = ?, updated_at = ? "
        "WHERE year = ? AND page_number = ? AND column_name = ?",
        [new_name, now, year, page_number, old_name],
    )
    conn.close()
    return {"status": "ok", "renamed": affected, "old": old_name, "new": new_name}


@app.post("/api/mark_year_complete")
async def api_mark_year_complete(request: Request) -> dict:
    body = await request.json()
    year = int(body.get("year", 1977))

    conn  = duckdb.connect(str(DB_PATH))
    count = conn.execute(
        "SELECT COUNT(*) FROM curated_scores_raw WHERE year = ? AND column_name != 'Band Name'",
        [year],
    ).fetchone()[0]
    if count == 0:
        conn.close()
        return {"error": f"Year {year} has no curated data. Add data before marking complete."}
    conn.close()

    csv_content, page_summaries, total_cells = _build_csv_content(year)
    csv_path = COMPLETED_DIR / f"{year}.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    now  = datetime.now(timezone.utc).isoformat()
    conn = duckdb.connect(str(DB_PATH))
    existing = conn.execute(
        "SELECT COUNT(*) FROM year_status WHERE year = ?", [year]
    ).fetchone()[0]
    if existing:
        conn.execute(
            "UPDATE year_status SET status='complete', completed_at=?, completed_csv_path=? WHERE year=?",
            [now, str(csv_path), year],
        )
    else:
        conn.execute(
            "INSERT INTO year_status (year, status, completed_at, completed_csv_path) VALUES (?, 'complete', ?, ?)",
            [year, now, str(csv_path)],
        )
    conn.close()

    return {
        "status":        "ok",
        "year":          year,
        "csv_path":      str(csv_path),
        "page_summaries": page_summaries,
        "total_cells":   total_cells,
    }


@app.post("/api/unlock_year")
async def api_unlock_year(request: Request) -> dict:
    body = await request.json()
    year = int(body.get("year", 1977))
    conn = duckdb.connect(str(DB_PATH))
    existing = conn.execute(
        "SELECT COUNT(*) FROM year_status WHERE year = ?", [year]
    ).fetchone()[0]
    if existing:
        conn.execute("UPDATE year_status SET status='in_progress' WHERE year=?", [year])
    else:
        conn.execute(
            "INSERT INTO year_status (year, status) VALUES (?, 'in_progress')", [year]
        )
    conn.close()
    return {"status": "ok", "year": year, "new_status": "in_progress"}


@app.post("/api/upload_csv")
async def api_upload_csv(
    file: UploadFile = File(...),
    year: int        = Form(...),
    mode: str        = Form(...),
) -> dict:
    if mode not in ("replace", "merge"):
        return {"error": f'mode must be "replace" or "merge", got "{mode}"'}
    if _get_year_status(year) == "complete":
        return {"error": f"Year {year} is marked complete. Unlock first to upload."}

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return {"error": "CSV appears empty or has no header row"}

    fieldnames = [f.strip() for f in reader.fieldnames]
    year_col = next((f for f in fieldnames if f.lower() == "year"),        None)
    band_col = next((f for f in fieldnames if f.lower() == "band"),        None)
    page_col = next((f for f in fieldnames if f.lower() == "page_number"), None)

    if not band_col:
        return {"error": "CSV must include a 'band' column"}

    data_cols = [f for f in fieldnames if f not in (year_col, band_col, page_col)]

    parsed_rows: list[dict] = []
    warnings:    list[str]  = []

    for row_idx, raw_row in enumerate(reader, start=2):
        row = {k.strip(): v.strip() for k, v in raw_row.items() if k}

        if year_col:
            row_year_str = row.get(year_col, "").strip()
            if row_year_str:
                try:
                    row_year = int(row_year_str)
                    if row_year != year:
                        return {"error": f"Row {row_idx} has year {row_year}, expected {year}"}
                except ValueError:
                    return {"error": f"Row {row_idx}: year value '{row_year_str}' is not an integer"}

        band = row.get(band_col, "").strip()
        if not band:
            return {"error": f"Row {row_idx}: band name is empty"}

        pnum = 1
        if page_col:
            pnum_str = row.get(page_col, "").strip()
            if pnum_str:
                try:
                    pnum = int(pnum_str)
                except ValueError:
                    return {"error": f"Row {row_idx}: page_number '{pnum_str}' is not an integer"}

        cell_values: dict[str, str] = {}
        for col in data_cols:
            val = row.get(col, "").strip()
            if val:
                try:
                    float(val)
                except ValueError:
                    warnings.append(
                        f"Row {row_idx} ({band}), col '{col}': non-numeric value '{val}' stored as text"
                    )
            cell_values[col] = val

        parsed_rows.append({"band": band, "page_number": pnum, "cells": cell_values})

    if not parsed_rows:
        return {"error": "CSV contains no data rows"}

    now           = datetime.now(timezone.utc).isoformat()
    conn          = duckdb.connect(str(DB_PATH))
    rows_deleted  = 0
    rows_updated  = 0
    rows_inserted = 0

    if mode == "replace":
        pages_in_csv = sorted(set(pr["page_number"] for pr in parsed_rows))
        for pg in pages_in_csv:
            count_before = conn.execute(
                "SELECT COUNT(*) FROM curated_scores_raw WHERE year = ? AND page_number = ?",
                [year, pg],
            ).fetchone()[0]
            conn.execute(
                "DELETE FROM curated_scores_raw WHERE year = ? AND page_number = ?",
                [year, pg],
            )
            rows_deleted += count_before

        records: list[tuple] = []
        for pr in parsed_rows:
            band = pr["band"]
            pnum = pr["page_number"]
            records.append((year, band, "Band Name", band, pnum, now, now, 0, None))
            for ci, col in enumerate(data_cols, 1):
                val = pr["cells"].get(col, "")
                records.append((year, band, col, val, pnum, now, now, ci, None))

        if records:
            conn.executemany(
                "INSERT INTO curated_scores_raw "
                "(year, band, column_name, value, page_number, created_at, updated_at, col_order, formula) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                records,
            )
            rows_inserted = len(records)

    else:  # merge
        for pr in parsed_rows:
            band = pr["band"]
            pnum = pr["page_number"]
            for ci, col in enumerate(data_cols, 1):
                val    = pr["cells"].get(col, "")
                exists = conn.execute(
                    "SELECT COUNT(*) FROM curated_scores_raw "
                    "WHERE year = ? AND band = ? AND column_name = ? AND page_number = ?",
                    [year, band, col, pnum],
                ).fetchone()[0]
                if exists:
                    conn.execute(
                        "UPDATE curated_scores_raw SET value=?, updated_at=? "
                        "WHERE year=? AND band=? AND column_name=? AND page_number=?",
                        [val, now, year, band, col, pnum],
                    )
                    rows_updated += 1
                else:
                    conn.execute(
                        "INSERT INTO curated_scores_raw "
                        "(year, band, column_name, value, page_number, created_at, updated_at, col_order, formula) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [year, band, col, val, pnum, now, now, ci, None],
                    )
                    rows_inserted += 1

    conn.close()

    result: dict = {
        "status":    "ok",
        "mode":      mode,
        "year":      year,
        "bands":     len(set(pr["band"] for pr in parsed_rows)),
        "data_cols": len(data_cols),
        "warnings":  warnings,
    }
    if mode == "replace":
        result["rows_deleted"]  = rows_deleted
        result["rows_inserted"] = rows_inserted
    else:
        result["rows_updated"]  = rows_updated
        result["rows_inserted"] = rows_inserted
    return result


@app.post("/api/extract")
async def api_extract(request: Request) -> dict:
    body        = await request.json()
    page_number = int(body.get("page_number", 1))
    year        = int(body.get("year", 1977))

    pages_dir = _get_year_pages_dir(year)
    page_file = pages_dir / f"page_{page_number:03d}.png"
    if not page_file.exists():
        return {"error": f"Page {page_number} not found for {year}"}

    api_key = (
        ANTHROPIC_KEY.read_text().strip() if ANTHROPIC_KEY.exists()
        else os.environ.get("ANTHROPIC_API_KEY", "")
    )
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    try:
        import anthropic as _ant
    except ImportError:
        return {"error": "anthropic package not installed"}

    prompt = (
        EXTRACT_PROMPT if page_number == 1
        else SUPPLEMENTAL_PROMPT_TEMPLATE.format(page=page_number)
    )

    img_b64 = base64.b64encode(page_file.read_bytes()).decode()
    client  = _ant.Anthropic(api_key=api_key)

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                    {"type": "text",  "text": prompt},
                ],
            }],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text  = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse failed: {exc}"}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/available_years")
async def api_available_years() -> dict:
    year_map, error = await asyncio.to_thread(_get_remote_year_map)
    if error:
        return {"error": error, "available": [], "already_loaded": []}
    loaded = set(_get_available_years())
    available     = sorted(y for y in year_map if y not in loaded)
    already_loaded = sorted(y for y in year_map if y in loaded)
    return {"available": available, "already_loaded": already_loaded}


@app.post("/api/load_year")
async def api_load_year(request: Request) -> dict:
    body = await request.json()
    year = int(body.get("year", 0))
    if not year:
        return {"error": "year is required"}

    if year in set(_get_available_years()):
        return {"status": "already_loaded", "year": year,
                "error": f"Year {year} is already loaded"}

    year_map, error = await asyncio.to_thread(_get_remote_year_map)
    if error:
        return {"error": f"Cannot reach pipeline server: {error}"}
    if year not in year_map:
        return {"error": f"Year {year} not found on pipeline server ({LXC124_IP})"}

    remote_filename = year_map[year]
    remote_src      = f"{LXC124_USER}@{LXC124_IP}:{LXC124_PDF_DIR}/{remote_filename}"

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    local_pdf = PDF_DIR / f"{year}.pdf"

    scp_error = await asyncio.to_thread(_scp_pdf, remote_src, local_pdf)
    if scp_error:
        if local_pdf.exists():
            local_pdf.unlink()
        return {"error": f"Transfer failed: {scp_error}"}

    out_dir = PAGES_DIR / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_generated, conv_error = await asyncio.to_thread(_convert_pdf_year, local_pdf, out_dir)

    resp: dict = {
        "status":          "ok",
        "year":            year,
        "pdf_path":        str(local_pdf),
        "pages_generated": pages_generated,
        "page_image_dir":  str(out_dir),
    }
    if conv_error:
        resp["conversion_error"] = conv_error
    return resp


@app.get("/api/export/csv")
def api_export_csv(year: int = 1977) -> StreamingResponse:
    csv_content, _, _ = _build_csv_content(year)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="curated_scores_{year}.csv"'},
    )


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8003, reload=False)
