"""
Download PDFs from public Google Drive share links.
Uses plain HTTP GET only — no authentication or service account.
Skips files that have already been downloaded.
"""

import logging
import re
import time
from pathlib import Path

import gdown
import requests

log = logging.getLogger("mummster.drive")

# Patterns for extracting file IDs from various Drive URL formats
_FILE_ID_PATTERNS = [
    re.compile(r"/file/d/([a-zA-Z0-9_-]+)"),   # /file/d/FILE_ID/
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),     # ?id=FILE_ID or &id=FILE_ID
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),          # /d/FILE_ID
]


def extract_file_id(url: str) -> str | None:
    """Pull the Drive file ID out of any common share URL format."""
    for pattern in _FILE_ID_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def _is_drive_url(url: str) -> bool:
    return "drive.google.com" in str(url) or "docs.google.com" in str(url)


def download_pdf(url: str, dest_dir: Path, filename: str | None = None,
                 skip_existing: bool = True) -> Path | None:
    """
    Download a single PDF from a public Google Drive URL.
    Returns the path to the downloaded file, or None on failure.
    Skips the download if the file already exists and skip_existing is True.
    """
    url = str(url).strip()
    if not url or not _is_drive_url(url):
        log.warning("Skipping non-Drive URL: %s", url)
        return None

    file_id = extract_file_id(url)
    if not file_id:
        log.warning("Could not extract file ID from URL: %s", url)
        return None

    dest_path = dest_dir / (filename or f"{file_id}.pdf")
    if skip_existing and dest_path.exists() and dest_path.stat().st_size > 0:
        log.debug("Already downloaded: %s", dest_path.name)
        return dest_path

    dest_dir.mkdir(parents=True, exist_ok=True)
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    try:
        # gdown handles the virus-scan confirmation page for larger files
        output = gdown.download(
            url=download_url,
            output=str(dest_path),
            quiet=True,
        )
        if output is None:
            log.error("gdown returned None for file_id=%s — file may not be public", file_id)
            return None

        size_kb = dest_path.stat().st_size // 1024
        log.info("Downloaded %-45s  %d KB", dest_path.name, size_kb)
        return dest_path

    except Exception as exc:
        log.error("Failed to download file_id=%s (%s): %s", file_id, url, exc)
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        return None


def find_drive_urls(df, url_cols: list[str] | None = None) -> list[tuple[str, str]]:
    """
    Find Drive URLs in a DataFrame.
    Returns list of (url, suggested_filename) tuples.
    If url_cols not specified, scans all columns whose name suggests a link.
    """
    if url_cols:
        candidates = [c for c in url_cols if c in df.columns]
    else:
        candidates = [
            c for c in df.columns
            if any(kw in c.lower() for kw in ("link", "url", "drive", "pdf", "file"))
        ]

    results: list[tuple[str, str]] = []
    for col in candidates:
        for val in df[col].dropna():
            val = str(val).strip()
            if _is_drive_url(val):
                file_id = extract_file_id(val)
                fname = f"{file_id}.pdf" if file_id else None
                if fname:
                    results.append((val, fname))
    return results


def download_all(urls: list[tuple[str, str]], dest_dir: Path,
                 delay: float = 0.5) -> list[Path]:
    """
    Download all PDFs. urls is a list of (url, filename) pairs.
    Returns list of successfully downloaded paths.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    total = len(urls)

    for i, (url, filename) in enumerate(urls, 1):
        log.info("[%d/%d] %s", i, total, filename)
        path = download_pdf(url, dest_dir, filename=filename)
        if path:
            downloaded.append(path)
        if i < total:
            time.sleep(delay)

    log.info("Downloaded %d / %d PDFs", len(downloaded), total)
    return downloaded
