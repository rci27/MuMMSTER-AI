"""
Fetch public Google Sheets tabs via the gviz CSV endpoint.
No authentication required — sheets must be publicly readable.
"""

import io
import logging
import time

import pandas as pd
import requests

log = logging.getLogger("mummster.sheets")

GVIZ_URL = (
    "https://docs.google.com/spreadsheets/d/{sheet_id}"
    "/gviz/tq?tqx=out:csv&gid={gid}"
)

# Tab names → GID mapping; populated at runtime from config
TAB_GIDS: dict[str, str] = {}

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "mummster-pipeline/1.0"


def _fetch_tab(sheet_id: str, gid: str, name: str) -> pd.DataFrame:
    url = GVIZ_URL.format(sheet_id=sheet_id, gid=gid)
    log.debug("Fetching tab %r from %s", name, url)
    resp = _SESSION.get(url, timeout=30)
    resp.raise_for_status()

    # gviz CSV sometimes wraps the entire response in a google.visualization
    # callback — detect and strip it if present
    text = resp.text
    if text.startswith("google.visualization"):
        # Not expected for tqx=out:csv, but guard anyway
        raise ValueError(f"Unexpected JSONP response for tab {name!r}")

    df = pd.read_csv(io.StringIO(text), dtype=str)

    # Drop fully empty rows and columns that gviz sometimes pads
    df.dropna(how="all", inplace=True)
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
    df.columns = [c.strip() for c in df.columns]

    log.info("Tab %-28s %4d rows  %d cols", f"{name!r}", len(df), len(df.columns))
    return df


def fetch_all(sheet_id: str, tab_gids: dict[str, str],
               retry: int = 3, backoff: float = 2.0) -> dict[str, pd.DataFrame]:
    """Fetch every tab in tab_gids. Returns {tab_name: DataFrame}."""
    results: dict[str, pd.DataFrame] = {}
    for name, gid in tab_gids.items():
        for attempt in range(1, retry + 1):
            try:
                results[name] = _fetch_tab(sheet_id, gid, name)
                break
            except Exception as exc:
                if attempt == retry:
                    log.error("Tab %r failed after %d attempts: %s", name, retry, exc)
                    raise
                wait = backoff ** attempt
                log.warning("Tab %r attempt %d failed (%s) — retrying in %.0fs",
                            name, attempt, exc, wait)
                time.sleep(wait)
    return results
