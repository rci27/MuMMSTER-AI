# mummster-query (LXC 125)

The internal natural-language query interface. FastAPI + Claude API + DuckDB. Six-step query pipeline streamed to the browser via Server-Sent Events.

See [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) for the full query pipeline diagram and model tiering table.

## Files

| File                | Purpose                                              |
|---------------------|------------------------------------------------------|
| `main.py`           | FastAPI web server — routes, CORS, static serving    |
| `schema.py`         | Schema introspection + system prompt assembly        |
| `pipeline.py`       | Query execution engine — six-step SSE generator      |
| `pdf_export.py`     | WeasyPrint PDF generator                             |
| `static/index.html` | Two-panel chat + thinking-panel frontend             |
| `requirements.txt`  | Python dependencies                                  |

## Runtime

- Python 3.11
- FastAPI + Uvicorn
- Anthropic Python SDK
- DuckDB (read-only)
- WeasyPrint (with `libpango`, `libcairo`, etc.)

## Routes

| Method | Path                  | Purpose                                |
|--------|-----------------------|----------------------------------------|
| POST   | `/query`              | Start a new query, returns `query_id`  |
| GET    | `/stream/{query_id}`  | SSE stream of pipeline events          |
| POST   | `/export/{query_id}`  | Generate PDF of completed query        |
| GET    | `/health`             | Health check                           |
| GET    | `/`                   | Static HTML frontend                   |

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
