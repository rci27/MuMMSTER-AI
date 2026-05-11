# mummster-curation (LXC 126)

The human-in-the-loop point sheet curation tool. Side-by-side view: original PDF on the left, editable data grid on the right.

## Status

**Prototype.** Currently supports 1977 only. Multi-year support is the next significant piece of work — the major challenge is that point sheet formats vary substantially across eras, and the current grid is shaped around the 1977 layout.

## Files

| File                | Purpose                                              |
|---------------------|------------------------------------------------------|
| `main.py`           | FastAPI server — routes for fetch / save / mark-complete |
| `db.py`             | Curation DB layer (separate `curation.db`)           |
| `static/index.html` | Side-by-side PDF + editable grid frontend            |
| `requirements.txt`  | Python dependencies                                  |

## Runtime

- Python 3.11
- FastAPI + Uvicorn
- DuckDB
- Port: 8003

## Data flow

```
parsed_scores (raw extraction)
       │
       │  loaded into curation tool
       ▼
curated_scores_raw (curation.db)
       │
       │  human edits via grid
       ▼
curated_scores (curation.db)
       │
       │  "Mark Complete" promotes the curated overlay
       ▼
sbdb_* tables (mummster.db, authoritative)
```

## Curation features

- Inline column rename (double-click column header)
- Column delete (X button on column hover)
- Band name editing in the first column
- Cell editing throughout
- CSV export preserves column order

## Design philosophy for different formats

The right approach to radically different point sheet formats (1977 vs. 2026 look almost nothing alike) isn't "make one tool handle every format." It's **format-aware templates** — per-era layouts that map the visible point sheet shape to a normalized data model. The current 1977-only tool is the proof-of-concept for one such template.
