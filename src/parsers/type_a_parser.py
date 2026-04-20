"""
Parser for Type-A reports (detailed attendance with overtime breakdown).

Uses a dynamic, position-agnostic approach:
  - Identifies data rows by finding a date in dd/mm/yyyy format
  - Classifies remaining tokens by type: time, decimal, text
  - Maps tokens by RTL order (after the date):
    text → day/location, times → entry/exit,
    decimals → break, total, 100%, 125%, 150%
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from src.models import TypeAReport, TypeARow, TypeASummary
from src.ocr_utils import OCRRow, OCRToken, parse_float, parse_time
from src.parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)

_DATE_LONG_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
_TIME_RE = re.compile(r"^\d{1,2}[.:;]\d{2}$")
_DECIMAL_RE = re.compile(r"^\d+\.\d+$")


def _find_date_token(tokens: List[OCRToken]) -> Optional[Tuple[int, str]]:
    """Find the first token that looks like dd/mm/yyyy. Returns (index, date)."""
    for i, tok in enumerate(tokens):
        m = _DATE_LONG_RE.search(tok.text.strip())
        if m:
            return (i, m.group())
    return None


def _classify_tok(tok: OCRToken) -> str:
    t = tok.text.strip()
    if _DATE_LONG_RE.search(t):
        return "date"
    if _TIME_RE.match(t):
        return "time"
    if _DECIMAL_RE.match(t):
        return "number"
    try:
        int(t)
        return "number"
    except ValueError:
        pass
    return "text"


def _safe_float(raw: str, default: float = 0.0) -> float:
    v = parse_float(raw)
    return v if v is not None else default


class TypeAParser(BaseParser):
    """Parse OCR rows into a TypeAReport."""

    def parse(self, rows: List[OCRRow], pdf_path: str | Path = "") -> TypeAReport:
        header_text = Path(pdf_path).stem if pdf_path else ""

        data_rows: List[TypeARow] = []

        for row in rows:
            tokens = row.tokens  # sorted RTL (highest‑x first)
            date_info = _find_date_token(tokens)
            if date_info is None:
                continue

            date_idx, date_str = date_info

            # Collect tokens AFTER the date (lower x = columns to the left)
            after_date = tokens[date_idx + 1:]

            times: List[str] = []
            numbers: List[float] = []
            texts: List[str] = []

            for tok in after_date:
                cls = _classify_tok(tok)
                if cls == "time" and len(times) < 2:
                    # Only first 2 time-tokens are entry/exit;
                    # subsequent time-like values (e.g. 00.30 break) → numbers
                    times.append(tok.text.strip())
                elif cls in ("number", "time"):
                    # time-like but we already have 2 times → treat as number
                    numbers.append(_safe_float(tok.text))
                elif cls == "text":
                    texts.append(tok.text.strip())

            # Day of week: text token right before date (if any)
            day_of_week = ""
            for tok in tokens[:date_idx]:
                if _classify_tok(tok) == "text" and len(tok.text.strip()) > 1:
                    day_of_week = tok.text.strip()
                    break

            if not day_of_week and texts:
                day_of_week = texts.pop(0)

            location = texts[0] if texts else ""

            # Times: entry then exit (sorted by descending x → entry first)
            entry_time = parse_time(times[0]) if len(times) >= 1 else "08:00"
            exit_time = parse_time(times[1]) if len(times) >= 2 else "15:00"

            # Numbers in RTL order after times:
            # break, total, hours_100, hours_125, hours_150
            break_val = numbers[0] if len(numbers) >= 1 else 0.0
            total_val = numbers[1] if len(numbers) >= 2 else 0.0
            h100 = numbers[2] if len(numbers) >= 3 else 0.0
            h125 = numbers[3] if len(numbers) >= 4 else 0.0
            h150 = numbers[4] if len(numbers) >= 5 else 0.0

            data_rows.append(TypeARow(
                date=date_str,
                day_of_week=day_of_week,
                location=location,
                entry_time=entry_time or "08:00",
                exit_time=exit_time or "15:00",
                break_minutes=break_val,
                total_hours=total_val,
                hours_100=h100,
                hours_125=h125,
                hours_150=h150,
                notes="",
            ))

        month_year = ""
        if data_rows:
            parts = data_rows[0].date.split("/")
            if len(parts) == 3:
                month_year = f"{parts[1]}/{parts[2]}"

        summary = TypeASummary(
            work_days=len(data_rows),
            total_hours=round(sum(r.total_hours for r in data_rows), 2),
            hours_100=round(sum(r.hours_100 for r in data_rows), 2),
            hours_125=round(sum(r.hours_125 for r in data_rows), 2),
            hours_150=round(sum(r.hours_150 for r in data_rows), 2),
        )

        report = TypeAReport(
            header_text=header_text,
            month_year=month_year,
            rows=data_rows,
            summary=summary,
        )

        logger.info(
            f"Type-A parsed: {len(data_rows)} rows, "
            f"month={report.month_year}, "
            f"total_hours={report.summary.total_hours}"
        )
        return report
