# Data Quality

An honest assessment of what's reliable in the MummSTER database and what still needs work. This document is the answer to *"can I trust this for serious analysis?"* — and the answer depends on which table you're querying and what you're asking.

---

## TL;DR

| Table family       | Trust level     | Best for                                              |
|--------------------|-----------------|-------------------------------------------------------|
| `sbdb_*`           | **High**        | Placement, wins, prize counts, captains, themes, parade info, awards |
| `parsed_scores`    | **Medium**      | Subcategory scoring trends, judge-level analysis with caveats        |
| `parsed_scores_summary` | **Medium-Low** | Year-level metadata about what was extracted          |

If you're doing serious analysis, default to the `sbdb_*` tables. Reach for `parsed_scores` only when you specifically need the judge-level detail it provides — and then read the caveats below before drawing conclusions.

---

## `sbdb_*` Tables

These are imported from `sbdb.xlsx`, a community-curated workbook maintained outside the system. Every row has been reviewed by humans who know the parade history. The known issues here are mostly cosmetic:

### Band name variations

Most are fixed; a few persist:

- **"Bobby Gagliardi" / "Bobby Gagliardi "** — trailing-space duplicate in some captain queries. Fix: strip whitespace before grouping.
- **"Joe Pomante" / "Joe Pomante "** — same pattern.
- **"Stephen Caldwell" / "Stephen Caldwell "** — same pattern.
- **"Uptown" with embedded non-breaking space** (`\xa0`) in one 2022 record. Fix in source sheet pending.

The merge of "Juniata" (1979–1987) into "Juniata Park" was completed in May 2026. All Juniata records now use the canonical name.

### Asterisk band names

Some band entries have a trailing asterisk (e.g. `"Aqua*"`) indicating a special status — these are intentional, not duplicates. The slug generator on LXC 127 has been updated to handle them, though some edge cases remain.

### Contact data

The `sbdb_band_directory` table currently has some hardcoded entries that should be migrated to a proper sheet tab. Treat this table as "best effort" until that migration completes.

---

## `parsed_scores` Table

This is where the honest caveats live. The pipeline extracts data from 59 point sheet PDFs spanning 1963–2026. Coverage and accuracy are uneven across eras.

### Coverage by era

| Era            | Years        | Coverage | Notes                                                |
|----------------|--------------|----------|------------------------------------------------------|
| Pre-Modern     | 1963–1990    | Good     | Simple formats, text parser works well               |
| Modern         | 1991–2013    | Good     | Standardized categories, both parsers work           |
| Contemporary   | 2014–2026    | Mixed    | New formats; some misidentified Total Score records  |

### Confidence value

The `parsed_scores.confidence` column is currently **flat 0.50 across all years**. The data is broadly correct, but cross-validating extracted totals against `sbdb_main_results` total points is unreliable because the scoring approaches differ across eras (different category weights, different denominators, different rounding rules). So a 0.50 confidence is a placeholder pending judge-level curation, not a signal that the data is wrong.

### Known systematic issues

**1. Contemporary era Total Score mislabeling.** In some 2014–2026 records, the AI vision extractor labeled a subcategory score (e.g. Visual Performance) as the grand total. This produces wrong totals when you sum or compare across years for those records. The fix is per-year curation via the LXC 126 tool.

**2. Duplicate records from multiple pipeline runs.** The deduplication step in `db.py` has a known gap that can leave duplicate `parsed_scores` rows from re-runs. Deduplication by `(year, band, category, judge)` is in the roadmap.

**3. Category name variations.** Mostly handled by `normalize.py`, but new variations show up whenever a previously unprocessed point sheet gets added. Adding a new mapping is a one-line dictionary update.

**4. Field name confusion.** Some columns originally extracted as `"Position"` actually meant marching order; some `"Production"` columns are actually `"Visual Performance"`. These are all in `normalize.py` now, but historical pipeline runs may have written the un-normalized name.

### Gap years (no data extractable)

- **2021** — parade cancelled (COVID-19). MUST be excluded from every multi-year query.
- **1964, 1967, 1999, 2001** — no point sheet available or extraction failed.

The query interface's system prompt enforces these exclusions; ad-hoc SQL queries must add them manually.

---

## Curation Strategy

The long-term plan for getting `parsed_scores` to "high trust" is year-by-year human review via the LXC 126 curation tool. The workflow:

1. Pick a year that needs review (start with contemporary era where issues are concentrated).
2. Open the curation tool — original PDF on the left, editable grid on the right.
3. Fix any extraction errors, rename mis-named columns, fill in gaps.
4. Mark the year complete — the curated overlay supersedes the raw extraction.
5. Promoted curated data lives in `sbdb_*` tables; raw stays in `parsed_scores` for transparency.

This is slow work. There are 59 years to review and the current curation tool only supports 1977 well. Multi-year support is the next major piece of work.

### What "curated" will mean

When a year is fully curated:
- Every band name matches the canonical `sbdb_main_results.Band`
- Every category name uses standard normalized names
- Total Score is verified against the official record
- Judge names are correct
- Any data not extractable from the PDF is explicitly marked as missing rather than absent

A `curation_status` column on `parsed_scores_summary` (planned) will track which years are fully curated, partially curated, or raw-only.

---

## How the Query Interface Handles This

The system prompt in `schema.py` includes explicit guidance about which table to use for which question type. The current rules:

- **Placement / win count / average finish / total points / prize counts:** always use `sbdb_main_results`.
- **Captain history / theme history:** always use `sbdb_main_results`.
- **Subcategory scoring (costume, music, performance breakdowns):** use `parsed_scores`, with mandatory exclusion of 2021 and the parsed_scores gap years (1964, 1967, 1999, 2001).
- **Parade-day facts (weather, mayor, sponsors):** use `sbdb_parade_info`.
- **Awards (Hall of Fame, Lifetime Achievement, etc.):** use the relevant `sbdb_*` award table.

The pipeline has two-level sanity checks: a prompt-side instruction telling the model never to use `parsed_scores` for placement questions, plus a code-side check that catches the case where the model returns rows from a placement query against `parsed_scores` anyway. Both fired together caught a class of "zero rows returned because the wrong table was queried" bugs.

---

## Reporting Issues

If you find a data issue while using the public site or the API:

1. Note the specific record (year, band, what's wrong).
2. Email `rci27@hotmail.com` or open a GitHub issue on this repo.
3. For systematic issues (band name variations, category mislabelings), the fix lives in either `normalize.py` (extraction-time) or `sbdb.xlsx` (canonical data).

A "report an issue" mailto link is on every page of the public site for exactly this purpose.
