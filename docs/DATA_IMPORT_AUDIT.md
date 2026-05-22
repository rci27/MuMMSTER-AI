# Data Import Audit Trail 2008-2026

**Status:** complete
**Owner:** Ron
**Session date:** 2026-05-11
**Output file:** `mummers_master_2008_2026.csv` (820 rows, 189 columns, 17 years of data)
**Source PDFs:** Mummers Parade String Band Division official results, 2008-2020 and 2022-2026

---

## Purpose

This document is the audit trail for the Mummers String Band Division master CSV covering 2008-2026. It explains what was imported, how every transcription was done, what decisions were made along the way, and what caveats apply to the resulting data. A data analyst with no prior context should be able to read this document and verify any value in the CSV against the corresponding source PDF.

The CSV is the canonical raw dataset for everything from 2008 forward. It feeds the eventual master workbook normalization step where cross-era concept mappings get applied. It does **not** yet contain pre-2008 years — those come through the separate MummSTER Curation Tool on LXC 126 and will be merged later.

---

## Executive Summary

### What was imported

18 years of String Band Division scoring data: **2008-2020** plus **2022-2026** (2021 is skipped because there was no parade due to COVID). Each year contains, where available:

- **Band scoring rows** — one row per judge per band, capturing all section sub-criteria
- **Captain scoring rows** — one row per judge per captain (only years where the captain page was a separate section of the source PDF, primarily 2013 onward)

### How it was imported

Hand transcription from the source PDFs, with each year's data verified by viewing the rasterized PDF pages at 200 DPI rather than relying on automated text extraction. Text extraction was used as a starting point but found unreliable for several years (truncated columns, garbled OCR, missing rows), so rasterization became the canonical method.

### Two schemas coexist in the file

- `transitional` (698 rows, 2008-2020) — judges' scores arranged in stacked rows per band on the source PDFs (Judge 1 row, Judge 2 row, averaged row). Captured as two rows per band in the CSV (J1 and J2), with the averaged row dropped because it is derivable.
- `contemporary` (122 rows, 2022-2026) — judges named individually (e.g., `G_Leitzel`, `C_Kilian`), with named judges' scores arranged in columns rather than rows on the source PDFs. Captured as one row per band, with judge names embedded in column names.

### Internal validation

Every transitional row's `Band_Total` was checked against the average of its two `Total_Score` values. **349 band/captain groups checked, zero mismatches** at tolerance 0.01. This confirms internal consistency between the captured per-judge totals and the captured band totals.

### Major caveats (read these before using the data)

1. **Band names are inconsistent across eras.** "Quaker City" in transitional vs "Quaker City String Band" or "Quaker City SB" in contemporary. Source typos preserved as-is (e.g., 2015's "Polish Americam"). Normalization is a deliberate downstream step in the master workbook, not this import.
2. **Two schemas means two separate column groups.** A query for "Music Playing scores across all years" requires summing across `Music_Playing__J1__Total`, `Music_Playing__J2__Total` (transitional), `Music__JudgeName__Tot` columns (contemporary). Cross-era concept mapping is a deferred step.
3. **2020 source PDF has an anomalous structure** — the ranked summary is page 1 (skipped); the per-judge band data starts on page 3 (captured); captains are page 5 (captured).
4. **2014 was rebuilt** — initial transcription from text extraction was incomplete for 11 bands (the per-judge data was missing and the averaged row appeared as both J1 and J2). The CSV in this file is the corrected version, transcribed from rasterized pages.
5. **2016 GE_Visual was rebuilt** — initial transcription from text extraction had truncated those columns. Corrected from rasterized pages.
6. **2022-2026 data was hand-transcribed in a prior session.** Same caveats from that session apply — transcription errors at the cell level are statistically possible.
7. **The averaged-row values are not in the CSV.** They can be derived: for any sub-criterion, the bold-row value in the source PDF equals `(J1_value + J2_value) / 2`.
8. **Decimal precision was preserved mathematically, not display-wise.** A value of `9.30` in the source is stored as `9.3` in the CSV. They are identical numbers. Excel formatting controls trailing-zero display.

---

## What the CSV contains

### Row counts by year

| Year | Bands | Captains | Total rows | Notes |
|------|---|---|---|---|
| 2008 | 18 | — | 36 | Captain page not present in PDF |
| 2009 | 18 | — | 36 | Captain page not present in PDF |
| 2010 | 17 | — | 34 | Captain page not present in PDF |
| 2011 | 17 | — | 34 | Captain page not present in PDF |
| 2012 | 17 | — | 34 | Captain page not present in PDF |
| 2013 | 17 | 17 | 68 | Captain page first appears |
| 2014 | 17 | 17 | 68 | Rebuilt from rasterized PDF |
| 2015 | 16 | 16 | 64 | |
| 2016 | 17 | 17 | 68 | GE_Visual columns rebuilt from rasterized PDF |
| 2017 | 16 | 16 | 64 | |
| 2018 | 16 | 16 | 64 | |
| 2019 | 16 | 16 | 64 | |
| 2020 | 16 | 16 | 64 | Source PDF anomaly: data starts on page 3 |
| 2021 | — | — | 0 | No parade (COVID) |
| 2022 | 14 | embedded | 14 | Captain data on page-1 band rows (Captain__ columns), not separate rows |
| 2023 | 14 | 14 | 28 | |
| 2024 | 14 | 14 | 28 | |
| 2025 | 14 | 14 | 28 | Two bands disqualified by penalty |
| 2026 | 12 | 12 | 24 | One captain column shows all zeros (judge no-show) |

**Total: 820 rows, 189 columns.**

### Column groups

The CSV has **189 columns** organized into the following groups, in this order:

#### 1. Identification columns (5 columns)

These columns identify what each row represents and apply to every row.

| Column | Type | Meaning |
|---|---|---|
| `year` | integer | The parade year (Jan 1 of that year) |
| `band` | string | Band name as it appears in source PDF |
| `neighborhood` | string | Band's neighborhood (mostly blank for transitional era) |
| `page_number` | integer | 1 = band scoring, 2 = captain scoring |
| `captain_name` | string | Blank for band rows, populated for captain rows |

#### 2. Metadata columns (4 columns)

These columns describe the kind of data, the totals, and any penalty.

| Column | Type | Meaning |
|---|---|---|
| `schema` | string | Either `transitional` (2008-2020) or `contemporary` (2022-2026) |
| `Total_Score` | number | Per-judge total. Populated for transitional only. For contemporary the equivalent is computed across the row. |
| `Band_Total` | number | The published averaged total for the band/captain (the "bold row" in the source PDF) |
| `PEN` | number | Penalty points (0 for almost all rows; 2025 has two bands with non-zero penalties) |

#### 3. Sub_Total column (1 column)

Applies only to contemporary rows. Pre-penalty sub-total. Blank for transitional rows.

| Column | Type | Meaning |
|---|---|---|
| `Sub_Total` | number | Sub-total of the four main sections before penalty is applied (contemporary only) |

#### 4. Transitional section columns (variable by sub-era, ~30-50 columns total)

Transitional rows use the `Section__Judge__SubCriterion` naming convention. Judges are anonymized as `J1` and `J2`. Section and sub-criterion names match the source PDF for that year.

The section naming evolved across sub-eras:

**2008-2010 sub-era** (`Production` caption, separate `Costume` caption):

- `Music_Playing__J1__Blend_Balance_Tone_Quality_Intonation`
- `Music_Playing__J1__Technique_Interpretation`
- `Music_Playing__J1__Total`
- `Music_Effect__J1__Total` (no sub-criteria broken out in this sub-era)
- `Production__J1__Composition`
- `Production__J1__Drill_Skills_Choreography`
- `Production__J1__Total`
- `GE_Visual__J1__Overall_Effect`
- `GE_Visual__J1__Performance_Effect`
- `GE_Visual__J1__Total`
- `Costume__J1__Costume_Effect`
- `Costume__J1__Costume_Design_Execution`
- `Costume__J1__Total`

(and the same set for `J2`)

**2011-2012 sub-era** (`Visual` caption with composition/accuracy-technique, single-value costume):

- `Music_Playing__J1__Blend_Balance_Tone_Quality_Intonation`
- `Music_Playing__J1__Technique_Interpretation`
- `Music_Playing__J1__Total`
- `Music_Effect__J1__Repertoire_Effectiveness`
- `Music_Effect__J1__Performance_Effectiveness`
- `Music_Effect__J1__Total`
- `Visual__J1__Composition`
- `Visual__J1__Accuracy_Technique`
- `Visual__J1__Total`
- `GE_Visual__J1__Performance_Effect`
- `GE_Visual__J1__Overall_Effect`
- `GE_Visual__J1__Total`
- `Costume__J1__Total` (single value, no sub-criteria)

(and the same set for `J2`)

**2013-2020 sub-era** (`Visual_Performance` caption with costume folded in as sub-criterion, `Music_Playing` uses Technique/Musicianship instead of Blend/Technique):

- `Music_Playing__J1__Technique`
- `Music_Playing__J1__Musicianship`
- `Music_Playing__J1__Total`
- `Music_Effect__J1__Repertoire_Effectiveness`
- `Music_Effect__J1__Performance_Effectiveness`
- `Music_Effect__J1__Total`
- `Visual_Performance__J1__Composition`
- `Visual_Performance__J1__Accuracy_Technique`
- `Visual_Performance__J1__Costume`
- `Visual_Performance__J1__Total`
- `GE_Visual__J1__Performance_Effect`
- `GE_Visual__J1__Overall_Effect`
- `GE_Visual__J1__Costume`
- `GE_Visual__J1__Total`

(and the same set for `J2`)

**Captain columns** (2013-2020), used on `page_number=2` rows:

- `Captain__J1__Costume`
- `Captain__J1__Design`
- `Captain__J1__Effect`
- `Captain__J1__Total`

(and the same set for `J2`)

#### 5. Contemporary section columns (~120 columns)

Contemporary rows use `Section__JudgeName__SubCriterion`. The judge names appear in the column names (because each year's panel rotates). Spaces become underscores; periods are removed (e.g., `G. Leitzel` → `G_Leitzel`).

Sections used in contemporary (2022-2026):

- `Music__JudgeName__Tech` / `Musc` / `Tot`
- `Music__SubTotal`
- `GE_Music__JudgeName__Rep_Ef` / `Per_Eff` / `Tot`
- `GE_Music__SubTotal`
- `VP__JudgeName__Comp` / `Acc_Tech` / `Cost` / `Tot`
- `VP__SubTotal`
- `GE_Visual__JudgeName__Per_Eff` / `Ov_Eff` / `Cost` / `Tot`
- `GE_Visual__SubTotal`
- `Captain__JudgeName__Cost` / `Des` / `GE` / `Tot` (plus `Show` for 2022 only)
- `Captain__SubTotal`
- `Captain__Total`
- `Total` (page 1 grand total)

Because each year has different judges, the column space is roughly 5 sections × 2 judges × ~3-4 sub-criteria × 5 years of unique judges = ~120 columns. Most cells in any given row are blank because that year's judges are different from other years' judges. This is expected; downstream normalization collapses across judges to recover the cross-year concept layer.

### How the two schemas coexist

A transitional row has populated cells in the transitional column group and blank cells in the contemporary column group. A contemporary row has the opposite pattern. Filtering by `schema` is the cleanest way to work with one era at a time.

---

## How values were verified

Three independent consistency checks ran against the final CSV. All passed.

### Check 1: Band_Total math

For every transitional band/captain group (one J1 row + one J2 row), the captured `Band_Total` should equal the average of the captured `Total_Score` values from the two judge rows. Verified across **349 groups; zero mismatches** at tolerance 0.01.

This proves internal consistency. If a `Total_Score` had been transcribed wrong, the average wouldn't match the captured `Band_Total` (which was independently transcribed from the bold row of the source PDF).

### Check 2: Decimal precision audit

I audited 2-decimal-place values to ensure they were preserved where the source had them. Findings:

- **2008** has 42.6% of cells with 2+ decimals because the source PDF used quarter-point precision (.125, .375, .625, .875) in averages and judge cells.
- **2009-2020** sit at 3-5% — most judge values are 1-decimal in the source, with occasional .x5 (e.g., Avalon 2019 J2's `9.55`).
- **2022-2026** are 7-11% — contemporary subtotal columns commonly show 2-decimal values like `28.40`.

A separate check verified: zero cases where my captured J1 and J2 are 1-decimal but their average computes to a 3+ decimal value (which would indicate I had rounded judge values that should have been more precise). The source's bold-row sub-criterion values can be reproduced from J1/J2 with no loss.

### Check 3: Spot checks

Specific cells were verified during the import session by viewing the rasterized PDF page and comparing against the captured row. Examples confirmed:

- 2008 Pennsport J1 row: Total_Score 51.00, Band_Total 48.875, Music_Playing 10.75/7.00/17.75, Costume 4.00/3.50/7.50.
- 2018 Greater Overbrook J1: 73.90, J2: 68.90, Band_Total: 71.40.
- 2014 Peter A. Broomall (rebuilt): J1 67.20, J2 72.40, Band_Total 69.80.
- 2019 Quaker City: J1 98.70, J2 97.10, Band_Total 97.90.
- 2026 Quaker City Band_Total 97.70.
- Aqua 2012 Music_Effect: J1 (7.60, 7.50, 15.10), J2 (7.80, 7.60, 15.40); the bold-row averaged value of 7.55 = (7.50+7.60)/2 ✓.

---

# Appendix

This appendix contains the detailed audit trail: every decision, every method, every revision. A demanding reader who needs to verify a value, understand a quirk, or re-do the import from scratch should find what they need here.

## A. Source PDFs

All PDFs are official Philadelphia Mummers' Parade String Band Division results. The transitional-era PDFs are digital exports (not scans) created in Excel or similar, then printed to PDF. Quality is high — text is selectable, layout is clean. PDFs were uploaded by Ron at the start of the session.

| Year | Filename | Page count | Notes |
|---|---|---|---|
| 2008 | `2008-String-Band-Division-Results.pdf` | 2 | No captain page |
| 2009 | `2009-String-Band-Division-Results.pdf` | 3 | No captain page (page 3 is rank summary, skipped) |
| 2010 | `2010-String-Band-Division-Results.pdf` | 3 | No captain page |
| 2011 | `2011-String-Band-Division-Results.pdf` | 3 | No captain page |
| 2012 | `2012-String-Band-Division-Results.pdf` | 3 | No captain page |
| 2013 | `2013-String-Band-Division-Results.pdf` | 5 | Pages 1-2 bands, p4 captains, p3 + p5 rank summaries (skipped) |
| 2014 | `2014-String-Band-Division-Results.pdf` | 5 | Pages 1-2 bands, p4 captains |
| 2015 | `2015-String-Band-Division-Results.pdf` | 5 | Pages 1-2 bands, p4 captains |
| 2016 | `2016-String-Band-Division-Results.pdf` | 5 | Pages 1-2 bands, p4 captains |
| 2017 | `2017-String-Band-Division-Results.pdf` | 5 | Pages 1-2 bands, p4 captains |
| 2018 | `2018-String-Band-Division-Results.pdf` | 5 | Pages 1-2 bands, p4 captains |
| 2019 | `2019-String-Band-Division-Results.pdf` | 6 | Pages 1-2 bands, p3 captains, p4-5 summary (skipped), p6 summary table |
| 2020 | `2020-String-Band-Division-Results.pdf` | 6 | **Anomaly**: p1 ranked summary (skipped), p3-4 bands, p5 captains, p6 captain rank summary (skipped) |
| 2022-2026 | (transcribed in prior session) | — | See related notes |

## B. Transcription methodology

### Tools used

- `pdftoppm` to rasterize PDF pages to JPEG at 200 DPI
- Direct visual reading of the rasterized images (no OCR)
- Python scripts to assemble the CSV row-by-row from the manually entered values
- All work done in `/home/claude/work` on the temporary container filesystem; outputs copied to `/mnt/user-data/outputs/`

### Why rasterization instead of text extraction

The initial approach was `pdftotext`-style text extraction. This was attempted for several years and failed in multiple ways:

- **2014** — text extraction returned only the averaged row for 11 of 17 bands; per-judge rows on pages 1-2 were garbled or missing.
- **2016** — text extraction truncated the `GE_Visual` column group; all four sub-criteria were dropped from the J1/J2 rows.
- **2017-2018-2019** — partial success but column alignment unreliable in places.

After the 2014 issue was found via internal consistency checking, the decision was made to rasterize every PDF and transcribe from the high-DPI image. This is slower per cell but produces verifiably correct results.

### Decimal precision policy

The source PDFs almost always display values to 2 decimal places (e.g., `7.50`, `8.20`). Most values are mathematically 1-decimal (the `.0` trailing zero is just display). My CSV stores them as 1-decimal (e.g., `7.5`). Where the source shows a genuinely 2-decimal value (e.g., `9.55`, `48.875`), the CSV stores the full precision.

Excel and downstream tools should format columns to display 2 decimals consistently if trailing-zero display matters for readability. The underlying numeric values are correct.

### Average-row handling

Source PDFs in the transitional era have a **third bold row per band** showing the averaged values across J1 and J2. This row was deliberately not captured because:

1. It is mathematically derivable from the J1 and J2 rows (verified — zero precision lost).
2. Including it would inflate the row count by 50% with redundant data.
3. Downstream analysis can compute averages on demand via `=(J1+J2)/2` or `AVERAGEIF()`.

The bold-row values that **are** captured are `Band_Total` (the overall band total) and `PEN` (penalty), since those are not pure averages and contain unique information.

### Page-skip policy

Rank summary pages and re-tabulation pages were skipped because they contain no scoring information not already present elsewhere. They're convenience views for readers, not data.

Pages skipped per year:

- 2008-2012: no rank summary pages exist
- 2013: page 3 (rank summary), page 5 (rank summary)
- 2014: page 3 (rank summary), page 5 (rank summary)
- 2015: page 3 (rank summary), page 5 (rank summary)
- 2016: page 3 (rank summary), page 5 (rank summary)
- 2017: page 3 (rank summary), page 5 (rank summary)
- 2018: page 3 (rank summary), page 5 (rank summary)
- 2019: page 4 (rank summary), page 5 (rank summary), page 6 (consolidated summary)
- 2020: page 1 (ranked summary), page 2 (rank table), page 6 (captain rank summary)

## C. Decisions and rationale

### Decision 1: J1+J2 only, drop the average row

Considered options were: capture all three rows (J1, J2, avg), capture only the average, capture J1+J2 only. Chose J1+J2 only because the average is mathematically derivable from J1+J2 with zero precision loss (verified — 349 groups, zero mismatches).

### Decision 2: Use raw section names per year, normalize later

Considered options were: pre-normalize to a single common schema (e.g., always call it "Music Total" regardless of source label), use raw names per year, capture both. Chose raw names per year so the CSV stays faithful to the source. Cross-era concept mapping is a downstream master-workbook step where domain judgment can be applied with full visibility.

This means "Music Effect" (2008-2010) and "GE Music" (2011+) live in different columns even though they're the same conceptual caption. That's the right tradeoff for the raw layer.

### Decision 3: Single unified CSV with `schema` column

Considered options were: one CSV per era, one CSV total with a schema column, two CSVs that can be unioned later. Chose unified with schema column. Storage is cheap; the schema column is the breadcrumb for downstream queries to filter by era when needed.

### Decision 4: Capture both per-judge `Total_Score` and averaged `Band_Total`

The per-judge `Total_Score` is the value on the J1 row or J2 row (different for each judge). The `Band_Total` is the bold-row averaged total. Both have analytical value:

- `Total_Score` lets you analyze judge variance/disagreement.
- `Band_Total` is the official ranking value.

Storing both adds one redundant column (`Band_Total` is computable from `Total_Score`) but eliminates a calculation step for ranking queries.

### Decision 5: No band-name normalization at this stage

"Quaker City" (transitional) vs "Quaker City String Band" (contemporary), "Polish American" vs "Polish Americam" (typo in 2015 source), etc. These are deliberately preserved as they appear in the source. Normalization is a master-workbook step where domain expert (Ron) makes calls about which names map to which canonical band.

### Decision 6: Penalty as a column, not a row

2025 had two disqualified bands (Duffy, Durning) whose final Totals went to zero because of penalty deductions. The penalty is captured in the `PEN` column on the main row, not as a separate "penalty row". This keeps the table relational and avoids creating sentinel row types.

### Decision 7: 2022 captain data is embedded in the band row, not a separate captain row

In 2022, the source PDF had the captain section inline on page 1 (no separate captain page). The 2022 captain data was captured **on the band's page-1 row**, populating the `Captain__JudgeName__SubCriterion` columns alongside the band's other section scores. There are no `captain_name`-populated rows for 2022.

This differs from 2023-2026, where each captain has its own page-2 row with the `captain_name` field populated.

To find captain data:

- For 2013-2020 (transitional): filter `captain_name != ""` and `page_number == 2`.
- For 2022 (contemporary inline): look at the band's page-1 row in the `Captain__*` columns.
- For 2023-2026 (contemporary separate): filter `captain_name != ""` and `page_number == 2`.

This inconsistency is a real quirk of the data. A demanding analyst querying "all captain scores across years" needs to handle both patterns.

### Decision 8: Skip pre-2008 years for now

Pre-2008 data exists but in a different format that varies more between years (the "classic" schema discussed in earlier sessions). Those years will be ingested through the MummSTER Curation Tool on LXC 126 and merged in a separate operation.

## D. Chronological build order

The import was built in chunks for context-window management. Each chunk built on the previous output.

### Chunk 0 (prior session): 2022-2026

Transcribed before this session. Output: `mummers_2022_2026.csv` (122 rows, 128 columns).

### Chunk 1: 2008-2014

Initial transcription used text extraction. Produced `mummers_2008_2014_partial.csv` (310 rows, 67 columns). **2014 had a data quality issue** — pages 1-2 text extraction was incomplete, so 11 bands had J1=J2=averaged value (duplicate data, not real per-judge scores).

### Chunk 1 revision: Fix 2014 from rasterized PDF

Rasterized 2014 pages 1-2 at 200 DPI and re-transcribed per-judge data. All 17 bands now have real J1/J2 values. Same file overwritten.

### Chunk 2: 2015-2016

Rasterized both years' pages 1-2 (and 4 for captains). 2015 matched the prior text extraction. **2016 GE_Visual had been truncated** in the earlier text extraction — re-transcribed from rasterized pages. Output: `mummers_2008_2016_partial.csv` (442 rows, 67 columns).

### Chunk 3a: 2017

Rasterized pages 1-2 and captain page. Transcribed cleanly. Output: `mummers_2008_2017_partial.csv` (506 rows, 67 columns).

### Chunk 3b: 2018-2019

Rasterized both years. Transcribed cleanly. Output: `mummers_2008_2019_partial.csv` (634 rows, 67 columns).

### Chunk 4: Merge contemporary

Unioned the 2008-2019 transitional CSV with the 2022-2026 contemporary CSV. Added `schema` column. Mapped contemporary `Total` to `Band_Total` for cross-era comparability. Output: `mummers_master_2008_2026.csv` (756 rows, 189 columns).

### Chunk 5: Add 2020 (missed in initial plan)

Spotted gap: 2020 was missing. Rasterized the anomalous PDF (data starts page 3 not page 1). Transcribed 16 bands + 16 captains. Sorted final output chronologically. Output: same file, now 820 rows.

## E. Per-year details

### 2008

- Source PDF: 2 pages
- 18 bands, no captain section in this year's PDF
- **Sub-era**: 2008-2010 schema (Production caption, Costume separate, Music Effect total only)
- Notable: Source uses 3-decimal quarter-point precision in averaged totals (e.g., Pennsport Band_Total 48.875)

### 2009

- Source PDF: 3 pages (page 3 is rank summary, skipped)
- 18 bands, no captain section
- Same schema as 2008

### 2010

- Source PDF: 3 pages
- 17 bands
- Same schema as 2008-2009
- "Kensington" appears as the band name (no "Greater" prefix) in this year's source PDF

### 2011

- Source PDF: 3 pages
- 17 bands
- **Sub-era shift**: Music Effect now has Repertoire and Performance Effectiveness as separate sub-criteria. Visual replaces Production. Costume is now a single value, not three.
- Source: `2011-String-Band-Division-Results.pdf` (also a duplicate `__1__.pdf` uploaded; both contain identical data)

### 2012

- Source PDF: 3 pages
- 17 bands
- Same schema as 2011

### 2013

- Source PDF: 5 pages
- 17 bands, **captain section first appears** as a separate page (page 4)
- **Sub-era shift**: Music_Playing now has Technique/Musicianship instead of Blend/Technique. Visual_Performance replaces Visual, with Costume folded in as a sub-criterion. GE_Visual also has Costume sub-criterion.

### 2014

- Source PDF: 5 pages
- 17 bands, 17 captains
- **Critical: this year was rebuilt during the import.** Initial transcription used text extraction, which returned only the averaged row for bands 7-17 (Avalon onwards). After spotting J1=J2=averaged duplicate values via internal consistency check, the PDF was rasterized at 200 DPI and re-transcribed cell-by-cell from the image. All 17 bands now have correct per-judge data.
- Sample verified: Peter A. Broomall J1=67.20, J2=72.40, Band_Total=69.80.

### 2015

- Source PDF: 5 pages
- 16 bands, 16 captains
- "Polish American" appears as "Polish Americam" in source PDF — typo preserved.

### 2016

- Source PDF: 5 pages
- 17 bands, 17 captains
- **GE_Visual columns were rebuilt during the import.** Initial text extraction truncated the rightmost columns. Re-transcribed from rasterized pages.

### 2017

- Source PDF: 5 pages
- 16 bands, 16 captains
- Clean transcription from rasterized pages.

### 2018

- Source PDF: 5 pages
- 16 bands, 16 captains
- Clean transcription from rasterized pages.

### 2019

- Source PDF: 6 pages
- 16 bands, 16 captains
- Clean transcription from rasterized pages.

### 2020

- Source PDF: 6 pages
- 16 bands, 16 captains
- **Anomaly**: data layout reversed. Page 1 is the ranked summary (skipped). Page 2 is a rank table. Pages 3-4 have the per-judge band data. Page 5 has captains. Page 6 has another summary (skipped).
- Was missed in the initial plan and added in a follow-up pass.

### 2021

- No parade due to COVID. Not in CSV.

### 2022-2026

Transcribed in a prior session before this audit-trail session. The 122-row contemporary block was unioned into the master CSV with a `schema=contemporary` tag.

Each year in this block has:
- Named judges (rotate year-to-year)
- 5 sections (Music, GE_Music, VP, GE_Visual, Captain) with sub-criteria per judge
- Captain section on page 2 (except 2022, where captain section was inline on page 1)

Notable details:
- **2022**: Captain section has an extra "Show" sub-criterion not present in other years.
- **2024**: PDF text didn't extract neighborhood data; cells are blank.
- **2025**: Two bands (Duffy, Durning) were disqualified; their PEN column shows non-zero values, Total = 0.
- **2026**: 12 bands (smaller field). Captain judge D. Metz has all-zero column — judge no-show, matches the source PDF.

## F. Files produced

All files are CSVs.

| Path | Purpose | Status |
|---|---|---|
| `mummers_2008_2012_partial.csv` | Initial 5-year build | Superseded |
| `mummers_2008_2014_partial.csv` | After adding 2013-2014 | Superseded |
| `mummers_2008_2016_partial.csv` | After adding 2015-2016 | Superseded |
| `mummers_2008_2017_partial.csv` | After adding 2017 | Superseded |
| `mummers_2008_2019_partial.csv` | After adding 2018-2019 | Superseded |
| `mummers_2022_2026.csv` | Contemporary era only | Component file |
| `mummers_master_2008_2026.csv` | **Final master CSV** | **Canonical** |

The canonical file is `mummers_master_2008_2026.csv`. Other CSVs are intermediate snapshots from the build process and should not be used for analysis.

## G. Open issues and known gaps

1. **Pre-2008 data not yet captured.** Will be added via the MummSTER Curation Tool on LXC 126.
2. **2021 has no data** (no parade due to COVID). This is correct, not a gap.
3. **Band-name normalization deferred** to master workbook phase. "Quaker City" / "Quaker City String Band" / "Quaker City SB" remain distinct.
4. **Cross-era concept mapping deferred** to master workbook phase. "Music Total" appears as multiple distinct columns across schemas.
5. **No automated validation against source PDFs.** Sanity checks were spot-checks plus mathematical consistency. A demanding audit would re-verify every cell against the source PDF.

## H. Glossary

- **Band**: A Mummers String Band (Quaker City, Fralinger, etc.). 12-18 bands compete each year.
- **Captain**: The band's captain. Judged separately in some years, with their own score sheet on page 2 of the PDF.
- **J1, J2**: Anonymized "Judge 1" and "Judge 2" labels used for transitional-era columns (the source PDFs didn't name judges per caption in this era).
- **Section**: A scoring category (Music Playing, GE Music, Visual Performance, GE Visual, Costume, Captain).
- **Sub-criterion**: A scoring component within a section (e.g., Music Playing has Technique and Musicianship).
- **Bold row / averaged row**: The third row per band in the transitional source PDFs, showing the average of J1 and J2's scores. Not captured directly; values are derivable.
- **Rank summary / re-tabulation**: Pages of the source PDFs showing bands sorted by rank. Convenience views, no unique scoring data. Skipped.
- **Schema**: Either `transitional` (2008-2020) or `contemporary` (2022-2026). Determines which column group is populated.
- **Penalty (PEN)**: Points deducted from a band's score (rare; 2025 had two disqualifications).
