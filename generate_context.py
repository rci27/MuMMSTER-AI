#!/usr/bin/env python3
"""
Generate a markdown context file summarising the MummSTER DuckDB dataset.

Written to DEFAULT_OUT after each pipeline sync. Loaded by the query
interface's system prompt so Claude has concrete knowledge of the actual data.

Usage: python3 generate_context.py [db_path [out_path]]
"""

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

DEFAULT_DB  = "/opt/mummster/data/mummster.db"
DEFAULT_OUT = "/opt/mummster/data/data_context.md"

GAP_YEARS = {1964, 1967, 1999, 2001, 2021}
ERA_MODERN_START = 1991
ERA_CONTEMPORARY_START = 2014

YEAR_CANDIDATES  = ["year", "Year", "season", "Season", "yr", "Yr"]
BAND_CANDIDATES  = [
    "band", "Band", "band_name", "Band Name", "String Band",
    "string_band", "name", "Name",
]
PLACE_CANDIDATES = [
    "placement", "Placement", "place", "Place",
    "rank", "Rank", "finish", "Finish", "Position", "position",
]
TOTAL_CANDIDATES = [
    "total", "Total", "total_points", "Total Points",
    "score", "Score", "total_score", "Total Score",
]

# Scoring category names in priority order (first match wins)
SCORE_CATEGORIES = [
    "Music Playing", "General Effect Music",
    "Visual Performance", "General Effect Visual",
    "Costume", "Music", "Presentation",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find(cols: list[str], *candidates: str) -> str | None:
    col_map = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in col_map:
            return col_map[cand.lower()]
        # also try snake_case variant
        snake = cand.lower().replace(" ", "_")
        if snake in col_map:
            return col_map[snake]
    return None


def _q(col: str) -> str:
    return f'"{col}"'


def _gap_excl(yc: str) -> str:
    return f'{_q(yc)} NOT IN ({", ".join(str(y) for y in sorted(GAP_YEARS))})'


def _safe(fn, title: str) -> str:
    try:
        return fn()
    except Exception as exc:
        return f"## {title}\n\n_(Could not generate: {exc})_\n"


# ---------------------------------------------------------------------------
# Section generators
# ---------------------------------------------------------------------------

def _overview(conn, yc, bc, pc) -> str:
    row = conn.execute(f"""
        SELECT
            COUNT(DISTINCT {_q(yc)}) AS total_years,
            MIN({_q(yc)})            AS first_year,
            MAX({_q(yc)})            AS last_year,
            COUNT(DISTINCT {_q(bc)}) AS total_bands,
            COUNT(*)                 AS total_records,
            MAX(_synced_at)          AS last_sync
        FROM sbdb_main_results
        WHERE completeness_flag != 'missing'
    """).fetchone()
    total_years, first_year, last_year, total_bands, total_records, last_sync = row
    gap_note = ", ".join(str(y) for y in sorted(GAP_YEARS))
    return (
        "## Dataset Overview\n\n"
        "| Metric | Value |\n|--------|-------|\n"
        f"| Years covered | {first_year}–{last_year} ({total_years} years with data) |\n"
        f"| Unique competing bands | {total_bands} |\n"
        f"| Total records (non-missing) | {total_records:,} |\n"
        f"| Last pipeline sync | {last_sync or 'unknown'} |\n"
        f"| Gap years (no data) | {gap_note} |"
    )


def _first_prizes(conn, yc, bc, pc) -> str:
    rows = conn.execute(f"""
        SELECT {_q(yc)}, {_q(bc)}
        FROM sbdb_main_results
        WHERE {_q(pc)} = 1
            AND completeness_flag != 'missing'
            AND {_gap_excl(yc)}
        ORDER BY {_q(yc)}
    """).fetchall()
    if not rows:
        return "## First Prize Winners\n\n_No first-prize records found._"
    lines = ["## First Prize Winners\n", "| Year | First Prize |\n|------|-------------|"]
    for year, band in rows:
        lines.append(f"| {year} | {band} |")
    return "\n".join(lines)


def _band_records(conn, yc, bc, pc) -> str:
    rows = conn.execute(f"""
        SELECT
            {_q(bc)}                                              AS band,
            COUNT(*)                                              AS appearances,
            SUM(CASE WHEN {_q(pc)} = 1 THEN 1 ELSE 0 END)        AS first_prizes,
            SUM(CASE WHEN {_q(pc)} = 2 THEN 1 ELSE 0 END)        AS second_prizes,
            SUM(CASE WHEN {_q(pc)} <= 3 THEN 1 ELSE 0 END)       AS top3,
            MIN({_q(pc)})                                         AS best_place,
            MAX({_q(pc)})                                         AS worst_place,
            MIN({_q(yc)})                                         AS first_year,
            MAX({_q(yc)})                                         AS last_year
        FROM sbdb_main_results
        WHERE completeness_flag != 'missing'
            AND {_gap_excl(yc)}
        GROUP BY {_q(bc)}
        HAVING COUNT(*) > 5
        ORDER BY first_prizes DESC, appearances DESC
    """).fetchall()
    if not rows:
        return "## Band Records\n\n_No bands with more than 5 appearances._"
    lines = [
        "## Band Records\n",
        "_(Bands with more than 5 appearances, sorted by first-prize wins)_\n",
        "| Band | App. | 1st | 2nd | Top-3 | Best | Worst | Active |",
        "|------|------|-----|-----|-------|------|-------|--------|",
    ]
    for band, app, w1, w2, t3, best, worst, fy, ly in rows:
        lines.append(f"| {band} | {app} | {w1} | {w2} | {t3} | {best} | {worst} | {fy}–{ly} |")
    return "\n".join(lines)


def _era_summaries(conn, yc, bc, pc, tc) -> str:
    era_defs = [
        ("pre-modern",   "Pre-Modern (before 1991)"),
        ("modern",       "Modern (1991–2013)"),
        ("contemporary", "Contemporary (2014–present)"),
    ]
    parts = ["## Era Summaries"]
    for era_val, era_label in era_defs:
        general = conn.execute(f"""
            SELECT
                COUNT(DISTINCT {_q(yc)})  AS years,
                COUNT(DISTINCT {_q(bc)})  AS total_bands,
                ROUND(AVG(bpy), 1)        AS avg_bpy
            FROM (
                SELECT {_q(yc)}, COUNT(DISTINCT {_q(bc)}) AS bpy
                FROM sbdb_main_results
                WHERE era = '{era_val}'
                    AND completeness_flag != 'missing'
                    AND {_gap_excl(yc)}
                GROUP BY {_q(yc)}
            )
        """).fetchone()
        years, total_bands, avg_bpy = general if general else (0, 0, 0)

        top_bands = conn.execute(f"""
            SELECT {_q(bc)},
                SUM(CASE WHEN {_q(pc)} = 1 THEN 1 ELSE 0 END) AS wins,
                COUNT(*) AS apps
            FROM sbdb_main_results
            WHERE era = '{era_val}'
                AND completeness_flag != 'missing'
                AND {_gap_excl(yc)}
            GROUP BY {_q(bc)}
            ORDER BY wins DESC, apps DESC
            LIMIT 5
        """).fetchall()

        lines = [f"\n### {era_label}"]
        lines.append(f"- Years with data: {years}")
        lines.append(f"- Average competing bands per year: {avg_bpy}")
        lines.append(f"- Total unique bands: {total_bands}")
        if top_bands:
            lines.append("- Dominant bands (by first-prize wins):")
            for band, wins, apps in top_bands:
                lines.append(f"  - {band}: {wins} first-prize win(s) in {apps} appearance(s)")
        if tc:
            score_row = conn.execute(f"""
                SELECT
                    ROUND(AVG(TRY_CAST({_q(tc)} AS DOUBLE)), 2)    AS avg,
                    ROUND(STDDEV(TRY_CAST({_q(tc)} AS DOUBLE)), 2) AS std,
                    MIN(TRY_CAST({_q(tc)} AS DOUBLE))              AS mn,
                    MAX(TRY_CAST({_q(tc)} AS DOUBLE))              AS mx
                FROM sbdb_main_results
                WHERE era = '{era_val}'
                    AND completeness_flag != 'missing'
                    AND {_q(tc)} IS NOT NULL
                    AND {_gap_excl(yc)}
            """).fetchone()
            if score_row and score_row[0] is not None:
                avg, std, mn, mx = score_row
                lines.append(f"- Total score: mean={avg}, σ={std}, range={mn}–{mx}")
        parts.append("\n".join(lines))
    return "\n".join(parts)


def _compute_streaks(rows: list[tuple]) -> list[tuple]:
    """
    Given (band, year) pairs, return top streaks as
    (band, streak_length, start_year, end_year), longest first.
    Gap years are treated as transparent (do not break a streak).
    """
    band_years: dict[str, list[int]] = defaultdict(list)
    for band, year in rows:
        try:
            band_years[band].append(int(year))
        except (TypeError, ValueError):
            pass

    streaks = []
    for band, years in band_years.items():
        years = sorted(set(years))
        if not years:
            continue
        run_start = years[0]
        run_len = 1
        for i in range(1, len(years)):
            prev, curr = years[i - 1], years[i]
            gap_only = all(y in GAP_YEARS for y in range(prev + 1, curr))
            if curr - prev == 1 or (curr > prev + 1 and gap_only):
                run_len += 1
            else:
                if run_len > 1:
                    streaks.append((band, run_len, run_start, years[i - 1]))
                run_start = curr
                run_len = 1
        if run_len > 1:
            streaks.append((band, run_len, run_start, years[-1]))

    return sorted(streaks, key=lambda x: -x[1])


def _notable_records(conn, yc, bc, pc) -> str:
    lines = ["## Notable Records\n"]

    most_apps = conn.execute(f"""
        SELECT {_q(bc)}, COUNT(*) AS apps
        FROM sbdb_main_results
        WHERE completeness_flag != 'missing' AND {_gap_excl(yc)}
        GROUP BY {_q(bc)}
        ORDER BY apps DESC LIMIT 5
    """).fetchall()
    if most_apps:
        lines.append("**Most total appearances:**")
        for band, apps in most_apps:
            lines.append(f"- {band}: {apps}")
        lines.append("")

    wins_data = conn.execute(f"""
        SELECT {_q(bc)}, {_q(yc)}
        FROM sbdb_main_results
        WHERE {_q(pc)} = 1
            AND completeness_flag != 'missing'
            AND {_gap_excl(yc)}
        ORDER BY {_q(bc)}, {_q(yc)}
    """).fetchall()
    if wins_data:
        streaks = _compute_streaks(wins_data)
        if streaks:
            lines.append("**Longest first-prize winning streaks:**")
            for band, length, start, end in streaks[:5]:
                yr = f"{start}–{end}" if start != end else str(start)
                lines.append(f"- {band}: {length} consecutive year(s) ({yr})")
            lines.append("")

    top3_data = conn.execute(f"""
        SELECT {_q(bc)}, {_q(yc)}
        FROM sbdb_main_results
        WHERE {_q(pc)} <= 3
            AND completeness_flag != 'missing'
            AND {_gap_excl(yc)}
        ORDER BY {_q(bc)}, {_q(yc)}
    """).fetchall()
    if top3_data:
        top3_streaks = _compute_streaks(top3_data)
        if top3_streaks:
            lines.append("**Longest consecutive top-3 finishes:**")
            for band, length, start, end in top3_streaks[:5]:
                yr = f"{start}–{end}" if start != end else str(start)
                lines.append(f"- {band}: {length} consecutive year(s) ({yr})")
            lines.append("")

    # Most first-prize wins overall
    most_wins = conn.execute(f"""
        SELECT {_q(bc)}, COUNT(*) AS wins
        FROM sbdb_main_results
        WHERE {_q(pc)} = 1
            AND completeness_flag != 'missing'
            AND {_gap_excl(yc)}
        GROUP BY {_q(bc)}
        ORDER BY wins DESC LIMIT 5
    """).fetchall()
    if most_wins:
        lines.append("**Most all-time first-prize wins:**")
        for band, wins in most_wins:
            lines.append(f"- {band}: {wins}")
        lines.append("")

    return "\n".join(lines)


def _data_quality(conn, yc) -> str:
    cf_rows = conn.execute("""
        SELECT completeness_flag, COUNT(*) AS cnt
        FROM sbdb_main_results
        GROUP BY completeness_flag
        ORDER BY cnt DESC
    """).fetchall()

    pdf_years = {
        r[0] for r in conn.execute(f"""
            SELECT DISTINCT {_q(yc)}
            FROM sbdb_main_results
            WHERE data_source = 'pdf-extracted'
                AND completeness_flag != 'missing'
        """).fetchall()
    }

    all_years = {
        r[0] for r in conn.execute(f"""
            SELECT DISTINCT {_q(yc)}
            FROM sbdb_main_results
            WHERE completeness_flag != 'missing'
        """).fetchall()
    }

    src_rows = conn.execute("""
        SELECT data_source, COUNT(*) AS cnt
        FROM sbdb_main_results
        GROUP BY data_source
        ORDER BY cnt DESC
    """).fetchall()

    no_pdf = sorted(all_years - pdf_years - GAP_YEARS)
    lines = ["## Data Quality Summary\n"]

    lines.append("**Completeness breakdown:**")
    for flag, cnt in cf_rows:
        lines.append(f"- `{flag}`: {cnt:,} records")
    lines.append("")
    lines.append(f"**Years with PDF data:** {len(pdf_years)}")
    if no_pdf:
        lines.append(
            f"**Years in DB but missing PDF:** {', '.join(str(y) for y in no_pdf)}"
        )
    lines.append(
        f"**Known gap years (parade not held or no data):** "
        f"{', '.join(str(y) for y in sorted(GAP_YEARS))}"
    )
    lines.append("\n**Data source breakdown:**")
    for src, cnt in src_rows:
        lines.append(f"- `{src}`: {cnt:,} records")

    return "\n".join(lines)


def _score_distributions(conn, yc, cols, score_cols, tc) -> str:
    if not score_cols and not tc:
        return "## Score Distributions\n\n_No score columns detected._"

    all_score: dict[str, str] = dict(score_cols)
    if tc and "Total" not in all_score:
        all_score["Total"] = tc

    era_defs = [
        ("pre-modern",   "Pre-Modern"),
        ("modern",       "Modern"),
        ("contemporary", "Contemporary"),
    ]
    parts = ["## Score Distributions\n"]
    for era_val, era_label in era_defs:
        lines = [f"\n### {era_label}"]
        any_data = False
        for name, col in all_score.items():
            try:
                row = conn.execute(f"""
                    SELECT
                        ROUND(AVG(TRY_CAST({_q(col)} AS DOUBLE)), 2)    AS mean,
                        ROUND(STDDEV(TRY_CAST({_q(col)} AS DOUBLE)), 2) AS std,
                        MIN(TRY_CAST({_q(col)} AS DOUBLE))              AS mn,
                        MAX(TRY_CAST({_q(col)} AS DOUBLE))              AS mx,
                        COUNT(*)                                         AS n
                    FROM sbdb_main_results
                    WHERE era = '{era_val}'
                        AND completeness_flag != 'missing'
                        AND {_q(col)} IS NOT NULL
                        AND TRY_CAST({_q(col)} AS DOUBLE) IS NOT NULL
                        AND {_gap_excl(yc)}
                """).fetchone()
                if row and row[0] is not None and row[4] > 0:
                    mean, std, mn, mx, n = row
                    lines.append(
                        f"- **{name}**: mean={mean}, σ={std}, range={mn}–{mx} (n={n:,})"
                    )
                    any_data = True
            except Exception:
                pass
        if not any_data:
            lines.append("_No numeric score data for this era._")
        parts.append("\n".join(lines))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_context(db_path: str = DEFAULT_DB, out_path: str = DEFAULT_OUT) -> None:
    conn = duckdb.connect(db_path, read_only=True)
    try:
        tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
        if "sbdb_main_results" not in tables:
            Path(out_path).write_text(
                "# MummSTER Data Context\n\n"
                "_No sbdb_main_results table — pipeline has not run yet._\n",
                encoding="utf-8",
            )
            return

        cols = [
            r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'sbdb_main_results' ORDER BY ordinal_position"
            ).fetchall()
        ]

        yc = _find(cols, *YEAR_CANDIDATES)
        bc = _find(cols, *BAND_CANDIDATES)
        pc = _find(cols, *PLACE_CANDIDATES)
        tc = _find(cols, *TOTAL_CANDIDATES)

        if not yc or not bc or not pc:
            Path(out_path).write_text(
                "# MummSTER Data Context\n\n"
                f"_Required columns not found. Available: {cols}_\n",
                encoding="utf-8",
            )
            return

        score_cols: dict[str, str] = {}
        for name in SCORE_CATEGORIES:
            c = _find(cols, name)
            if c:
                score_cols[name] = c

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sections = [f"# MummSTER Data Context\n_Generated {ts}_"]

        sections.append(_safe(lambda: _overview(conn, yc, bc, pc),             "Dataset Overview"))
        sections.append(_safe(lambda: _first_prizes(conn, yc, bc, pc),         "First Prize Winners"))
        sections.append(_safe(lambda: _band_records(conn, yc, bc, pc),         "Band Records"))
        sections.append(_safe(lambda: _era_summaries(conn, yc, bc, pc, tc),    "Era Summaries"))
        sections.append(_safe(lambda: _notable_records(conn, yc, bc, pc),      "Notable Records"))
        sections.append(_safe(lambda: _data_quality(conn, yc),                 "Data Quality"))
        sections.append(_safe(lambda: _score_distributions(conn, yc, cols, score_cols, tc), "Score Distributions"))

        Path(out_path).write_text("\n\n---\n\n".join(sections), encoding="utf-8")
        print(f"[generate_context] Written: {out_path}", flush=True)

    finally:
        conn.close()


if __name__ == "__main__":
    db_arg  = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    out_arg = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    generate_context(db_arg, out_arg)
