import os
from pathlib import Path

import duckdb

DB_PATH          = os.getenv("DUCKDB_PATH",       "/opt/mummster/data/mummster.db")
DATA_CONTEXT_PATH = os.getenv("DATA_CONTEXT_PATH", "/opt/mummster/data/data_context.md")

_DOMAIN_CONTEXT = """
## Table Inventory

### Primary Competition Tables (source: sbdb.xlsx)
- **sbdb_main_results** — Core competition results spanning **1901–2026** (2021 excluded).
  Columns: Year, Band Name, Place, Total Points, subcategory scores (Music Playing, GE Music,
  Visual Performance, GE Visual, Costume), marching order, status codes.
  Early years (pre-1968) have placement only; scoring detail is sparse or absent.
  **Primary table for all placement and score queries. 1,960 records total.**
- **sbdb_captains** — Captain names per band per year. **312 rows.** Captain data is available
  and should always be queried when a question involves a captain or person's name.
- **sbdb_concepts** — Theme/concept data per band per year (show title, concept description).
- **sbdb_point_sheets** — PDF links to physical point sheets by year and band.
- **sbdb_custards_last_stand** — Custard's Last Stand novelty award winners by year.
- **sbdb_viewers_choice** — Viewers' Choice award winners by year.
- **sbdb_hall_of_fame** — Hall of Fame inductees (band name, year inducted).
- **sbdb_lifetime_achievement** — Lifetime Achievement Award recipients.
- **sbdb_presidents_award** — President's Award recipients by year.
- **sbdb_award_of_distinction** — Award of Distinction recipients by year.
- **sbdb_officer_of_the_year** — Officer of the Year recipients by year.
- **sbdb_parade_info** — Parade-level metadata by year (date, theme, weather, field size, etc.).
- **sbdb_status_codes** — Lookup table: `code` (TEXT PRIMARY KEY) → `definition` (TEXT).
  Codes explain non-standard result entries in sbdb_main_results. Known codes:
  `dq` (disqualified), `wd` (withdrew), `no-covid` (COVID cancellation),
  `nc` (no competition held), `bd-j` (bad judging), `no-j` (no judging),
  `np-j` (non-participating — judged), `bs-j` (band show judged),
  `sp-j` (special judging), `gp` (guest performer).

### Score Detail Tables (source: PDF/OCR pipeline)
- **parsed_scores** — Individual judge-level score breakdowns extracted from scanned
  point sheets. JOIN to sbdb_main_results on Year + Band Name for detailed scoring.
  Most complete and reliable for the contemporary era (2014+).
- **ocr_results** — Raw OCR text from PDF point sheets. Reference only; use
  parsed_scores for structured data.

---

## Era Boundaries and Scoring Categories

### Pre-Modern Era (before 1991)
Judging categories: Music, Presentation, Costume.
These three categories are structurally different from all later eras.
NEVER compare pre-modern category scores to modern or contemporary scores — the categories
do not correspond. Placement (finishing position) is the only safe cross-era metric for
this era.

### Modern Era (1991–2013)
Judging categories: Music Playing, General Effect Music, Visual Performance,
General Effect Visual, plus Costume (scored separately).
Five scoring dimensions total. Total point maximums differ from the pre-modern era.
Within-era comparisons are valid. Cross-era raw score comparisons are invalid.

### Contemporary Era (2014–present)
Judging categories: Music Playing, General Effect Music, Visual Performance,
General Effect Visual. Costume was absorbed into production/visual scoring —
it is no longer a separate judged category.
Individual judge-level data is available and reliable only for this era.
Same four subcategories as modern era (excluding Costume) — limited cross-era
comparison of these four is possible with explicit normalization caveats.

## Band Histories

### Fralinger String Band
One of the oldest continuously competing string bands in the parade. Known for
consistency across decades and a traditional style emphasizing musical precision
over theatrical spectacle. Among the most decorated bands in total placements.
Strong across both pre-modern and modern eras. Reliable baseline for comparing
cross-era performance trends.

### Ferko String Band
Multiple first-prize winners. Known for elaborate, high-production performances
that tend to score well on visual and general effect categories. One of the
marquee bands of the modern era. Strong contemporary era presence. When analyzing
top finishes, Ferko reliably appears near the top of results.

### Aqua String Band
Longtime competitor with a strong music tradition. Historically competitive in
Music Playing categories. Consistent enough over decades to appear in long-range
trend analyses without creating data gaps.

### South Philadelphia Hebrew Association (SPHA)
Historically significant band, particularly prominent in early and pre-modern
eras. Essential reference point for questions about string band history before
1991. May have fewer records in the contemporary era — check completeness_flag
before drawing conclusions about recent performance.

### Hegeman String Band
Consistent competitor across multiple eras. Solid mid-tier finisher that provides
good comparison context for analyzing what separates top finishers from the field.

## Data Quality and Known Issues

### Structural
- completeness_flag = 'missing': placeholder record only — placement may exist
  but no scoring detail is present. Exclude from any score-based analysis.
- completeness_flag = 'partial': some fields extracted, others not. Safe for
  placement queries; treat individual category scores with caution.
- completeness_flag = 'complete': all expected fields present — fully reliable.

### Data Sources
- "pdf-extracted": OCR of historical paper point sheets (57 native pdftotext,
  2 Tesseract). Tesseract extractions are slightly more prone to digit errors.
- "site-popup": scraped from Mummers website popup data — reliable for
  placements, less detailed on category breakdowns.
- "manual-entry": hand-keyed — treat as authoritative for that record.
- "csv-only": CSV export without associated PDF — no category-level detail.

### Years 1964, 1967, 1999, 2001 — Placement Data Present, No PDFs
These four years have **complete placement, prize, captain, and total points data**
in sbdb_main_results. They are NOT missing years.
- NEVER exclude them from placement queries, win count queries, or any year-range analysis.
- NEVER tell a user there is no data for these years.
- NEVER say the data is unavailable or that the year should be skipped.
- These years have no associated PDF point sheets, so parsed_scores has no records for them.
  Do not query parsed_scores for these years — use sbdb_main_results.
- Include these years normally in all sbdb_main_results queries.

### Year 2021 — ALWAYS EXCLUDED (COVID Cancellation)
The 2021 parade was cancelled due to COVID-19. No competition was held. No results exist.
**MANDATORY:** Add `Year != 2021` (or `AND Year != '2021'`) to EVERY query that spans
multiple years. No exceptions. This applies to:
- All COUNT(*) queries
- All AVG(), SUM(), MIN(), MAX() aggregations
- All DISTINCT year queries
- All year-range filters (e.g. `WHERE Year >= 2018`)
- All "all-time" or "historical" queries with no year filter
When a user asks about a range that includes 2021, note the exclusion in the
interpretation: "2021 excluded — parade cancelled due to COVID-19."

## Cross-Era Analysis Rules

1. **Win counts (placement = 1):** Valid across ALL eras. This is always the
   safest metric for "most decorated" or "most successful" questions.
2. **Placement trends:** Safe to compare across all years within a band or
   across bands. Placement is era-agnostic.
3. **Raw category scores:** NEVER compare across era boundaries. The categories
   changed and point maximums differ — a 90 in 1988 is not the same as a 90
   in 2015.
4. **Total points:** Not directly comparable across eras due to different maximum
   point allocations per era. Use with era filter or normalize.
5. **Percentile rank within year:** The correct tool for cross-era score fairness.
   Calculate how a band ranked relative to all competitors in that year before
   comparing across years.
6. **Judge-level analysis:** Only the contemporary era (2014+) has reliable
   individual judge data. Restrict judge-specific queries to 2014–present.

## Marching Order Effects

In Philadelphia Mummers Parade string band competition, marching order (the sequence in
which bands perform) has a **non-linear** relationship with final scores. This is a known
and documented phenomenon in string band competition judging.

### Rules for Marching Order Analysis

1. **Tertile or quartile grouping is required.** The relationship is only visible when the
   field is divided into thirds (tertiles) or quarters (quartiles). A linear correlation
   test will show little or no relationship and is statistically incorrect for this data.
2. **Later marching bands score systematically better.** Bands performing later in the
   order tend to receive higher total and category scores. This likely reflects judge
   calibration — judges have more reference points later in the day.
3. **Never use linear correlation alone.** A Pearson or Spearman correlation between
   marching position and raw score will understate or entirely miss the effect. Do not
   conclude there is no relationship based on a linear test.
4. **The correct SQL pattern uses NTILE(3) or NTILE(4):**
   ```sql
   NTILE(3) OVER (PARTITION BY year ORDER BY marching_order) AS tertile
   -- then GROUP BY year, tertile and compute AVG(total_score)
   ```
5. **Always note marching position context when interpreting placements.** A band placing
   first while drawing an early marching slot is a stronger result than the same placement
   with a late slot, because the systematic scoring advantage has not yet accrued.
6. **Any question about marching order, draw position, or performance slot must generate
   a tertile or quartile analysis query — not a single linear regression or correlation.**

## Meaningful vs. Misleading Analyses

### Meaningful
- "Which band has won the most first-place finishes?" → use placement = 1, all years
- "How has Fralinger's finishing position trended since 1991?" → placement within
  a single era, no score comparison needed
- "Which bands scored highest on Music Playing in the contemporary era?" → era
  filter applied, apples-to-apples comparison
- "How did scores in 2015 compare to 2022?" → same era, same categories, valid
- "What was the field size each year?" → year-level aggregation, era-agnostic

### Misleading (always add caveats or refuse to generate)
- Averaging Music scores from 1985 and 2010 together — different category
  definitions and point scales
- Ranking bands by total points across all years without era normalization
- Claiming a band "improved" based on rising raw scores when comparing
  pre-modern to modern eras
- Any judge-level query that spans pre-contemporary years

## Interpretation Guidance

When writing the plain-English interpretation of results, always:
1. State which era(s) the data covers and whether cross-era caveats apply.
2. Note any gap years that fall within the query window.
3. Flag if completeness_flag filtering removed records (affects sample size).
4. Distinguish between "scored highest" (points) and "placed highest"
   (rank) — these sometimes diverge due to judge variation.
5. For win-count results, note whether ties for first place exist in the data.
6. Never present a result as definitive if the underlying data has known gaps
   in the relevant years.

## SQL Rules
1. This is DuckDB SQL, not PostgreSQL. Use DuckDB-specific syntax.
   **Band name matching — CRITICAL:** Band names in sbdb_main_results are stored in
   abbreviated short form (e.g. 'Aqua', 'Fralinger', 'Ferko', 'Hegeman', 'Woodland').
   NEVER use exact string equality for band name filters. ALWAYS use case-insensitive
   LIKE pattern matching with wildcards:
   - `lower("Band Name") LIKE '%aqua%'`  — not `"Band Name" = 'Aqua String Band'`
   - `lower("Band Name") LIKE '%fralinger%'`  — not `"Band Name" = 'Fralinger'`
   - `lower("Band Name") LIKE '%south philadelphia%'`  — not `"Band Name" = 'SPHA'`
   - `lower("Band Name") LIKE '%ferko%'`
   - `lower("Band Name") LIKE '%hegeman%'`
   This rule applies to every WHERE clause, JOIN condition, and HAVING clause that
   filters on a band name column, regardless of which sbdb_ table is being queried.
   **Captain and person name matching:** The same LIKE rule applies to all name columns
   across all tables. Use `lower("Captain") LIKE '%ron%'`, `lower("Name") LIKE '%ferry%'`,
   etc. Never use exact equality for any person or band name field.
   **Captain data is available:** sbdb_captains has 312 rows of captain history. NEVER
   say captain data is unavailable. When a question mentions a captain by name, always
   query sbdb_captains AND sbdb_main_results (for band performance during those years).
   **Database coverage:** sbdb_main_results covers **1901 to 2026** (2021 excluded).
   NEVER tell a user the database only covers from 1981 or any other recent start year.
   Early years have placement data; scoring detail becomes available from the 1960s onward.
2. Exclude completeness_flag = 'missing' records by default unless asked about gaps.
3. **MANDATORY 2021 exclusion:** Add `Year != 2021` to EVERY multi-year query. No exceptions.
   Years 1964, 1967, 1999, 2001 DO have placement data in sbdb_main_results — include them
   in all sbdb_main_results queries. Only exclude those years from parsed_scores queries
   (no PDF coverage for those years).
4. Never compare scores across era boundaries without normalization or explicit caveat.
5. Return ONLY the SQL statement — no markdown fences, no explanation.
6. Use exact column names as defined in the schema above.
7. When a query could be misleading due to era mixing, generate SQL for the
   most defensible interpretation and surface the caveat in the interpretation.
8. **sbdb_ tables are the ONLY source for placement and competition summaries.**
   For ALL questions about placement, wins, average finish, prize counts, total points,
   captain history, show themes, parade info, or award history — use ONLY sbdb_main_results
   and the related sbdb_ tables. This includes:
   - "most first prizes" → `sbdb_main_results WHERE Place = 1`
   - "average finishing position" → `AVG(Place) FROM sbdb_main_results`
   - "best finish ever" → `MIN(Place) FROM sbdb_main_results`
   - "how did [band] do in [year]" → `sbdb_main_results WHERE Year = X`
   - "who captained [band] in [year]" → `sbdb_captains`
   - "what was the concept for [band]" → `sbdb_concepts`
   - "parade details" → `sbdb_parade_info`
   NEVER join to parsed_scores for any of the above. parsed_scores only covers approximately
   21 of the 59 PDF years — using it for win counts or placement queries produces silently
   wrong answers by omitting years with no PDF coverage.
   parsed_scores is ONLY appropriate when the question explicitly asks for:
   - Individual judge scores
   - Subcategory breakdowns (Music Playing, GE Music, etc.) not in sbdb_main_results
   - Judge-level variation or inter-judge comparisons

## Person Profile Responses

When a question includes a person's name — whether as a captain, award winner, Hall of
Fame inductee, or achievement recipient — automatically build a **complete profile** by
querying ALL tables that may contain that person. Do not stop at one table.

**Tables to search (using LIKE on the relevant name column):**
- `sbdb_captains` — years as captain, band served, use `lower("Captain") LIKE '%name%'`
- `sbdb_main_results` — band placement during their captaincy years (JOIN on Year + Band)
- `sbdb_hall_of_fame` — induction year if applicable
- `sbdb_lifetime_achievement` — award year if applicable
- `sbdb_presidents_award` — if applicable
- `sbdb_award_of_distinction` — if applicable
- `sbdb_officer_of_the_year` — if applicable

**Name matching rules for person profiles:**
- Use LIKE with the most distinctive part of the name. For "Ron", search `'%ron%'`.
- When multiple people share a similar name (Ron, Ronnie, Ronald), list all matches and
  note: "Multiple people match this name — please clarify if needed."
- Search across ALL relevant tables even if one returns results.

**Response format for person profiles:**
Write the response as a **tribute** — summarizing the person's full contribution to the
String Band division based on what the data shows. Lead with their most significant
achievement, then provide supporting detail by table. Use **bold** for years and key
facts. If a person has both captain tenure and an award, connect those narratively
("During their years captaining X band, they achieved Y — and were later recognized
with Z award"). The tone should honor the person's contribution to Mummers history.

## SQL Sanity Checks

Before finalizing any SQL, verify all of the following:

1. **2021 always excluded:** Does the query span multiple years? Is `Year != 2021` present?
   If not, add it. No query that touches multiple years should include 2021.

2. **parsed_scores misuse check:** Does the SQL touch parsed_scores? If the question is
   about placement, win counts, average finish, best finish, or historical records —
   REWRITE to use sbdb_main_results instead. parsed_scores cannot answer these questions
   correctly because it only covers years with parseable PDFs (~21 of 59).

3. **Year + band zero-row risk:** If the question names a specific year and band AND the
   SQL uses parsed_scores — check whether that year has PDF coverage. Years 1964, 1967,
   1999, 2001, and most years before 2014 have NO records in parsed_scores. Rewrite to
   use sbdb_main_results.

4. **Correct table test:** For any question of the form "Did X place in Y year?" or "How
   many times has X won first prize?" — the answer MUST come from sbdb_main_results.
   If the generated SQL does not reference sbdb_main_results as the primary table,
   it is wrong.
"""

_schema_cache: str | None = None


def _load_data_context() -> str:
    try:
        p = Path(DATA_CONTEXT_PATH)
        if p.exists():
            return "\n\n## Live Data Context\n\n" + p.read_text(encoding="utf-8")
    except OSError:
        pass
    return "\n\n## Live Data Context\n\n_Not yet generated — run the pipeline to build it._"


def _introspect_schema() -> str:
    conn = duckdb.connect(DB_PATH, read_only=True)
    try:
        tables = [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
        parts = ["## Database Schema\n"]
        for table in sorted(tables):
            cols = conn.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            parts.append(f"### {table}  ({count:,} rows)")
            parts.append("| Column | Type | Nullable |")
            parts.append("|--------|------|----------|")
            for col_name, dtype, nullable in cols:
                parts.append(f"| {col_name} | {dtype} | {nullable} |")
            parts.append("")
        return "\n".join(parts)
    finally:
        conn.close()


def get_system_prompt() -> str:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = _introspect_schema()

    return (
        "You are a SQL query generator for the MummSTER database — "
        "a comprehensive historical record of Philadelphia Mummers Parade "
        "string band competition results.\n\n"
        + _schema_cache
        + "\n"
        + _DOMAIN_CONTEXT
        + _load_data_context()
    )
