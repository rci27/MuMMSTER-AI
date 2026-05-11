"""
Mummster — structured score parser.

Reads OCR text from ocr_results, parses judge-level and category-level scores
into the parsed_scores DuckDB table.  Handles three distinct era formats.

Safety contract:
  - A DuckDB backup is created before any writes (backup_db).
  - parsed_scores is append-only with upsert logic: existing records are
    replaced only if the new parse_confidence is strictly higher.
  - main_results is read-only from this module's perspective.
  - Each year is wrapped in a transaction — failure rolls back that year only.
  - Year 1968 is skipped and flagged as manual-entry-required.
"""

import hashlib
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path

import duckdb
import pandas as pd

from normalize import normalize_band_name, normalize_field

log = logging.getLogger("mummster.parse_scores")

# ── Constants ─────────────────────────────────────────────────────────────────

SKIP_YEARS = {1968}          # no reliable parseable format; manual entry needed
ERA_MODERN_START = 1991
ERA_CONTEMPORARY_START = 2014
ERA3_JUDGE_MATRIX_START = 2022   # format boundary confirmed from 2022 OCR sample
BACKUP_RETENTION = 10        # keep last N .db backups
MIN_BANDS_FOR_MODERN = 3     # fewer than this → flag file as needs-tesseract-reprocess

# ── Era 1 OCR Analysis — 2026-05-06 ──────────────────────────────────────────
#
# VISION-AI-REQUIRED YEARS (pdftotext returns garbage despite char count > 150):
#   Root cause: these are scanned images where pdftotext succeeds byte-count-wise
#   but extracts only layout whitespace and OCR artifacts — no real text.
#   The existing quality gate (char count ≥ 150) is insufficient; content must
#   also pass an alphanumeric-density check.
#
#   Confirmed garbage years from 1971 sample and adjacent years:
VISION_REQUIRED_YEARS = {
    1963, 1965, 1966, 1969, 1970, 1971, 1972, 1973, 1975, 1976, 1977,
    1978, 1979, 1980, 1981,
}
#   These years will receive parse_error = 'vision-extraction-required' and
#   will not be sent through the era1 parser.
#
# YEARS CURRENTLY PARSING AT CONFIDENCE 0.50 (1983-1989):
#   Records are written but totals differ from main_results by > 5 points.
#   Hypotheses (priority order):
#     1. Prize money column (e.g. "$1,000") being parsed as a score value.
#        _reconstruct_score_from_section strips "$" and "," correctly, yielding
#        1000.0 — which then displaces the real score columns by one position.
#     2. Header row passing the band-name fuzzy match (a header cell containing
#        a band name fragment) and being treated as a data row.
#     3. Fixed-width row_re failing to anchor correctly, so the wrong numeric
#        columns are captured as music/costume/pres/total.
#   Investigation needed (before fixing): query parsed_scores for year=1985,
#   category='Total Score', and compare to main_results.total_score for the
#   same band — the delta will confirm which column offset is wrong.
#
# PROPOSED FIX (not yet implemented — awaiting plan review):
#   (1) Add VISION_REQUIRED_YEARS check in run_parse before calling _parse_era1;
#       write placeholder record with parse_error = 'vision-extraction-required'.
#   (2) Add _text_alphanumeric_density(text) → float; if < 0.40, also flag as
#       vision-required even for years not in the hard list (catches future cases).
#   (3) For 1983-1989: after diagnosis, either exclude the prize column explicitly
#       from score parsing, or tighten the fixed-width regex to require numeric
#       tokens in the right range (scores 0-100, totals 0-400).

PARSED_SCORES_TABLE = "parsed_scores"
PARSED_SCORES_SUMMARY_VIEW = "parsed_scores_summary"
REPROCESS_FILE = Path("/opt/mummster/pipeline/tesseract_reprocess.txt")

# Era 2 category name normalization
_ERA2_CAT_MAP: dict[str, str] = {
    "music playing":        "Music Playing",
    "music arrangement":    "General Effect Music",
    "general effect music": "General Effect Music",
    "production":           "Visual Performance",
    "visual performance":   "Visual Performance",
    "performance":          "Performance",
    "costume":              "Costume",
    "total score":          "Total Score",
    "total":                "Total Score",
}

# ── Backup ────────────────────────────────────────────────────────────────────

def backup_db(db_path: Path, backup_dir: Path) -> Path | None:
    """
    Copy mummster.db to a timestamped file in backup_dir.
    Enforces BACKUP_RETENTION — deletes oldest backups beyond the limit.
    Returns the new backup path, or None if the DB doesn't exist yet.
    """
    if not db_path.exists():
        log.info("backup_db: no DB at %s — skipping", db_path)
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

    # Retention policy
    existing = sorted(backup_dir.glob("mummster_*.db"))
    to_delete = existing[:-BACKUP_RETENTION] if len(existing) > BACKUP_RETENTION else []
    for old in to_delete:
        try:
            old.unlink()
            log.info("Backup deleted (retention): %s", old.name)
        except OSError as exc:
            log.warning("Could not delete backup %s: %s", old.name, exc)

    return dest


# ── Schema DDL ────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PARSED_SCORES_TABLE} (
    id                TEXT,
    year              INTEGER,
    band              TEXT,
    placement         INTEGER,
    marching_order    INTEGER,
    category          TEXT,
    score             DOUBLE,
    subcategory       TEXT,
    subcategory_score DOUBLE,
    judge_number      INTEGER,
    judge_name        TEXT,
    theme             TEXT,
    prize_money       TEXT,
    penalty           DOUBLE,
    parse_confidence  DOUBLE,
    parse_method      TEXT,
    source_filename   TEXT,
    era               TEXT,
    parse_error       TEXT,
    parsed_at         TEXT,
    run_id            TEXT
)
"""

# Migrations: add columns introduced after initial deployment
_MIGRATE_SQL = f"""
ALTER TABLE {PARSED_SCORES_TABLE}
ADD COLUMN IF NOT EXISTS marching_order INTEGER
"""
_MIGRATE_JUDGE_NAME_SQL = f"""
ALTER TABLE {PARSED_SCORES_TABLE}
ADD COLUMN IF NOT EXISTS judge_name TEXT
"""

_CREATE_VIEW_SQL = f"""
CREATE OR REPLACE VIEW {PARSED_SCORES_SUMMARY_VIEW} AS
SELECT
    year,
    era,
    COUNT(DISTINCT band)              AS bands_parsed,
    COUNT(DISTINCT source_filename)   AS source_files,
    ROUND(AVG(parse_confidence), 3)   AS avg_confidence,
    SUM(CASE WHEN parse_error IS NOT NULL THEN 1 ELSE 0 END) AS error_count,
    COUNT(*)                          AS total_records,
    MAX(parsed_at)                    AS last_parsed_at
FROM {PARSED_SCORES_TABLE}
GROUP BY year, era
ORDER BY year
"""


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_CREATE_TABLE_SQL)
    for migration in (_MIGRATE_SQL, _MIGRATE_JUDGE_NAME_SQL):
        try:
            conn.execute(migration)
        except Exception:
            pass
    conn.execute(_CREATE_VIEW_SQL)
    log.debug("parsed_scores table and summary view ready")


# ── Utilities ─────────────────────────────────────────────────────────────────

def _era(year: int) -> str:
    if year < ERA_MODERN_START:
        return "pre-modern"
    if year < ERA_CONTEMPORARY_START:
        return "modern"
    return "contemporary"


def _record_id(year: int, band: str, category: str,
               subcategory: str | None, judge_number: int | None) -> str:
    key = f"{year}:{band.strip().upper()}:{category}:{subcategory or ''}:{judge_number or ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def _parse_score(text: str | None) -> float | None:
    if not text:
        return None
    clean = re.sub(r"[$,\s]", "", str(text).strip())
    try:
        return float(clean)
    except ValueError:
        return None


def _reconstruct_score_from_section(text: str, max_plausible: float = 200.0) -> float | None:
    """
    Reconstruct a score from a single pipe-delimited section where pdftotext
    has inserted spaces inside numbers due to fixed-width column layout.

    Rules (confirmed from OCR output):
      '3 7'  → 37    (column break inside integer: concatenate)
      '39 5' → 39.5  (decimal point dropped at column boundary; concat '395' > max_plausible)
      '1 8'  → 18    (concatenate; result ≤ max_plausible)

    Algorithm: concatenate all digit groups. If result > max_plausible, assume the
    last group is the fractional part and insert a decimal before it.
    Returns None if text contains no digit groups or is clearly an OCR artifact.
    """
    # Strip dollar signs, commas, and leading/trailing whitespace
    clean = re.sub(r'[$,]', '', str(text)).strip()

    if not clean:
        return None

    # Already has a decimal point → parse directly after collapsing internal spaces
    if '.' in clean:
        try:
            return float(re.sub(r'\s', '', clean))
        except ValueError:
            pass

    # Extract all contiguous digit groups
    groups = re.findall(r'\d+', clean)
    if not groups:
        return None

    if len(groups) == 1:
        try:
            return float(groups[0])
        except ValueError:
            return None

    # Concatenate all groups
    concat = ''.join(groups)
    try:
        v_concat = float(concat)
    except ValueError:
        return None

    if v_concat <= max_plausible:
        return v_concat

    # concat > max_plausible: insert decimal before the last group
    prefix = ''.join(groups[:-1])
    suffix = groups[-1]
    try:
        return float(f"{prefix}.{suffix}")
    except ValueError:
        return v_concat   # return as-is; confidence check will catch the mismatch


def _count_known_bands(text: str, known_bands: list[str]) -> int:
    """Count how many canonical band names appear in the OCR text (case-insensitive)."""
    text_upper = text.upper()
    return sum(1 for b in known_bands if b.strip().upper() in text_upper)


def _add_to_reprocess_queue(filename: str) -> None:
    """Append filename to REPROCESS_FILE if not already listed."""
    try:
        REPROCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: set[str] = set()
        if REPROCESS_FILE.exists():
            existing = {l.strip() for l in REPROCESS_FILE.read_text().splitlines() if l.strip()}
        if filename not in existing:
            with REPROCESS_FILE.open("a") as fh:
                fh.write(filename + "\n")
            log.info("Tesseract reprocess queue: added %s", filename)
    except OSError as exc:
        log.warning("Could not update reprocess queue: %s", exc)


def _compute_confidence(parsed_total: float | None, expected_total: float | None) -> float:
    if parsed_total is None or expected_total is None:
        return 0.5
    delta = abs(round(parsed_total, 2) - round(expected_total, 2))
    if delta < 0.5:
        return 1.0
    if delta < 5.0:
        return 0.8
    return 0.5


def _fuzzy_match_band(raw: str, known_bands: list[str]) -> tuple[str | None, bool]:
    """Return (canonical_band_name, exact_match)."""
    raw_up = raw.strip().upper()
    upper_to_canon = {b.strip().upper(): b for b in known_bands}
    if raw_up in upper_to_canon:
        return upper_to_canon[raw_up], True
    matches = get_close_matches(raw_up, list(upper_to_canon.keys()), n=1, cutoff=0.65)
    if matches:
        return upper_to_canon[matches[0]], False
    return None, False


def _get_known_bands(conn: duckdb.DuckDBPyConnection) -> list[str]:
    try:
        rows = conn.execute(
            "SELECT DISTINCT band FROM main_results WHERE band IS NOT NULL ORDER BY band"
        ).fetchall()
        return [normalize_band_name(r[0]) for r in rows if r[0]]
    except Exception:
        return []


def _get_main_map(conn: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    """Return {(year, band): {placement, total_score, theme, prize}} from main_results."""
    result: dict[tuple, dict] = {}
    try:
        rows = conn.execute(
            "SELECT year, band, placement, total_score, theme, prize FROM main_results "
            "WHERE year IS NOT NULL AND band IS NOT NULL"
        ).fetchall()
    except Exception:
        return result
    for year, band, placement, total_score, theme, prize in rows:
        try:
            y = int(float(str(year)))
        except (ValueError, TypeError):
            continue
        result[(y, (band or "").strip())] = {
            "placement":   placement,
            "total_score": _parse_score(str(total_score)) if total_score else None,
            "theme":       theme,
            "prize":       str(prize) if prize else None,
        }
    return result


def _filename_to_year(conn: duckdb.DuckDBPyConnection, filename: str) -> int | None:
    """Match OCR filename (Drive file ID + .pdf) to year via Point Sheet column."""
    file_id = Path(filename).stem
    try:
        rows = conn.execute(
            'SELECT year, "Point Sheet" FROM main_results WHERE "Point Sheet" IS NOT NULL'
        ).fetchall()
    except Exception:
        return None
    for year, url in rows:
        if url and file_id in str(url):
            try:
                return int(float(str(year)))
            except (ValueError, TypeError):
                continue
    return None


def _make_record(
    *,
    run_id: str,
    year: int,
    band: str,
    placement: int | None,
    category: str,
    score: float | None,
    marching_order: int | None = None,
    subcategory: str | None = None,
    subcategory_score: float | None = None,
    judge_number: int | None = None,
    judge_name: str | None = None,
    theme: str | None = None,
    prize_money: str | None = None,
    penalty: float | None = None,
    parse_confidence: float,
    parse_method: str,
    source_filename: str,
    era: str,
    parse_error: str | None = None,
) -> dict:
    category = normalize_field(category)   # canonical name before id computation
    return {
        "id":                _record_id(year, band, category, subcategory, judge_number),
        "year":              year,
        "band":              band,
        "placement":         placement,
        "marching_order":    marching_order,
        "category":          category,
        "score":             score,
        "subcategory":       subcategory,
        "subcategory_score": subcategory_score,
        "judge_number":      judge_number,
        "judge_name":        judge_name,
        "theme":             theme,
        "prize_money":       prize_money,
        "penalty":           penalty,
        "parse_confidence":  parse_confidence,
        "parse_method":      parse_method,
        "source_filename":   source_filename,
        "era":               era,
        "parse_error":       parse_error,
        "parsed_at":         datetime.now(timezone.utc).isoformat(),
        "run_id":            run_id,
    }


# ── Era 1 parser: Pre-modern 1963–1990 ────────────────────────────────────────

def _parse_era1(text: str, year: int, filename: str,
                known_bands: list[str], main_map: dict, run_id: str) -> list[dict]:
    """
    Pre-modern point sheets — pipe-delimited or fixed-width.
    Columns: Band, Prize, Music, Costume, Presentation/Other, Total
    Theme titles appear on the line immediately below each band row.
    """
    lines = text.splitlines()
    era   = _era(year)
    records: list[dict] = []

    # Detect format
    pipe_count = sum(1 for l in lines if l.count("|") >= 3)
    use_pipe   = pipe_count >= 3

    # Heuristic: numeric columns at end of line
    row_re = re.compile(
        r'^(?P<band>.{3,45}?)\s{2,}'
        r'(?P<prize>[\d$,.]+)\s+'
        r'(?P<music>[\d.]+)\s+'
        r'(?P<costume>[\d.]+)\s+'
        r'(?P<pres>[\d.]+)\s+'
        r'(?P<total>[\d.]+)\s*$'
    )

    placement = 0
    for i, line in enumerate(lines):
        raw = line.strip()
        if not raw:
            continue

        # Skip obvious header/separator lines
        if re.match(r'^[-=|_\s]+$', raw):
            continue
        upper = raw.upper()
        if any(kw in upper for kw in ("BAND", "CLUB", "PRIZE", "MUSIC", "TOTAL", "POSITION")):
            if not any(c.isdigit() for c in raw):
                continue

        if use_pipe:
            parts = [p for p in raw.split("|")]
            if len(parts) < 4:
                continue
            band_raw = parts[0].strip()
            # Strip leading rank number
            m = re.match(r'^(\d+)[.\s)]+(.+)$', band_raw)
            if m:
                placement = int(m.group(1))
                band_raw  = m.group(2).strip()
            else:
                placement += 1

            # Parse each pipe section independently using the reconstruction function.
            # This handles spaces-within-numbers from pdftotext column layout.
            # Prize section (parts[1]) may contain a dollar amount — keep as string.
            prize_raw = parts[1].strip() if len(parts) > 1 else None

            # Score sections: all parts after prize (parts[2:])
            score_sections = parts[2:] if len(parts) > 2 else []
            section_scores: list[float | None] = [
                _reconstruct_score_from_section(s) for s in score_sections
            ]
            valid_scores = [v for v in section_scores if v is not None]

            if len(valid_scores) < 2:
                continue

            # Expect: Music, Costume, Presentation, Total (last 4 valid scores)
            # If a section is an OCR artifact (None), attempt back-calculation below.
            total   = valid_scores[-1] if valid_scores else None
            music   = valid_scores[-4] if len(valid_scores) >= 4 else (valid_scores[0] if len(valid_scores) >= 1 else None)
            costume = valid_scores[-3] if len(valid_scores) >= 3 else (valid_scores[1] if len(valid_scores) >= 2 else None)
            pres    = valid_scores[-2] if len(valid_scores) >= 3 else None

            # Back-calculate presentation if it was an OCR artifact (None or implausible).
            # Artifact indicators: section contains no valid digit groups, or score < 1.
            backfilled_pres = False
            pres_section_raw = score_sections[-2] if len(score_sections) >= 2 else ""
            pres_is_artifact = (
                pres is None
                or (pres < 1.0 and re.search(r'[^0-9.\s]', pres_section_raw))
            )
            if pres_is_artifact and music is not None and costume is not None:
                main_ref = main_map.get((year, band_raw.strip() if not band_raw.startswith(" ") else band_raw.strip()))
                ref_total = main_ref["total_score"] if main_ref else total
                if ref_total is not None and music is not None and costume is not None:
                    pres = round(ref_total - music - costume, 1)
                    total = ref_total
                    backfilled_pres = True
        else:
            m = row_re.match(line)
            if not m:
                continue
            placement += 1
            band_raw  = m.group("band")
            prize_raw = m.group("prize")
            music     = _parse_score(m.group("music"))
            costume   = _parse_score(m.group("costume"))
            pres      = _parse_score(m.group("pres"))
            total     = _parse_score(m.group("total"))

        if not band_raw or len(band_raw.strip()) < 3:
            continue

        band, exact = _fuzzy_match_band(band_raw, known_bands)
        if not band:
            band = band_raw.strip()

        # Theme: next non-empty line that doesn't look like a data row
        theme = None
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if nxt and not re.search(r'\d{2,}', nxt) and len(nxt) > 4:
                theme = nxt
                break

        main = main_map.get((year, band))
        confidence = _compute_confidence(total, main["total_score"] if main else None)
        if use_pipe and backfilled_pres:
            confidence = min(confidence, 0.7)
        if main and main.get("theme") and not theme:
            theme = main["theme"]

        if use_pipe:
            parse_method = "era1-pipe-backfill" if backfilled_pres else "era1-pipe"
        else:
            parse_method = "era1-fixed"

        cats = [
            ("Music",        music),
            ("Costume",      costume),
            ("Presentation", pres),
            ("Total Score",  total),
        ]
        for cat, score in cats:
            if score is None:
                continue
            records.append(_make_record(
                run_id=run_id, year=year, band=band, placement=placement,
                category=cat, score=score, theme=theme,
                prize_money=str(prize_raw) if prize_raw else None,
                parse_confidence=confidence, parse_method=parse_method,
                source_filename=filename, era=era,
            ))

    return records


# ── Era 2 parser: Modern 1991–2013 ────────────────────────────────────────────
#
# OCR ANALYSIS — 1993 point sheet (2026-05-06)
# ─────────────────────────────────────────────
# HEADER STRUCTURE: three lines, not one.
#   Line 1: top-level categories, spaced wide  e.g. "MUSIC       PRESENTATION ..."
#   Line 2: sub-labels beneath each category   e.g. "PLAYING  ARRANGEMENT  PRODUCTION  PERFORMANCE  COSTUME"
#   Line 3: point-value weights                e.g. "200      200          200         200          100"
#
# DATA ROW STRUCTURE (confirmed):
#   [rank]  [BAND NAME ALL CAPS]  [grand_total]  [j1]  [j2]  [avg]  [j1]  [j2]  [avg]  [subtotal]  ...
#   Group of (j1, j2, avg) repeats for each sub-category; [subtotal] closes each top-level category.
#   Individual judge scores ARE present — judge_number 1 or 2 per score.
#
# CURRENT FAILURE MODE:
#   _parse_era2 looks for "MUSIC" and ("COSTUME" or "TOTAL") on the SAME line.
#   The 1993 layout puts these words on different lines, so header_idx is never
#   set and the function returns [] for every modern year.
#
# PROPOSED FIX (not yet implemented — awaiting plan review):
#   Replace single-line scan with _find_era2_header_block():
#     Scan for a line containing "PLAYING"; check the next 5 lines for "ARRANGEMENT".
#     The span [playing_line .. arrangement_line] is the multi-line header block.
#   Reconstruct a merged column map from the combined header lines (horizontal
#   character offsets) to identify where each (category, judge_slot) column lives.
#   Parse each data row by: extracting rank (first int), band (uppercase token block),
#   then reading the remaining floats into groups of (j1, j2, avg, [subtotal]).
#   Emit one parsed_scores record per judge per sub-category (judge_number = 1 or 2);
#   also emit the avg as judge_number = None (or 0) for aggregation queries.

def _parse_era2(text: str, year: int, filename: str,
                known_bands: list[str], main_map: dict, run_id: str) -> list[dict]:
    """
    Modern era — columnar format with explicit header row.
    Columns: Position, Prize, Club, Music Playing, Music Arrangement,
             Production, Performance, Costume, Total Score.
    """
    lines = text.splitlines()
    era   = _era(year)
    records: list[dict] = []

    # Find header line: contains "Music" and ("Costume" or "Total")
    header_idx = None
    raw_header_cols: list[str] = []
    for i, line in enumerate(lines):
        up = line.upper()
        if "MUSIC" in up and ("COSTUME" in up or "TOTAL" in up):
            # Try tab split, then 2+ space split
            if "\t" in line:
                raw_header_cols = [c.strip() for c in line.split("\t")]
            else:
                raw_header_cols = [c.strip() for c in re.split(r" {2,}", line.strip())]
            if len(raw_header_cols) >= 4:
                header_idx = i
                break

    if header_idx is None:
        log.warning("Era 2 [%d]: no header row found in %s", year, filename)
        return records

    # Normalize column names
    norm_cols = [_ERA2_CAT_MAP.get(c.lower().strip(), c.strip()) for c in raw_header_cols]

    def _col(*names: str) -> int | None:
        for n in names:
            for i, c in enumerate(norm_cols):
                if n.lower() in c.lower():
                    return i
        return None

    pos_i     = _col("position", "pos", "#", "rank")
    prize_i   = _col("prize", "award", "$")
    band_i    = _col("club", "band", "name")
    mp_i      = _col("music playing")
    gem_i     = _col("general effect music", "music arrangement")
    vp_i      = _col("visual performance", "production")
    perf_i    = _col("performance")
    costume_i = _col("costume")
    total_i   = _col("total score", "total")

    if band_i is None or total_i is None:
        log.warning("Era 2 [%d]: could not locate band or total column in %s", year, filename)
        return records

    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped or len(stripped) < 8:
            continue
        if re.match(r'^[-=]+$', stripped):
            continue

        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        else:
            parts = [p.strip() for p in re.split(r" {2,}", stripped)]

        max_needed = max(i for i in [band_i, total_i] if i is not None)
        if len(parts) <= max_needed:
            continue

        def get(idx: int | None) -> str | None:
            return parts[idx] if idx is not None and idx < len(parts) else None

        band_raw = get(band_i) or ""
        if len(band_raw) < 3 or re.match(r'^[-\d.]+$', band_raw):
            continue

        band, _ = _fuzzy_match_band(band_raw, known_bands)
        if not band:
            band = band_raw

        placement = None
        pos_raw = get(pos_i)
        if pos_raw:
            m = re.search(r'\d+', pos_raw)
            if m:
                placement = int(m.group())

        scores = {
            "Music Playing":        _parse_score(get(mp_i)),
            "General Effect Music": _parse_score(get(gem_i)),
            "Visual Performance":   _parse_score(get(vp_i)),
            "Performance":          _parse_score(get(perf_i)),
            "Costume":              _parse_score(get(costume_i)),
            "Total Score":          _parse_score(get(total_i)),
        }

        main = main_map.get((year, band))
        confidence = _compute_confidence(scores["Total Score"], main["total_score"] if main else None)
        prize = get(prize_i)

        for cat, score in scores.items():
            if score is None:
                continue
            records.append(_make_record(
                run_id=run_id, year=year, band=band, placement=placement,
                category=cat, score=score,
                theme=main["theme"] if main else None,
                prize_money=prize,
                parse_confidence=confidence,
                parse_method="era2-columnar",
                source_filename=filename, era=era,
            ))

    return records


# ── Era 3 parser: Contemporary 2014–present ───────────────────────────────────
#
# OCR ANALYSIS — 2022 point sheet (2026-05-06)
# ─────────────────────────────────────────────
# FORMAT SPLIT CONFIRMED: 2014-2020 and 2022+ use different layouts.
#
# 2014-2020 (current era3-v2 target):
#   Rank(int) MarchingOrder(int) BandName Penalty(int) TotalScore(float) [cat floats...]
#   Parser runs and extracts records but confidence = 0.46 across all years.
#   Root cause unconfirmed — likely the state machine stops at a category subtotal
#   rather than the grand total.  The line may be:
#     rank pos band penalty MusicTotal GEMTotal VPTotal GEVTotal GrandTotal
#   making the "first float after penalty" = MusicTotal, not GrandTotal.
#   Needs: print raw post-band token sequence for one known band (e.g. Fralinger 2020).
#
# 2022+ — JUDGE-BY-SUBCATEGORY MATRIX (requires separate parser, era3_judge_matrix):
#   Header contains individual judge names matching [A-Z]\. [A-Z][a-z]+
#   (e.g. "G. Leitzel", "J. McCoach") — multiple judges per category.
#   Each band row is a score vector over (judge × subcategory) pairs.
#   Grand total column is NOT positionally predictable — locate via labeled
#   "TOTAL" header column or as the sum/rightmost float on each band line.
#   The current era3-v2 state machine cannot handle this matrix layout.
#
# PROPOSED FIX (not yet implemented — awaiting plan review):
#   Constant: ERA3_JUDGE_MATRIX_START = 2022
#   Routing in run_parse: year >= ERA3_JUDGE_MATRIX_START → _parse_era3_judge_matrix()
#   _parse_era3_judge_matrix():
#     Phase 1 — header scan: collect lines matching [A-Z]\. [A-Z][a-z]+; build
#     ordered judge list with column offsets (character positions from the OCR line).
#     Phase 2 — data rows: for each band-name-anchored line, slice the score
#     vector by column offset to map each float to (judge_name, subcategory).
#     Grand total: pin from a "TOTAL" header column; fallback to rightmost float.
#     Emit one parsed_scores record per (band, judge, subcategory) combination.

# Category totals column order in the typical contemporary point sheet:
# Rank | Marching# | Band | Penalty | TotalMP | TotalGEM | TotalVP | TotalGEV | GrandTotal
_ERA3_CATS = ["Music Playing", "General Effect Music", "Visual Performance", "General Effect Visual"]

# Subcategory structures per category (for multi-line point sheets)
_ERA3_SUBCATS: dict[str, list[str]] = {
    "Music Playing":        ["Technique", "Musicianship"],
    "General Effect Music": ["Effectiveness", "Effectiveness"],
    "Visual Performance":   ["Composition", "Accuracy/Technique", "Costume", "Performance", "Performance Effect"],
    "General Effect Visual": ["Overall Effect", "Costume"],
}


def _parse_era3(text: str, year: int, filename: str,
                known_bands: list[str], main_map: dict, run_id: str) -> list[dict]:
    """
    Contemporary era 2014-2021 (era3-v3).
    Confirmed column layout from 2020 Datasette analysis:
      pre-band:  [...] MarchingOrder(int) Rank(int)  ← last two ints before band
      post-band: Penalty(int) GrandTotal(float) [sub sub MP_total sub sub GEM_total
                  sub sub sub VP_total sub sub GEV_total]

    Fixed index positions after penalty:
      sn[0]=GrandTotal  sn[3]=MP  sn[6]=GEM  sn[10]=VP  sn[13]=GEV
    marching_order = pre_ints[-2] (second-to-last int before band name).
    """
    lines   = text.splitlines()
    era     = _era(year)
    records: list[dict] = []

    # Sort known bands by length descending so longer names match before substrings
    sorted_bands = sorted(known_bands, key=len, reverse=True)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Find the longest known band name present in this line
        band = None
        band_m_start = -1
        band_m_end   = -1
        for known in sorted_bands:
            pat = re.compile(re.escape(known.strip()), re.IGNORECASE)
            m = pat.search(stripped)
            if m:
                band = known
                band_m_start = m.start()
                band_m_end   = m.end()
                break
        if not band:
            continue

        pre_band  = stripped[:band_m_start]
        post_band = stripped[band_m_end:]

        # Pre-band integers: last = rank (finishing position),
        # second-to-last = marching_order (parade draw/position).
        # Confirmed from 2020 Datasette analysis: marching_order was null with
        # the old pre_ints[1] approach; pre_ints[-2] gives the correct column.
        pre_ints = re.findall(r'\b(\d+)\b', pre_band)
        rank           = int(pre_ints[0])  if len(pre_ints) >= 1 else None
        marching_order = int(pre_ints[-2]) if len(pre_ints) >= 2 else None

        # Post-band: collect every numeric token in order, then extract by
        # FIXED POSITION — state machine was stopping at wrong float.
        # Confirmed token positions from 2020 OCR analysis (after penalty int):
        #   [0] grand total   [1][2] subcats   [3] MP total
        #   [4][5] subcats    [6] GEM total
        #   [7][8][9] subcats [10] VP total
        #   [11][12] subcats  [13] GEV total
        post_nums: list[float] = []
        for tok in post_band.split():
            cleaned = re.sub(r'[^0-9.]', '', tok)
            if not cleaned:
                continue
            try:
                post_nums.append(float(cleaned))
            except ValueError:
                continue

        # First integer-like value (0–99, no decimal) is penalty
        penalty    = None
        score_start = 0
        for idx, v in enumerate(post_nums):
            if v == int(v) and 0 <= v <= 99:
                penalty     = int(v)
                score_start = idx + 1
            else:
                # First value is already a float → treat penalty as 0
                penalty     = 0
                score_start = idx
            break

        sn = post_nums[score_start:]  # score numbers after penalty

        total     = sn[0]  if len(sn) >  0 else None
        mp_total  = sn[3]  if len(sn) >  3 else None
        gem_total = sn[6]  if len(sn) >  6 else None
        vp_total  = sn[10] if len(sn) > 10 else None
        gev_total = sn[13] if len(sn) > 13 else None

        if total is None:
            continue

        main = main_map.get((year, band))
        confidence = _compute_confidence(total, main["total_score"] if main else None)

        common = dict(
            run_id=run_id, year=year, band=band,
            placement=rank, marching_order=marching_order,
            penalty=float(penalty) if penalty is not None else None,
            theme=main["theme"] if main else None,
            prize_money=main["prize"] if main else None,
            source_filename=filename, era=era,
        )

        records.append(_make_record(
            **common,
            category="Total Score", score=total,
            parse_confidence=confidence, parse_method="era3-v3",
        ))

        for cat, score in [
            ("Music Playing",        mp_total),
            ("General Effect Music", gem_total),
            ("Visual Performance",   vp_total),
            ("General Effect Visual", gev_total),
        ]:
            if score is not None:
                records.append(_make_record(
                    **common,
                    category=cat, score=score,
                    parse_confidence=round(confidence * 0.9, 3),
                    parse_method="era3-v3",
                ))

    # Second pass: subcategory detail lines near band-name lines
    num_re = re.compile(r'\b\d+(?:\.\d+)?\b')
    for i, line in enumerate(lines):
        stripped = line.strip()
        for cat, subcats in _ERA3_SUBCATS.items():
            for j, subcat in enumerate(subcats):
                if subcat.upper() not in stripped.upper():
                    continue
                nums = [float(m.group()) for m in num_re.finditer(stripped)]
                if not nums:
                    continue
                nearby_band = None
                for k in range(max(0, i - 10), i):
                    for known in sorted_bands:
                        if known.strip().upper() in lines[k].upper():
                            nearby_band = known
                            break
                    if nearby_band:
                        break
                if not nearby_band:
                    continue
                main = main_map.get((year, nearby_band))
                records.append(_make_record(
                    run_id=run_id, year=year, band=nearby_band,
                    placement=None, marching_order=None,
                    category=cat, score=nums[-1],
                    subcategory=subcat,
                    subcategory_score=nums[j] if j < len(nums) else None,
                    judge_number=j + 1 if "Effectiveness" in subcat else None,
                    theme=main["theme"] if main else None,
                    prize_money=main["prize"] if main else None,
                    parse_confidence=0.7, parse_method="era3-subcategory-v2",
                    source_filename=filename, era=era,
                ))

    return records


# ── Upsert ────────────────────────────────────────────────────────────────────

def _upsert(conn: duckdb.DuckDBPyConnection, records: list[dict]) -> int:
    """
    Append-only upsert: existing records are replaced only when the new
    parse_confidence is strictly higher.  Never deletes records without replacement.
    Returns number of records written (new + replaced).
    """
    if not records:
        return 0

    df = pd.DataFrame(records)

    # Delete records that would be improved (lower confidence than incoming)
    conn.register("_ps_new", df[["id", "parse_confidence"]])
    conn.execute(f"""
        DELETE FROM {PARSED_SCORES_TABLE} existing
        WHERE EXISTS (
            SELECT 1 FROM _ps_new n
            WHERE n.id = existing.id
              AND n.parse_confidence > existing.parse_confidence
        )
    """)
    conn.unregister("_ps_new")

    # Explicit column list guards against position mismatches when ALTER TABLE
    # has placed marching_order at the table tail while the DataFrame has it mid-order.
    _COLS = (
        "id, year, band, placement, marching_order, category, score, "
        "subcategory, subcategory_score, judge_number, judge_name, theme, prize_money, "
        "penalty, parse_confidence, parse_method, source_filename, era, "
        "parse_error, parsed_at, run_id"
    )

    # Insert all incoming records that don't already exist
    conn.register("_ps_incoming", df)
    conn.execute(f"""
        INSERT INTO {PARSED_SCORES_TABLE} ({_COLS})
        SELECT {_COLS}
        FROM _ps_incoming i
        WHERE NOT EXISTS (
            SELECT 1 FROM {PARSED_SCORES_TABLE} e WHERE e.id = i.id
        )
    """)
    conn.unregister("_ps_incoming")

    return len(records)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_parse(
    conn: duckdb.DuckDBPyConnection,
    db_path: Path,
    backup_dir: Path,
) -> dict:
    """
    Called from sync.py after OCR step.
    Creates a backup, then parses all unprocessed OCR text into parsed_scores.
    Returns a stats dict.
    """
    stats: dict = {
        "backup_path":      None,
        "years_attempted":  0,
        "years_succeeded":  0,
        "years_failed":     0,
        "years_skipped":    0,
        "records_written":  0,
        "errors":           [],
    }

    backup = backup_db(db_path, backup_dir)
    if backup:
        stats["backup_path"] = str(backup)

    ensure_schema(conn)

    known_bands = _get_known_bands(conn)
    main_map    = _get_main_map(conn)
    run_id      = str(uuid.uuid4())

    log.info("Parse run %s  bands_known=%d  main_rows=%d",
             run_id[:8], len(known_bands), len(main_map))

    try:
        ocr_rows = conn.execute("""
            SELECT filename, text, method, confidence
            FROM ocr_results
            WHERE text IS NOT NULL AND text != '' AND error IS NULL
            ORDER BY filename
        """).fetchall()
    except Exception as exc:
        log.error("Cannot query ocr_results: %s", exc)
        stats["errors"].append(str(exc))
        return stats

    # Resolve filename → year; group by year
    by_year: dict[int, list[dict]] = {}
    for filename, text, method, confidence in ocr_rows:
        year = _filename_to_year(conn, filename)
        if year is None:
            log.debug("No year mapping for %s — skipping", filename)
            continue
        by_year.setdefault(year, []).append({
            "filename": filename, "text": text,
            "method": method, "confidence": confidence,
        })

    now = datetime.now(timezone.utc).isoformat()

    for year, ocr_batch in sorted(by_year.items()):
        stats["years_attempted"] += 1

        if year in SKIP_YEARS:
            log.info("Year %d: skipped (manual-entry-required)", year)
            stats["years_skipped"] += 1
            # Write a placeholder record so the summary view shows the gap
            skip_rec = _make_record(
                run_id=run_id, year=year, band="", placement=None,
                category="", score=None,
                parse_confidence=0.0, parse_method="skip",
                source_filename=ocr_batch[0]["filename"],
                era=_era(year),
                parse_error="manual-entry-required",
            )
            try:
                conn.execute("BEGIN TRANSACTION")
                _upsert(conn, [skip_rec])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
            continue

        era          = _era(year)
        year_records: list[dict] = []

        for ocr in ocr_batch:
            fn, text = ocr["filename"], ocr["text"]

            # Fix 2 — Modern era OCR quality gate.
            # pdftotext sometimes returns plausible character counts but no actual
            # band names (garbage column data). Flag and skip; queue for Tesseract reprocess.
            if ERA_MODERN_START <= year < ERA_CONTEMPORARY_START:
                band_count = _count_known_bands(text, known_bands)
                if band_count < MIN_BANDS_FOR_MODERN:
                    log.warning(
                        "[%d] %s: only %d known band name(s) found — queuing for Tesseract reprocess",
                        year, fn, band_count,
                    )
                    _add_to_reprocess_queue(fn)
                    stats["errors"].append(
                        f"[{year}] {fn}: needs-tesseract-reprocess (bands_found={band_count})"
                    )
                    continue

            try:
                if year < ERA_MODERN_START:
                    parsed = _parse_era1(text, year, fn, known_bands, main_map, run_id)
                elif year < ERA_CONTEMPORARY_START:
                    parsed = _parse_era2(text, year, fn, known_bands, main_map, run_id)
                else:
                    parsed = _parse_era3(text, year, fn, known_bands, main_map, run_id)
                year_records.extend(parsed)
                log.debug("  [%d] %s → %d records", year, fn, len(parsed))
            except Exception as exc:
                msg = f"[{year}] {fn}: parse error: {exc}"
                log.warning(msg)
                stats["errors"].append(msg)

        if not year_records:
            log.info("Year %d [%s]: no records extracted", year, era)
            stats["years_failed"] += 1
            continue

        # Wrap year in a transaction — roll back entirely on any write error
        try:
            conn.execute("BEGIN TRANSACTION")
            written = _upsert(conn, year_records)
            conn.execute("COMMIT")
            stats["records_written"] += written
            stats["years_succeeded"] += 1
            avg_conf = sum(r["parse_confidence"] for r in year_records) / len(year_records)
            log.info("Year %d [%s]: %d records written  avg_confidence=%.2f",
                     year, era, written, avg_conf)
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            msg = f"Year {year}: transaction rolled back — {exc}"
            log.error(msg)
            stats["years_failed"] += 1
            stats["errors"].append(msg)

    log.info(
        "Parse complete — attempted=%d succeeded=%d failed=%d skipped=%d records=%d",
        stats["years_attempted"], stats["years_succeeded"],
        stats["years_failed"], stats["years_skipped"], stats["records_written"],
    )
    return stats
