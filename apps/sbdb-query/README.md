# sbdb-query (LXC 128)

The public AI query API. A CORS-open clone of [`mummster-query`](../mummster-query/) (LXC 125) that the public Gatsby site calls from the browser.

## What's different from mummster-query

- **CORS** — `allow_origins` includes `https://sbdb-ai.theronlab.com`
- **Service name** — `sbdb-query.service` instead of `mummster-query.service`
- **Port** — 8004 instead of 8002
- **Hostname** — fronted by `sbdb-ai-query.theronlab.com` via Cloudflare Tunnel

Everything else (`schema.py`, `pipeline.py`, `pdf_export.py`) is **byte-for-byte identical** to LXC 125 at deploy time.

## Why a clone

1. **Isolation.** If a public misuse pattern stresses the public API, LXC 125 keeps working internally for development.
2. **Future divergence.** Public-facing concerns (rate limiting, per-session IDs, abuse mitigation) belong here. LXC 125 stays simple as the dev environment.

## Files

| File                | Purpose                                              |
|---------------------|------------------------------------------------------|
| `main.py`           | FastAPI server with public CORS                      |
| `schema.py`         | Identical to LXC 125                                 |
| `pipeline.py`       | Identical to LXC 125                                 |
| `pdf_export.py`     | Identical to LXC 125                                 |
| `static/index.html` | Unused at runtime (Gatsby /ask is the public UI); kept as fallback |
| `requirements.txt`  | Same dependencies as LXC 125                         |

## Configuration

- API key: `/etc/artemis-secrets/anthropic.key` (mode 640, owner `root:mummster-data`)
- Data: `/opt/mummster/data/mummster.db` (read-only bind mount, same as LXC 125)
- Port: 8004

## Conversation state

In-process, last 5 exchanges. Currently **shared across all users** — when one user asks a follow-up, they may see context from another user's previous question. Per-session isolation via browser-generated session IDs is the next planned upgrade.

To reset all conversations:
```bash
pct exec 128 -- systemctl restart sbdb-query
```

## Public exposure

```
Browser → sbdb-ai-query.theronlab.com → Cloudflare Tunnel → LXC 128 :8004
```

Cloudflare's "Block Common Exploits" is **disabled** for this hostname because it false-positives on legitimate SQL-shaped strings in the query SSE responses.
