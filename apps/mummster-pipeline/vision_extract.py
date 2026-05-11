"""
Mummster — vision AI score extractor.

Converts PDF pages to base64 PNG and sends to Claude vision API for
structured JSON extraction. Handles all eras and sheet formats that
failed text-based parsing.

Priority order:
  1. Era 1 pre-modern (1963-1990)  }  avg parse_confidence < CONFIDENCE_THRESHOLD
  2. Era 2 modern (1991-2013)      }  or no text-parse records at all
  3. Era 3 contemporary (2014+)    }
  4. Year 1968 (manual-entry-required) — always included

Rate limited to RATE_LIMIT_PER_MINUTE PDF calls to avoid API throttling.
Cost per PDF is estimated and logged using known token pricing.
"""

import base64
import io
import json
import logging
import time
import uuid
from pathlib import Path

import anthropic
import duckdb
from pdf2image import convert_from_path

from normalize import normalize_field
from parse_scores import (
    PARSED_SCORES_TABLE,
    _compute_confidence,
    _era,
    _filename_to_year,
    _fuzzy_match_band,
    _get_known_bands,
    _get_main_map,
    _make_record,
    _upsert,
    ensure_schema,
)

log = logging.getLogger("mummster.vision_extract")

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL                    = "claude-sonnet-4-6"
ANTHROPIC_KEY_PATH_DEFAULT = "/etc/artemis-secrets/anthropic.key"
RATE_LIMIT_PER_MINUTE    = 5      # max PDF-level API calls per minute
PDF_DPI                  = 150    # resolution for page→image conversion
MAX_TOKENS_PER_PAGE      = 32000
CONFIDENCE_THRESHOLD     = 0.8    # years below this are queued for extraction

# Approximate pricing for claude-sonnet-4-6 (2025)
_INPUT_COST_PER_MTOK  = 3.00     # USD per million input tokens
_OUTPUT_COST_PER_MTOK = 15.00    # USD per million output tokens

# Cost guard: abort if estimated run cost exceeds this unless force_vision=True.
# Estimated at $0.35/year (run-2 actual average: $18.55 / 57 years).
# Override via VISION_COST_LIMIT_USD in config.env; bypass via FORCE_VISION=true.
COST_GUARD_LIMIT_USD        = 2.0
ESTIMATED_COST_PER_YEAR_USD = 0.35

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are extracting structured scoring data from Philadelphia Mummers String Band "
    "competition point sheets. Extract all data into JSON. "
    "Return ONLY valid JSON, no other text."
)

_USER_PROMPT = (
    "This is page {page} of the {year} Philadelphia Mummers String Band competition "
    "scoring sheet. Extract all scoring data into this exact JSON structure: "
    '{{"year": {year}, "bands": ['
    '{{"rank": int or null, "marching_order": int or null, "band_name": str, '
    '"grand_total": float or null, "penalty": float or null, '
    '"categories": {{'
    '"Music Playing": float or null, "General Effect Music": float or null, '
    '"Visual Performance": float or null, "General Effect Visual": float or null, '
    '"Costume": float or null, "Music": float or null, "Presentation": float or null'
    '}}, '
    '"judges": [{{"judge_name": str or null, "judge_number": int or null, '
    '"category": str, "score": float}}], '
    '"theme": str or null, "prize_money": str or null'
    '}}]}} '
    "Include all bands visible on this page. Use null for any value not present. "
    "Normalize category names to match the standard names in the JSON structure. "
    "For pre-1991 sheets the categories will be Music, Costume, and Presentation. "
    "For 1991-2013 the categories will be Music Playing, General Effect Music, "
    "Visual Performance, General Effect Visual, and Costume. "
    "For 2014+ Costume will be absent. "
    "IMPORTANT: The grand_total field must be the final overall score for the band "
    "— typically the largest single number associated with that band, usually between "
    "70 and 100 for contemporary era sheets. Individual judge subcategory scores are "
    "typically between 5 and 20. If the value you are placing in grand_total is less "
    "than 50, you have the wrong number — look for the overall final score instead."
)


# ── Rate limiter ──────────────────────────────────────────────────────────────

class _RateLimiter:
    """Token bucket: enforce minimum gap between calls."""
    def __init__(self, per_minute: int) -> None:
        self._min_gap = 60.0 / per_minute
        self._last = 0.0

    def wait(self) -> None:
        gap = self._min_gap - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


# ── PDF → base64 pages ────────────────────────────────────────────────────────

def _pdf_to_base64_pages(pdf_path: Path) -> list[str]:
    """Convert every PDF page to a base64-encoded PNG. Returns [] on failure."""
    try:
        images = convert_from_path(str(pdf_path), dpi=PDF_DPI)
    except Exception as exc:
        log.error("pdf2image failed for %s: %s", pdf_path.name, exc)
        return []
    pages: list[str] = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        pages.append(base64.standard_b64encode(buf.getvalue()).decode())
    return pages


# ── Single-page API call ──────────────────────────────────────────────────────

def _extract_page(
    client: anthropic.Anthropic,
    year: int,
    page_num: int,
    page_b64: str,
) -> tuple[dict | None, int, int]:
    """
    Send one page image to Claude vision.
    Returns (parsed_dict | None, input_tokens, output_tokens).
    """
    try:
        # Use streaming — required by Anthropic SDK when max_tokens is large
        # (requests that may take > 10 min must use the stream context manager).
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS_PER_PAGE,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": page_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": _USER_PROMPT.format(page=page_num, year=year),
                    },
                ],
            }],
        ) as stream:
            resp = stream.get_final_message()
    except Exception as exc:
        log.error("Vision API error (year=%d page=%d): %s", year, page_num, exc)
        return None, 0, 0

    in_tok  = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    raw     = resp.content[0].text.strip()

    # Strip markdown fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```")).strip()

    try:
        return json.loads(raw), in_tok, out_tok
    except json.JSONDecodeError as exc:
        exc_str = str(exc)
        # "Extra data": valid JSON followed by extra model output — slice at exc.pos.
        if "Extra data" in exc_str and exc.pos > 0:
            try:
                return json.loads(raw[:exc.pos]), in_tok, out_tok
            except json.JSONDecodeError:
                pass
        # "Expecting ',' delimiter": model emitted a malformed band entry mid-array.
        # Recover by finding the last complete band object before the error and
        # closing the JSON structure.
        if "Expecting ',' delimiter" in exc_str:
            segment = raw[:exc.pos]
            last_band_end = segment.rfind('},')
            if last_band_end > 0:
                for suffix in (']}', ']}}', '}]}'):
                    try:
                        return json.loads(segment[:last_band_end + 1] + suffix), in_tok, out_tok
                    except json.JSONDecodeError:
                        pass
        log.warning("JSON parse failed (year=%d page=%d): %s — raw: %s",
                    year, page_num, exc, raw[:300])
        return None, in_tok, out_tok


# ── Multi-page merger ─────────────────────────────────────────────────────────

def _merge_pages(pages: list[dict]) -> dict:
    """
    Combine band data across all pages of one PDF.
    Bands are keyed by uppercase name; null fields are filled from later pages;
    judge lists are concatenated.
    """
    if not pages:
        return {"bands": []}

    year   = next((p.get("year") for p in pages if p.get("year")), None)
    merged: dict[str, dict] = {}

    for page in pages:
        for band in page.get("bands") or []:
            key = (band.get("band_name") or "").strip().upper()
            if not key:
                continue
            if key not in merged:
                merged[key] = {
                    "band_name":      band.get("band_name"),
                    "rank":           band.get("rank"),
                    "marching_order": band.get("marching_order"),
                    "grand_total":    band.get("grand_total"),
                    "penalty":        band.get("penalty"),
                    "theme":          band.get("theme"),
                    "prize_money":    band.get("prize_money"),
                    "categories":     dict(band.get("categories") or {}),
                    "judges":         list(band.get("judges") or []),
                }
            else:
                ex = merged[key]
                for field in ("rank", "marching_order", "grand_total",
                              "penalty", "theme", "prize_money"):
                    if ex.get(field) is None and band.get(field) is not None:
                        ex[field] = band[field]
                for cat, score in (band.get("categories") or {}).items():
                    if score is not None and ex["categories"].get(cat) is None:
                        ex["categories"][cat] = score
                ex["judges"].extend(band.get("judges") or [])

    return {"year": year, "bands": list(merged.values())}


# ── Record builder ────────────────────────────────────────────────────────────

def _band_to_records(
    band: dict,
    year: int,
    filename: str,
    run_id: str,
    main_map: dict,
    known_bands: list[str],
) -> list[dict]:
    """Convert one band's extracted data into parsed_scores record dicts."""
    raw_name = (band.get("band_name") or "").strip()
    if not raw_name:
        return []

    canonical, _ = _fuzzy_match_band(raw_name, known_bands)
    band_name    = canonical or raw_name

    grand_total = band.get("grand_total")
    main        = main_map.get((year, band_name))
    expected    = main["total_score"] if main else None
    confidence  = _compute_confidence(grand_total, expected)

    common = dict(
        run_id=run_id, year=year, band=band_name,
        placement=band.get("rank"),
        marching_order=band.get("marching_order"),
        penalty=band.get("penalty"),
        theme=band.get("theme") or (main["theme"] if main else None),
        prize_money=band.get("prize_money") or (main["prize"] if main else None),
        parse_confidence=confidence,
        parse_method="vision-extracted",
        source_filename=filename,
        era=_era(year),
    )

    records: list[dict] = []

    if grand_total is not None:
        records.append(_make_record(**common, category="Total Score", score=grand_total))

    for cat, score in (band.get("categories") or {}).items():
        if score is not None:
            records.append(_make_record(**common, category=normalize_field(cat), score=score))

    for j in (band.get("judges") or []):
        j_score = j.get("score")
        j_cat   = normalize_field((j.get("category") or "").strip())
        if j_score is None or not j_cat:
            continue
        records.append(_make_record(
            **common,
            category=j_cat,
            score=j_score,
            judge_name=j.get("judge_name"),
            judge_number=j.get("judge_number"),
        ))

    # Deduplicate Total Score records: keep only the single highest-score one.
    # Contemporary sheets often produce spurious Total Score entries from individual
    # judge subcategory rows; the true grand total is always the largest value.
    ts    = [r for r in records if r["category"] == "Total Score"]
    other = [r for r in records if r["category"] != "Total Score"]
    if len(ts) > 1:
        ts = [max(ts, key=lambda r: r.get("score") or 0)]
    return other + ts


# ── Priority queue builder ────────────────────────────────────────────────────

def _build_extraction_queue(
    conn: duckdb.DuckDBPyConnection,
    pdf_dir: Path,
) -> list[tuple[int, Path]]:
    """
    Return [(year, pdf_path)] for all years needing vision extraction.
    A year needs extraction if avg parse_confidence (text-based) < CONFIDENCE_THRESHOLD
    and vision extraction hasn't already reached the threshold.
    """
    try:
        text_rows = conn.execute(f"""
            SELECT year, AVG(parse_confidence)
            FROM {PARSED_SCORES_TABLE}
            WHERE parse_method != 'vision-extracted'
              AND parse_error IS NULL AND band != ''
            GROUP BY year
        """).fetchall()
        text_conf: dict[int, float] = {r[0]: r[1] for r in text_rows}
    except Exception:
        text_conf = {}

    try:
        vision_rows = conn.execute(f"""
            SELECT year, AVG(parse_confidence)
            FROM {PARSED_SCORES_TABLE}
            WHERE parse_method = 'vision-extracted'
            GROUP BY year
        """).fetchall()
        vision_conf: dict[int, float] = {r[0]: r[1] for r in vision_rows}
    except Exception:
        vision_conf = {}

    # Build year → PDF path map from ocr_results
    try:
        ocr_filenames = [r[0] for r in
                         conn.execute("SELECT filename FROM ocr_results WHERE filename IS NOT NULL").fetchall()]
    except Exception:
        return []

    year_to_pdf: dict[int, Path] = {}
    for fn in ocr_filenames:
        yr = _filename_to_year(conn, fn)
        if yr is not None:
            p = pdf_dir / fn
            if p.exists():
                year_to_pdf[yr] = p

    def _needs(yr: int) -> bool:
        # Re-queue only if avg vision confidence is 0 (placeholder-only record)
        # or no vision records exist at all. Confidence > 0 means real data was
        # extracted and the year is done regardless of confidence level.
        if vision_conf.get(yr, 0.0) > 0.0:
            return False
        return text_conf.get(yr, 0.0) < CONFIDENCE_THRESHOLD

    queue: list[tuple[int, Path]] = []

    # Era 1 + era 2 + era 3 in chronological priority
    for yr in list(range(1963, 2014)) + list(range(2014, 2030)):
        if yr in year_to_pdf and _needs(yr):
            queue.append((yr, year_to_pdf[yr]))

    # 1968 always included if not already queued
    if 1968 in year_to_pdf and not any(y == 1968 for y, _ in queue):
        queue.append((1968, year_to_pdf[1968]))

    return queue


# ── Failure placeholder ───────────────────────────────────────────────────────

def _write_failure_placeholder(
    conn: duckdb.DuckDBPyConnection,
    year: int,
    filename: str,
    run_id: str,
) -> None:
    """Write a vision-extracted placeholder so the year isn't re-queued forever."""
    record = _make_record(
        run_id=run_id, year=year, band="", placement=None,
        category="", score=None,
        parse_confidence=0.0, parse_method="vision-extracted",
        source_filename=filename, era=_era(year),
        parse_error="vision-json-parse-failed",
    )
    try:
        conn.execute("BEGIN TRANSACTION")
        _upsert(conn, [record])
        conn.execute("COMMIT")
        log.info("Year %d: failure placeholder written (delete to force re-extraction)", year)
    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        log.warning("Year %d: could not write failure placeholder: %s", year, exc)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_vision_extract(
    conn: duckdb.DuckDBPyConnection,
    pdf_dir: Path,
    api_key_path: str = ANTHROPIC_KEY_PATH_DEFAULT,
    cost_limit: float = COST_GUARD_LIMIT_USD,
    force_vision: bool = False,
) -> dict:
    """
    Extract scores via vision API for all queued years.
    Called from sync.py after parse_scores step; conn must be open.

    cost_limit: abort if estimated run cost exceeds this (default $2.00).
    force_vision: bypass the cost guard (set FORCE_VISION=true in config.env).
    """
    stats: dict = {
        "years_attempted":    0,
        "years_succeeded":    0,
        "years_failed":       0,
        "records_written":    0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "errors":             [],
    }

    try:
        with open(api_key_path) as fh:
            api_key = fh.read().strip()
    except OSError as exc:
        log.error("Cannot read API key from %s: %s", api_key_path, exc)
        stats["errors"].append(f"API key error: {exc}")
        return stats

    client      = anthropic.Anthropic(api_key=api_key)
    ensure_schema(conn)
    known_bands = _get_known_bands(conn)
    main_map    = _get_main_map(conn)
    run_id      = str(uuid.uuid4())
    rate        = _RateLimiter(RATE_LIMIT_PER_MINUTE)

    queue = _build_extraction_queue(conn, pdf_dir)
    if not queue:
        log.info("Vision extraction: all years at confidence ≥ %.1f — nothing to do",
                 CONFIDENCE_THRESHOLD)
        return stats

    log.info("Vision extraction queue: %d year(s) — %s",
             len(queue), [y for y, _ in queue])

    estimated_cost = len(queue) * ESTIMATED_COST_PER_YEAR_USD
    if estimated_cost > cost_limit and not force_vision:
        msg = (
            f"Cost guard: estimated run cost ${estimated_cost:.2f} "
            f"({len(queue)} years × ${ESTIMATED_COST_PER_YEAR_USD:.2f}/year) "
            f"exceeds limit ${cost_limit:.2f}. "
            f"Set FORCE_VISION=true in config.env to proceed."
        )
        log.warning(msg)
        stats["errors"].append(msg)
        return stats
    if estimated_cost > 0:
        log.info("Cost estimate: $%.2f for %d year(s) (limit $%.2f%s)",
                 estimated_cost, len(queue), cost_limit,
                 " — FORCE_VISION active" if force_vision else "")

    for year, pdf_path in queue:
        stats["years_attempted"] += 1
        rate.wait()

        log.info("Vision extracting year %d  file=%s", year, pdf_path.name)

        pages_b64 = _pdf_to_base64_pages(pdf_path)
        if not pages_b64:
            stats["years_failed"] += 1
            stats["errors"].append(f"[{year}] pdf2image failed: {pdf_path.name}")
            continue

        page_results: list[dict] = []
        yr_in, yr_out = 0, 0

        for page_num, page_b64 in enumerate(pages_b64, 1):
            data, in_tok, out_tok = _extract_page(client, year, page_num, page_b64)
            yr_in  += in_tok
            yr_out += out_tok
            if data:
                page_results.append(data)
            if page_num < len(pages_b64):
                time.sleep(2)   # be polite between pages of the same PDF

        cost = (yr_in * _INPUT_COST_PER_MTOK + yr_out * _OUTPUT_COST_PER_MTOK) / 1_000_000
        stats["total_input_tokens"]  += yr_in
        stats["total_output_tokens"] += yr_out
        stats["estimated_cost_usd"]  += cost

        log.info("Year %d: %d/%d page(s) returned data  in=%d out=%d  est=$%.4f",
                 year, len(page_results), len(pages_b64), yr_in, yr_out, cost)

        if not page_results:
            stats["years_failed"] += 1
            stats["errors"].append(f"[{year}] vision API returned no usable data")
            # Only write a failure placeholder for JSON parse errors (yr_in > 0).
            # API/credit errors (yr_in == 0) should remain re-queueable after
            # the underlying issue is fixed.
            if yr_in > 0:
                _write_failure_placeholder(conn, year, pdf_path.name, run_id)
            continue

        merged      = _merge_pages(page_results)
        year_records: list[dict] = []
        for band in merged.get("bands") or []:
            year_records.extend(
                _band_to_records(band, year, pdf_path.name, run_id, main_map, known_bands)
            )

        if not year_records:
            stats["years_failed"] += 1
            stats["errors"].append(f"[{year}] no records generated from merged data")
            continue

        try:
            conn.execute("BEGIN TRANSACTION")
            written = _upsert(conn, year_records)
            conn.execute("COMMIT")

            avg_conf = sum(r["parse_confidence"] for r in year_records) / len(year_records)
            stats["records_written"] += written
            stats["years_succeeded"] += 1
            complete = "✓ COMPLETE" if avg_conf >= CONFIDENCE_THRESHOLD else ""
            log.info("Year %d [%s]: %d records written  avg_confidence=%.2f  %s",
                     year, _era(year), written, avg_conf, complete)
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            msg = f"[{year}] vision upsert failed: {exc}"
            log.error(msg)
            stats["years_failed"] += 1
            stats["errors"].append(msg)

    log.info(
        "Vision complete — attempted=%d succeeded=%d failed=%d "
        "records=%d tokens_in=%d tokens_out=%d cost=$%.4f",
        stats["years_attempted"], stats["years_succeeded"], stats["years_failed"],
        stats["records_written"], stats["total_input_tokens"],
        stats["total_output_tokens"], stats["estimated_cost_usd"],
    )
    return stats
