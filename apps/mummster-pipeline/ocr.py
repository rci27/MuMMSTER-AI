"""
Extract text from PDFs.
Strategy: try native pdftotext first (fast, lossless for machine-readable PDFs).
Fall back to Tesseract OCR for scanned pages with insufficient extractable text.
Returns structured results with method and confidence score.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFPageCountError

log = logging.getLogger("mummster.ocr")

# Minimum character count to consider pdftotext output "substantial"
_MIN_TEXT_CHARS = 150
_MIN_TEXT_WORDS = 25


def _pdftotext(pdf_path: Path) -> str:
    """Run poppler pdftotext. Returns extracted text or empty string on failure."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("pdftotext unavailable or timed out: %s", exc)
        return ""


def _is_substantial(text: str) -> bool:
    stripped = text.strip()
    word_count = len(stripped.split())
    return len(stripped) >= _MIN_TEXT_CHARS and word_count >= _MIN_TEXT_WORDS


def _pdf_page_count(pdf_path: Path) -> int:
    """Get page count via pdfinfo (poppler). Falls back to 1 on error."""
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if line.lower().startswith("pages:"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    return 1


def _tesseract_page(image) -> tuple[str, float]:
    """OCR a single PIL image. Returns (text, confidence)."""
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config="--psm 6",
    )
    text = pytesseract.image_to_string(image, config="--psm 6")
    confs = [c for c in data["conf"] if isinstance(c, (int, float)) and c >= 0]
    confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return text, confidence


def _ocr_pdf(pdf_path: Path) -> tuple[str, float, int]:
    """
    Convert PDF to images and OCR each page.
    Returns (full_text, mean_confidence, page_count).
    """
    try:
        images = convert_from_path(str(pdf_path), dpi=300)
    except PDFPageCountError as exc:
        log.error("Could not convert %s to images: %s", pdf_path.name, exc)
        return "", 0.0, 0

    texts: list[str] = []
    confs: list[float] = []
    for i, image in enumerate(images, 1):
        page_text, page_conf = _tesseract_page(image)
        texts.append(page_text)
        confs.append(page_conf)
        log.debug("  Page %d/%d confidence=%.2f", i, len(images), page_conf)

    full_text = "\n\n--- PAGE BREAK ---\n\n".join(texts)
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    return full_text, mean_conf, len(images)


def process_pdf(pdf_path: Path, force_tesseract: bool = False) -> dict:
    """
    Extract text from a PDF file.

    When force_tesseract=True, skip pdftotext entirely and go straight to
    Tesseract — used when a previous pdftotext pass returned text that failed
    the OCR quality gate (too few recognizable band names).

    Returns:
        {
            "path": str,
            "filename": str,
            "text": str,
            "method": "pdftotext" | "tesseract",
            "confidence": float,   # 1.0 for pdftotext, 0.0–1.0 for tesseract
            "page_count": int,
            "error": str | None,
        }
    """
    result = {
        "path": str(pdf_path),
        "filename": pdf_path.name,
        "text": "",
        "method": None,
        "confidence": 0.0,
        "page_count": 0,
        "error": None,
    }

    if not pdf_path.exists():
        result["error"] = "file not found"
        return result

    # Try native extraction first (unless force_tesseract bypasses it)
    if not force_tesseract:
        native_text = _pdftotext(pdf_path)
        if _is_substantial(native_text):
            result["text"] = native_text.strip()
            result["method"] = "pdftotext"
            result["confidence"] = 1.0
            result["page_count"] = _pdf_page_count(pdf_path)
            log.info("%-45s  pdftotext  conf=1.00  pages=%d",
                     pdf_path.name, result["page_count"])
            return result
        log.debug("%s: pdftotext yielded %d chars — falling back to Tesseract",
                  pdf_path.name, len(native_text.strip()))
    else:
        log.info("%-45s  force-tesseract (bypassing pdftotext)", pdf_path.name)

    # Tesseract OCR
    try:
        ocr_text, confidence, page_count = _ocr_pdf(pdf_path)
        result["text"] = ocr_text.strip()
        result["method"] = "tesseract"
        result["confidence"] = round(confidence, 4)
        result["page_count"] = page_count
        log.info("%-45s  tesseract  conf=%.2f  pages=%d",
                 pdf_path.name, confidence, page_count)
    except Exception as exc:
        result["error"] = str(exc)
        log.error("OCR failed for %s: %s", pdf_path.name, exc)

    return result


def process_all(pdf_paths: list[Path], already_done: set[str],
                force_tesseract: set[str] | None = None) -> list[dict]:
    """
    OCR all PDFs not already in already_done (set of filenames).
    Files listed in force_tesseract are re-processed with Tesseract even if
    already in already_done — used when the parse quality gate determined that
    a previous pdftotext pass produced unusable text.
    Returns list of result dicts for all newly processed / force-reprocessed files.
    """
    force = force_tesseract or set()

    # Normal pending: not yet done and not force-reprocess
    pending_normal = [p for p in pdf_paths
                      if p.name not in already_done and p.name not in force]
    # Force reprocess regardless of already_done
    force_paths = [p for p in pdf_paths if p.name in force]

    pending = pending_normal + force_paths
    skipped = len(pdf_paths) - len(pending)
    if skipped:
        log.info("Skipping %d already-processed PDFs", skipped)
    if force_paths:
        log.info("Force-reprocessing %d file(s) with Tesseract: %s",
                 len(force_paths), [p.name for p in force_paths])

    results: list[dict] = []
    for i, pdf_path in enumerate(pending, 1):
        is_force = pdf_path.name in force
        log.info("[%d/%d] OCR: %s%s", i, len(pending), pdf_path.name,
                 " (force-tesseract)" if is_force else "")
        results.append(process_pdf(pdf_path, force_tesseract=is_force))

    errors = sum(1 for r in results if r["error"])
    log.info("OCR complete: %d processed, %d errors", len(results), errors)
    return results
