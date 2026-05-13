# mummster-query (LXC 125)

The internal natural-language query interface. FastAPI + Claude API + DuckDB. Six-step query pipeline streamed to the browser via Server-Sent Events.

See [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) for the full query pipeline diagram and model tiering table.

## Files

| File                    | Purpose                                                          |
|-------------------------|------------------------------------------------------------------|
| `main.py`               | FastAPI web server — routes, CORS, static serving                |
| `schema.py`             | Schema introspection + system prompt assembly                    |
| `pipeline.py`           | Query execution engine — six-step SSE generator                  |
| `pdf_export.py`         | WeasyPrint PDF generator for query results                       |
| `personal_stats.py`     | Computes career statistics for a named marcher across bands/years |
| `certificate.py`        | Generates a WeasyPrint "Certificate of Marching Service" PDF     |
| `generate_context.py`   | Introspects `mummster.db` and writes `data_context.md`           |
| `static/index.html`     | Two-panel chat + thinking-panel frontend                         |
| `static/personal.html`  | Personal marching history lookup and stats form                  |
| `static/user-submitted-records.html` | Public browse/filter view of user-submitted records |
| `requirements.txt`      | Python dependencies                                              |

## Runtime

- Python 3.11
- FastAPI + Uvicorn
- Anthropic Python SDK
- DuckDB (read-only)
- WeasyPrint (with `libpango`, `libcairo`, etc.)

## Routes

| Method | Path                              | Purpose                                                  |
|--------|-----------------------------------|----------------------------------------------------------|
| POST   | `/query`                          | Start a new query, returns `query_id`                    |
| GET    | `/stream/{query_id}`              | SSE stream of pipeline events                            |
| POST   | `/export/{query_id}`              | Generate PDF of completed query                          |
| GET    | `/health`                         | Health check                                             |
| GET    | `/`                               | Static HTML frontend                                     |
| GET    | `/personal`                       | Personal marching history page                           |
| GET    | `/api/bands-for-year/{year}`      | List competing bands for a given year                    |
| GET    | `/api/theme/{year}/{band}`        | Theme and placement for a year/band                      |
| POST   | `/api/calculate-stats`            | Compute career stats for a named marcher; returns token  |
| POST   | `/api/save-submission`            | Persist a user's marching history to `user_submissions.db` |
| GET    | `/api/certificate/{token}`        | Generate Certificate of Marching Service PDF             |
| GET    | `/api/share-card/{token}`         | Generate 1200×630 PNG share card                         |
| GET    | `/api/marched-with/{year}/{band}` | List all bands that competed the same year               |
| GET    | `/user-submitted-records`         | User-submitted records browse page                       |
| GET    | `/api/user-submitted-records`     | Paginated, filterable API for submitted records          |

## Configuration

- API key: `/etc/artemis-secrets/anthropic.key` (mode 640, owner `root:mummster-data`)
- Data: `/opt/mummster/data/mummster.db` (read-only bind mount from host)
- Port: 8002

## Conversation state

In-process only — the last 5 exchanges live in a Python dict. Nothing is written to disk. Restarting the service clears history for everyone. Per-session isolation is in the Phase 3 roadmap.

## Model configuration

| Step           | Model                         | Tokens | Thinking budget |
|----------------|-------------------------------|--------|-----------------|
| SQL generation | `claude-sonnet-4-6`           | 8,000  | 5,000           |
| SQL auto-fix   | `claude-sonnet-4-6`           | 4,000  | —               |
| Interpretation | `claude-haiku-4-5-20251001`   | 1,500  | —               |
| Chart spec     | `claude-haiku-4-5-20251001`   | 1,500  | —               |
| Refinement     | `claude-haiku-4-5-20251001`   | 200    | —               |
