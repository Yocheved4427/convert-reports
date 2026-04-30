"""
Parser for Type-A reports (detailed attendance with overtime breakdown).

Implements the four abstract hooks defined by ``BaseParser``'s Template
Method pattern.  The algorithm skeleton (row iteration, header skipping,
report assembly call) lives entirely in ``BaseParser.parse()``; this class
provides only the Type-A–specific steps:

  _is_header_line  – skip rows that contain no long-format date
  _parse_row       – extract one AttendanceRow from a date-bearing OCR row
  _parse_summary   – returns None (summary is built from rows in _build_report)
  _build_report    – compute overtime summary and assemble AttendanceReport
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from src.models import ReportType
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.ocr import OCRRow, OCRToken, parse_float, parse_time
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


# Token kind literal – used as the subject in match/case blocks below.
_TokKind = str   # one of: "date" | "time" | "number" | "text"


def _classify_tok(tok: OCRToken) -> _TokKind:
    """Classify an OCR token into one of four mutually-exclusive kinds."""
    t = tok.text.strip()
    match True:
        case _ if _DATE_LONG_RE.search(t):
            return "date"
        case _ if _TIME_RE.match(t):
            return "time"
        case _ if _DECIMAL_RE.match(t):
            return "number"
        case _:
            try:
                int(t)
                return "number"
            except ValueError:
                return "text"


def _safe_float(raw: str, default: float = 0.0) -> float:
    v = parse_float(raw)
    return v if v is not None else default


class TypeAParser(BaseParser):
    """Type-A concrete parser – implements the four ``BaseParser`` hooks."""

    # ── Hook 1 ────────────────────────────────────────────────────────────────

    def _is_header_line(self, row: OCRRow) -> bool:
        """Skip any OCR row that does not contain a long-format date token.

        Type-A PDFs may include column-header rows, separator rows, or
        summary-label rows that carry no dd/mm/yyyy date.  Returning True
        here causes ``BaseParser.parse()`` to skip the row entirely before
        it reaches ``_parse_row()``.
        """
        return _find_date_token(row.tokens) is None

    # ── Hook 2 ────────────────────────────────────────────────────────────────

    def _parse_row(self, row: OCRRow) -> Optional[AttendanceRow]:
        """Extract one ``AttendanceRow`` from a date-bearing OCR row.

        Token layout (RTL, highest-x first after the date token):
          texts   → [day_of_week, location]
          times   → [entry_time, exit_time]
          numbers → [break, total_hours, hours_100, hours_125, hours_150]
        """
        tokens = row.tokens
        date_info = _find_date_token(tokens)
        if date_info is None:
            return None  # safety guard (should have been caught by _is_header_line)

        date_idx, date_str = date_info
        after_date = tokens[date_idx + 1:]

        times: List[str] = []
        numbers: List[float] = []
        texts: List[str] = []

        for tok in after_date:
            match _classify_tok(tok):
                case "time" if len(times) < 2:
                    times.append(tok.text.strip())
                case "time" | "number":
                    numbers.append(_safe_float(tok.text))
                case "text":
                    texts.append(tok.text.strip())

        # Day of week: text token right before date (if any)
        day_of_week = ""
        for tok in tokens[:date_idx]:
            match _classify_tok(tok):
                case "text" if len(tok.text.strip()) > 1:
                    day_of_week = tok.text.strip()
                    break

        if not day_of_week and texts:
            day_of_week = texts.pop(0)

        # Raw OCR location text – transformer will canonicalise it.
        location = texts[0] if texts else ""

        entry_time = parse_time(times[0]) if len(times) >= 1 else "08:00"
        exit_time  = parse_time(times[1]) if len(times) >= 2 else "15:00"

        # Numbers in RTL order after times:
        # break, total, regular_hours, overtime_125_hours, overtime_150_hours
        break_val = numbers[0] if len(numbers) >= 1 else 0.0
        total_val = numbers[1] if len(numbers) >= 2 else 0.0
        h100      = numbers[2] if len(numbers) >= 3 else 0.0
        h125      = numbers[3] if len(numbers) >= 4 else 0.0
        h150      = numbers[4] if len(numbers) >= 5 else 0.0

        return AttendanceRow(
            date=date_str,
            day_of_week=day_of_week,
            location=location,
            entry_time=entry_time or "08:00",
            exit_time=exit_time  or "15:00",
            break_minutes=break_val,
            total_hours=total_val,
            regular_hours=h100,
            overtime_125_hours=h125,
            overtime_150_hours=h150,
            notes="",
        )

    # ── Hook 3 ────────────────────────────────────────────────────────────────

    def _parse_summary(self, rows: List[OCRRow]) -> Optional[AttendanceSummary]:
        """Type-A PDFs have no pre-built summary block to extract.

        The summary is computed from the fully-parsed data rows inside
        ``_build_report()``, so this hook returns ``None``.
        """
        return None

    # ── Hook 4 ────────────────────────────────────────────────────────────────

    def _build_report(
        self,
        header_text: str,
        data_rows: List[AttendanceRow],
        summary: Optional[AttendanceSummary],
    ) -> AttendanceReport:
        """Compute overtime summary totals and assemble the AttendanceReport."""
        month_year = ""
        if data_rows:
            parts = data_rows[0].date.split("/")
            if len(parts) == 3:
                month_year = f"{parts[1]}/{parts[2]}"

        computed_summary = AttendanceSummary(
            work_days=len(data_rows),
            total_hours=round(sum(r.total_hours for r in data_rows), 2),
            regular_hours=round(sum(r.regular_hours or 0.0 for r in data_rows), 2),
            overtime_125_hours=round(sum(r.overtime_125_hours or 0.0 for r in data_rows), 2),
            overtime_150_hours=round(sum(r.overtime_150_hours or 0.0 for r in data_rows), 2),
        )

        report = AttendanceReport(
            report_type=ReportType.TYPE_A,
            header_text=header_text,
            month_year=month_year,
            rows=data_rows,
            summary=computed_summary,
        )

        logger.info(
            f"Type-A parsed: {len(data_rows)} rows, "
            f"month={report.month_year}, "
            f"total_hours={report.summary.total_hours if report.summary else 0}"
        )
        return report
