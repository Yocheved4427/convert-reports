"""
Layer 1 – Report type detection.

Analyses OCR output to determine whether a PDF is Type-A (detailed/overtime)
or Type-N (simple monthly).

Strategy:
  • Type-A reports contain "100%", "125%", "150%" in the header row and have
    10+ numeric columns per data row (dates in dd/mm/yyyy format).
  • Type-N reports have fewer columns (≤ 6 numeric values per row), a pay
    summary block at the top, and dates in d/m/yy format.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from src.models import ReportType
from src.ocr_utils import OCRRow, OCRToken, ocr_pdf

logger = logging.getLogger(__name__)

# Keywords that only appear in Type-A (overtime) reports
_OVERTIME_KEYWORDS = {"100%", "125%", "150%"}


def _all_text(rows: List[OCRRow]) -> str:
    """Concatenate all token text into a single string."""
    parts = []
    for row in rows:
        for tok in row.tokens:
            parts.append(tok.text)
    return " ".join(parts)


def _count_numeric_columns(rows: List[OCRRow]) -> float:
    """Average number of numeric-looking tokens per data row (skip first rows)."""
    from src.ocr_utils import is_numeric_token
    counts = []
    for row in rows[3:]:  # skip header rows
        n = sum(1 for t in row.tokens if is_numeric_token(t))
        if n > 0:
            counts.append(n)
    return sum(counts) / len(counts) if counts else 0


def _has_overtime_headers(rows: List[OCRRow]) -> bool:
    """Check if any row contains 100% / 125% / 150% keywords."""
    for row in rows[:8]:  # Only scan header area
        for tok in row.tokens:
            for kw in _OVERTIME_KEYWORDS:
                if kw in tok.text:
                    return True
    return False


def _date_format_hint(rows: List[OCRRow]) -> str:
    """Detect dominant date format: 'long' for dd/mm/yyyy, 'short' for d/m/yy."""
    long_count = 0
    short_count = 0
    for row in rows:
        for tok in row.tokens:
            t = tok.text.strip()
            if re.match(r"\d{2}/\d{2}/\d{4}$", t):
                long_count += 1
            elif re.match(r"\d{1,2}/\d{1,2}/\d{2}$", t):
                short_count += 1
    if long_count > short_count:
        return "long"
    elif short_count > long_count:
        return "short"
    return "unknown"


def detect_report_type(pdf_path: str | Path) -> ReportType:
    """
    Determine the report type from a PDF file.

    Returns ReportType.TYPE_A or ReportType.TYPE_N.
    """
    rows = ocr_pdf(pdf_path)
    full = _all_text(rows)

    has_overtime = _has_overtime_headers(rows)
    avg_cols = _count_numeric_columns(rows)
    date_fmt = _date_format_hint(rows)

    logger.info(
        f"Detection for {Path(pdf_path).name}: "
        f"overtime_headers={has_overtime}, avg_numeric_cols={avg_cols:.1f}, "
        f"date_format={date_fmt}"
    )

    # Decision logic
    if has_overtime or avg_cols >= 7 or date_fmt == "long":
        return ReportType.TYPE_A
    else:
        return ReportType.TYPE_N


def detect_from_rows(rows: List[OCRRow]) -> ReportType:
    """
    Detect type from already-extracted OCR rows (avoids re-OCR).
    """
    has_overtime = _has_overtime_headers(rows)
    avg_cols = _count_numeric_columns(rows)
    date_fmt = _date_format_hint(rows)

    if has_overtime or avg_cols >= 7 or date_fmt == "long":
        return ReportType.TYPE_A
    else:
        return ReportType.TYPE_N
