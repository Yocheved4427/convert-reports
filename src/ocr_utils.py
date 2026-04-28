"""
OCR utilities – extract text with bounding boxes from PDF images,
then cluster into rows/columns for structured parsing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Tuple

import pdfplumber
from PIL import Image

logger = logging.getLogger(__name__)

# Singleton reader (model loading is expensive)
_reader: Any | None = None
_reader_error: Exception | None = None


def _get_reader() -> Any:
    global _reader
    global _reader_error

    if _reader_error is not None:
        raise RuntimeError(
            f"EasyOCR is unavailable: {_reader_error}"
        ) from _reader_error

    if _reader is None:
        logger.info("Loading EasyOCR model (first call)…")
        try:
            import easyocr

            _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except Exception as exc:
            _reader_error = exc
            raise RuntimeError(
                f"EasyOCR failed to initialize: {exc}"
            ) from exc
    return _reader


@dataclass
class OCRToken:
    """Single recognised text element with its position."""
    text: str
    confidence: float
    x_center: float
    y_center: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass
class OCRRow:
    """One visual row of tokens (grouped by y-proximity)."""
    y_center: float
    tokens: List[OCRToken] = field(default_factory=list)


def pdf_to_image(pdf_path: str | Path, resolution: int = 200) -> Image.Image:
    """Render the first page of a PDF as a PIL Image."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        return page.to_image(resolution=resolution).original


def ocr_image(image: Image.Image) -> List[OCRToken]:
    """Run OCR on a PIL Image and return tokens."""
    import numpy as np
    reader = _get_reader()
    results = reader.readtext(np.array(image), detail=1)
    tokens: List[OCRToken] = []
    for bbox, text, conf in results:
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        tokens.append(OCRToken(
            text=text.strip(),
            confidence=conf,
            x_center=(min(xs) + max(xs)) / 2,
            y_center=(min(ys) + max(ys)) / 2,
            x_min=min(xs),
            y_min=min(ys),
            x_max=max(xs),
            y_max=max(ys),
        ))
    return tokens


def extract_pdf_words(pdf_path: str | Path) -> List[OCRToken]:
    """Fallback extractor using embedded PDF text positions (no OCR model needed)."""
    tokens: List[OCRToken] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words() or []

    for word in words:
        text = (word.get("text") or "").strip()
        if not text:
            continue
        x_min = float(word["x0"])
        x_max = float(word["x1"])
        y_min = float(word["top"])
        y_max = float(word["bottom"])
        tokens.append(OCRToken(
            text=text,
            confidence=1.0,
            x_center=(x_min + x_max) / 2,
            y_center=(y_min + y_max) / 2,
            x_min=x_min,
            y_min=y_min,
            x_max=x_max,
            y_max=y_max,
        ))

    return tokens


def cluster_into_rows(tokens: List[OCRToken],
                      y_tolerance: float = 18) -> List[OCRRow]:
    """
    Group tokens into rows based on y-coordinate proximity.
    Within each row, tokens are sorted by x descending (RTL → leftmost last).
    """
    if not tokens:
        return []

    sorted_tokens = sorted(tokens, key=lambda t: t.y_center)
    rows: List[OCRRow] = []
    current_row = OCRRow(y_center=sorted_tokens[0].y_center,
                         tokens=[sorted_tokens[0]])

    for tok in sorted_tokens[1:]:
        if abs(tok.y_center - current_row.y_center) <= y_tolerance:
            current_row.tokens.append(tok)
            # Update row y_center as running average
            n = len(current_row.tokens)
            current_row.y_center = (
                current_row.y_center * (n - 1) + tok.y_center
            ) / n
        else:
            rows.append(current_row)
            current_row = OCRRow(y_center=tok.y_center, tokens=[tok])
    rows.append(current_row)

    # Sort tokens within each row by x descending (RTL: rightmost first)
    for row in rows:
        row.tokens.sort(key=lambda t: -t.x_center)

    return rows


def ocr_pdf(pdf_path: str | Path, resolution: int = 200) -> List[OCRRow]:
    """Full pipeline: PDF → image → OCR → clustered rows."""
    logger.info(f"OCR processing: {pdf_path}")
    try:
        img = pdf_to_image(pdf_path, resolution)
        tokens = ocr_image(img)
    except Exception as exc:
        logger.warning(
            "EasyOCR unavailable (%s). Falling back to pdfplumber text extraction.",
            exc,
        )
        tokens = extract_pdf_words(pdf_path)

    rows = cluster_into_rows(tokens)
    logger.info(f"  → {len(tokens)} tokens in {len(rows)} rows")
    return rows


# ── Helpers for numeric extraction ─────────────────────────────────────────────

_TIME_RE = re.compile(r"^(\d{1,2})[.:;](\d{2})$")
_DATE_DMY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$")
_FLOAT_RE = re.compile(r"^-?\d+[.,]\d+$")
_INT_RE = re.compile(r"^\d+$")


def parse_time(raw: str) -> str | None:
    """Normalise a time string to HH:MM.  Returns None if not a time."""
    m = _TIME_RE.match(raw.strip())
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def parse_float(raw: str) -> float | None:
    """Parse a decimal number, accepting both ',' and '.' as separator.
    Strips common OCR artifacts like @ prefix."""
    raw = raw.strip().lstrip("@$ ").replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_date(raw: str) -> str | None:
    """Normalise a date like '2/10/2022' or '02/10/22'.  Returns as-is if ok."""
    m = _DATE_DMY_RE.match(raw.strip())
    if m:
        return raw.strip()
    return None


def is_numeric_token(tok: OCRToken) -> bool:
    """True if the token text looks like a number or time."""
    t = tok.text.strip()
    return bool(_TIME_RE.match(t) or _FLOAT_RE.match(t) or _INT_RE.match(t))
