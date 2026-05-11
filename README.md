# MummSTER AI

**M**ummers **U**ltimate **M**etrics **M**achine for **S**coring, **T**rends, **E**valuation & **R**eporting — Analytics Interface.

A complete data platform for the Philadelphia Mummers String Band Parade — over a century of competition results, judge-level point sheets, parade-day history, and band records, made queryable through natural language with the help of large language models.

---

## What This Is

The Philadelphia Mummers Parade is one of the oldest folk parades in the United States, with the String Band division competing every January 1st since 1901. Until now, the historical record has lived across scanned PDFs, paper point sheets, scattered spreadsheets, and the memories of band members.

MummSTER AI brings all of that into one place:

- **125 years** of parade-day history (1901–2026)
- **1,960+** main competition results
- **34,000+** judge-level scoring rows extracted from 59 historical point sheet PDFs
- **126** parade-day records with weather, route, mayor, sponsors, media coverage
- **All annual awards** — Hall of Fame, Lifetime Achievement, Custard's Last Stand, Viewer's Choice
- A natural-language query interface powered by Claude that lets anyone ask questions like *"which band has the best average placement since 2000?"* and get back charts, tables, and prose answers — with the SQL shown if you want to see it.

The public site is at **[sbdb-ai.theronlab.com](https://sbdb-ai.theronlab.com)**.

---

## Repo Contents

This repository is the **public documentation and reference source code** for the MummSTER AI system. It is *not* a turnkey deployment — the system runs on a private Proxmox host (ARTEMIS) with a broker-pattern deployment automation that lives in a separate private repo. What you'll find here is everything you need to understand how the system works and to reproduce the architecture on your own infrastructure if you wish.

```
mummster-ai/
├── README.md                          ← you are here
├── LICENSE                            ← MIT
├── docs/
│   ├── ARCHITECTURE.md                ← LXC 124–128, networking, data flow
│   ├── DATA_MODEL.md                  ← every table, every column, era boundaries
│   ├── CODEBASE_OVERVIEW.md           ← file-by-file walkthrough
│   ├── DEPLOYMENT.md                  ← how the broker pattern deploys all five containers
│   ├── DATA_QUALITY.md                ← known issues, curation strategy
│   └── PHASE_LOGS/                    ← chronological build notes
│       ├── PHASE_1_BUILD_LOG.md
│       └── PHASE_2_BUILD_LOG.md
└── apps/
    ├── mummster-pipeline/             ← LXC 124 source — ingestion, OCR, vision AI, DuckDB
    ├── mummster-query/                ← LXC 125 source — internal AI query interface
    ├── mummster-curation/             ← LXC 126 source — point sheet curation tool
    ├── sbdb-frontend/                 ← LXC 127 source — public Gatsby/React site
    └── sbdb-query/                    ← LXC 128 source — public AI query API
```

Each `apps/*` directory contains its own `README.md` with the runtime specifics for that container.

---

## The System at a Glance

Five Linux containers (LXCs) on a single Proxmox host. Each does one thing.

| Container | Name              | Role                                           | Stack                              |
|-----------|-------------------|------------------------------------------------|------------------------------------|
| **124**   | mummster          | Data pipeline + Datasette data viewer          | Python, DuckDB, SQLite, Datasette  |
| **125**   | mummster-query    | Internal natural-language query interface      | FastAPI, Claude API, DuckDB, SSE   |
| **126**   | mummster-curation | Human-in-the-loop point sheet curation tool    | FastAPI, DuckDB                    |
| **127**   | sbdb-frontend     | Public static website                          | Gatsby 5, React 18, nginx          |
| **128**   | sbdb-query        | Public AI query API (clone of 125, CORS-open)  | FastAPI, Claude API, DuckDB, SSE   |

The pipeline (LXC 124) is the source of truth — everything else reads from the DuckDB database it produces.

For a complete walkthrough of the architecture, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## The Data

The data comes from three sources:

1. **A live Google Sheet** (the String Band Database, curated by the Mummers community) — six tabs covering main results, Hall of Fame, parade info, Lifetime Achievement awards, Custard's Last Stand, and Viewer's Choice.
2. **59 historical point sheet PDFs** (1963–2026) — most originally on paper, digitized over the years.
3. **A community-validated Excel workbook** (`sbdb.xlsx`) — twelve tabs of cleaned, canonical records that supersede the raw extracted data.

The pipeline pulls all three sources, runs OCR and Claude Vision API extraction on the PDFs, normalizes field names, and writes everything into a single DuckDB database (`mummster.db`). That database is then exported to SQLite (`datasette.db`) for the Datasette viewer.

For the full data model and known quality issues, see [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) and [`docs/DATA_QUALITY.md`](docs/DATA_QUALITY.md).

---

## The Query Pipeline

When you ask a question on the AI interface, this is what happens:

```
Your question
    │
    ▼
[1] SQL generation
    Claude Sonnet generates DuckDB SQL with extended thinking.
    Schema, era boundaries, gap years, and band-name rules are
    all injected into the system prompt.
    │
    ▼
[2] Validation
    EXPLAIN dry-run against DuckDB. Up to 2 auto-fix attempts
    if the SQL is invalid.
    │
    ▼
[3] Execution
    Query runs read-only against mummster.db. Result is a
    Pandas DataFrame.
    │
    ▼
[4] Interpretation
    Claude Haiku takes the rows and writes a plain-English
    explanation grounded in the actual data.
    │
    ▼
[5] Chart spec
    Claude Haiku decides whether a chart helps, and if so
    emits a Chart.js spec.
    │
    ▼
[6] Refinement
    Claude Haiku suggests one follow-up question.
    │
    ▼
Streamed back to the browser via Server-Sent Events.
```

Model tiering — Sonnet for SQL generation (where reasoning matters), Haiku for the lighter interpretive and formatting steps — keeps responses fast and costs low. The full table of models, token budgets, and thinking budgets is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Try It

The public site is live at **[sbdb-ai.theronlab.com](https://sbdb-ai.theronlab.com)**. Things to try:

- *"Which band has the best average placement since 2000?"*
- *"What were Fralinger's costume scores from 2014 to 2024?"*
- *"How many first prizes has Aqua won? What years?"*
- *"Compare the weather on parade day for the last 20 years."*
- *"Which captains have led the most first-prize bands?"*

Every answer shows the underlying SQL in the thinking panel so you can verify the AI is querying what you think it is.

---

## Why This Exists

There has never been a single place to query a hundred years of Mummers history. The point sheets sat in filing cabinets and scanned-PDF folders. The captain history lived in oral tradition. Researchers, band members, and historians who wanted to ask "what's the longest streak of consecutive top-five finishes?" had no real way to answer it without weeks of manual work.

MummSTER AI is an attempt to fix that — combining the legacy data, the modern tooling, and the kind of natural-language interface that finally makes the archive accessible to people who care about the music and the parade but don't want to write SQL.

---

## Status

The system is **live and functioning** as of May 2026. Phase 1 (data pipeline + Datasette) and Phase 2 (AI query interface + curation tool + public site) are complete. Current focus is on data curation — the parsed point sheet data needs human review year-by-year before it can be considered fully authoritative, especially for the contemporary era (2014–2026) where vision extraction sometimes misidentifies which subcategory score is the grand total.

See [`docs/DATA_QUALITY.md`](docs/DATA_QUALITY.md) for the honest assessment of what's reliable and what still needs work.

---

## Contributing

This is currently a personal project, but if you're a Mummers fan, historian, or band member and you spot a data issue or have records that should be added, open an issue. Corrections to band names, captain attributions, theme details, or any other field are very welcome.

For larger contributions — a new analysis page, an additional table, a different visualization — open an issue first so we can discuss.

---

## Acknowledgments

- **The Philadelphia Mummers community** — for keeping a century of records alive.
- **TJ Ferry and Brian Hamburg** — for stewarding the String Band Database Google Sheet that anchors the modern data.
- **Anthropic** — for the Claude API that powers the natural-language interface and the vision extraction.
- **Simon Willison** — for [Datasette](https://datasette.io/), which made the data viewer trivial to stand up.

---

## License

MIT — see [`LICENSE`](LICENSE).
