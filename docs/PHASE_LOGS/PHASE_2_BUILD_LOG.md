# MummSTER — Phase 2 Build Log

**Status:** Complete (May 2026)
**Covers:** LXC 125 (internal query), LXC 126 (curation), LXC 127 (public site), LXC 128 (public query API)

---

## What Phase 2 Built

Phase 1 made the data queryable. Phase 2 made it accessible — first to the developer (LXC 125), then to data curators (LXC 126), then to the public (LXC 127 + 128).

| Container | Name              | Purpose                                              | Public? |
|-----------|-------------------|------------------------------------------------------|---------|
| LXC 125   | mummster-query    | Internal natural-language query interface            | No      |
| LXC 126   | mummster-curation | Point sheet curation tool                            | No      |
| LXC 127   | sbdb-frontend     | Public Gatsby/React static site                      | Yes     |
| LXC 128   | sbdb-query        | Public AI query API (clone of 125, CORS-open)        | Yes     |

---

## LXC 125 — mummster-query

The first real AI surface. FastAPI + Claude API + DuckDB. Multi-step pipeline: SQL generation → validation → execution → interpretation → chart → refinement. SSE streaming to the browser. PDF export. Two-panel UI with a live thinking panel showing pipeline state.

**Model tiering** (added late Phase 2):
- SQL generation: Claude Sonnet 4.6 with 8k tokens and 5k thinking budget
- SQL auto-fix: Claude Sonnet 4.6 with 4k tokens, no thinking
- Interpretation / chart / refinement: Claude Haiku 4.5

This was a significant cost/latency improvement. Earlier versions used Sonnet for everything; moving the lighter steps to Haiku cut per-query cost by roughly 60% with no observable quality drop.

**Key architectural decision:** the schema introspection runs once at startup, but the system prompt is rebuilt per-request from `schema.py`. This means every query gets the latest `data_context.md` injected without needing a service restart when the pipeline regenerates context.

**Conversation memory:** in-process dict, last 5 exchanges, no persistence. Restarting the service clears history for everyone. Per-session isolation via browser-generated session IDs is in the Phase 3 roadmap.

---

## LXC 126 — mummster-curation

A prototype tool for human-in-the-loop point sheet correction. Side-by-side view: PDF on left, editable data grid on right. Inline column rename, column delete, cell edit, band name fix. CSV export in column order.

**Current scope:** 1977 only. The 1977 point sheets have a consistent format that the tool was built around. Multi-year support is the next significant piece of curation work — it requires handling radically different formats (the 2026 point sheet bears almost no resemblance to the 1977 one).

**Design philosophy for radically different formats:** the right approach isn't to make one tool handle every format — it's to make the tool format-aware, with per-era templates that map the visible layout to a normalized data shape.

---

## LXC 127 — sbdb-frontend

A Gatsby 5 + React 18 static site. Pages:

- **Home** — hero, latest year results table with YouTube thumbnails, AI teaser, stats bar
- **Results** — all-years results browser with year selector
- **Bands** — grid with filter and search
- **Band detail** (`/bands/[slug]`) — placement history chart, full history table
- **Captain detail** (`/captains/[slug]`) — 311 auto-generated pages, sortable history
- **Parade** — four-card layout per year: parade day facts, annual awards, Hall of Fame, competition awards
- **Search** — cross-table global search
- **Ask** — AI query interface (calls LXC 128)

**Color scheme:** dark navy charcoal background (`#0f1720`) with gold accents (`#c8a84b`). Playfair Display headings, Source Sans 3 body. Archival record aesthetic.

**Build-time data fetching:** `gatsby-node.js` fetches all 8 tables (results + 6 award tables + parade info) from LXC 124's Datasette JSON API during `npm run build`. After build, every page is plain HTML — no runtime database calls.

**Favicon and logos:** sourced from `mummers.github.io/stringbands`. Aqua's logo currently has a black background; transparent PNG pending.

---

## LXC 128 — sbdb-query

A CORS-open clone of LXC 125. Same source code at deploy time, two differences:
- CORS `allow_origins` includes `https://sbdb-ai.theronlab.com`
- Service unit renamed `sbdb-query.service`, port 8004

Same bind mount, same secrets pattern (`/etc/artemis-secrets/anthropic.key`), same six-step query pipeline.

**Why a clone:** isolation. If a public misuse pattern stresses the public API, LXC 125 keeps working internally. Future public-facing changes (rate limiting, per-session IDs, abuse mitigation) belong on LXC 128 only.

---

## Notable Fixes During Phase 2

### SQL routing rules (schema.py)

A class of bugs where the AI would query `parsed_scores` for placement questions. `parsed_scores` only covers ~21 of 59 years for placement, so queries silently returned wrong win counts.

Fix: a four-part change to `schema.py` + `pipeline.py`:
1. **1964/1967/1999/2001 gap years:** explicitly told the model these years exist in `sbdb_main_results` and to never exclude them or claim data is unavailable.
2. **2021 mandatory exclusion:** elevated from "note the gap" to a hard rule. `Year != 2021` must appear in every multi-year query.
3. **sbdb_* for competition summaries:** expanded list — placement, wins, average finish, prize counts, total points, captain history, themes, parade info, awards. Seven question patterns enumerated with the correct table.
4. **Two-level sanity check:** prompt-side rule + code-side check. Code-side catches placement queries against `parsed_scores` that returned rows (wrong answer, not zero rows).

### Band name fixes

Juniata (1979–1987) and Juniata Park (1988+) were merged into "Juniata Park" across all `sbdb_main_results` records. This required a one-off DuckDB UPDATE and a re-export to SQLite for Datasette.

### Multi-sub-query complexity

Early versions of the pipeline aggressively decomposed questions into era-specific sub-queries even for simple averages. Fix: an added rule in `schema.py` telling the model to use a single query against `sbdb_main_results` for simple aggregations unless the user explicitly asks for an era breakdown.

### Vision extraction max_tokens

Some complex modern-era point sheets were truncating JSON output mid-array. Fix: bumped `max_tokens` in `vision_extract.py` to handle the worst-case responses, plus a JSON recovery fallback that attempts to parse a truncated response by adding `]}` or similar closing brackets and seeing if the result parses.

### Normalization dictionary

Moved field-name normalization out of both parsers into a shared `normalize.py`. Both `parse_scores.py` and `vision_extract.py` import from the same dictionary. Adding a new variation is a one-line update.

---

## Phase 2 Outcomes

- Two AI query surfaces live (internal + public)
- Static public site with 8 distinct page types
- ~311 auto-generated captain pages
- Curation tool prototype proving the workflow
- Model tiering live (Sonnet for reasoning, Haiku for formatting)
- All known SQL routing bugs fixed
- Juniata merge complete
- Documentation in this repo

---

## Phase 2 Outstanding Items

- **Multi-year curation tool** — currently 1977-only. Format-aware templates needed.
- **Per-session conversation isolation** on LXC 128 — currently all users share global conversation state.
- **Backup verification for LXC 127 and 128** — confirm they're in the Proxmox vzdump job and the Synology mirror scope.
- **Asterisk band deduplication edge cases** — slug fix applied but some cases remain.
- **Uptown non-breaking space** in 2022 — fix in source sheet.
- **Aqua logo transparent PNG** — currently has black background.
- **Parade History "View Results" button** doesn't pass year param — links to `/results` instead of `/results?year=X`.

---

## Phase 3 Roadmap (Not Yet Started)

- Year-by-year point sheet curation via multi-format curation tool
- Raw scores table — store everything extracted exactly as found
- Curated scores table — only confirmed data, fed to analytics
- Field dictionary — maps raw field names to standard names with provenance
- Annotations table — domain expert notes on specific records
- CSV import pipeline for bulk manual corrections
- Web search integration for MummSTER AI (cite recent news / context)
- Statistical analysis layer — Monte Carlo simulation, change-point detection, era comparisons
- Public band contact directory migrated from hardcoded to a sheet tab
- Comprehensive Obsidian documentation write-up for non-technical stewards
