"""
Parser for Type-N reports (simple monthly attendance with pay summary).

Implements the four abstract hooks defined by ``BaseParser``'s Template
Method pattern.  The algorithm skeleton lives entirely in
``BaseParser.parse()``; this class provides only the Type-N–specific steps:

  _is_header_line  – always False; non-date rows are discarded by _parse_row
  _parse_row       – extract one AttendanceRow from a date-bearing OCR row
  _parse_summary   – extract the top summary block (work_days / pay figures)
  _build_report    – derive month_year and assemble AttendanceReport

Note: ``_parse_summary`` is called first by the template method, so it can
cache ``self._first_data_y`` for use by the other hooks if needed.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from src.models import ReportType
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.ocr import OCRRow, OCRToken, parse_float, parse_time
from src.parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)

# Short date: d/m/yy or dd/mm/yy or dd/mm/yyyy
_SHORT_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
# Fuzzy date: OCR sometimes drops the slashes → e.g. "30123" = 30/1/23
_FUZZY_DATE_RE = re.compile(r"^(\d{1,2})(\d{1,2})(\d{2})$")
_TIME_RE = re.compile(r"^\d{1,2}[.:;]\d{2}$")
_DECIMAL_RE = re.compile(r"^\d+\.\d+$")


def _find_date_token(tokens: List[OCRToken]) -> Optional[Tuple[int, str]]:
    """Find first short-date token. Returns (index, clean_date).

    Also handles OCR-mangled dates where slashes are dropped
    (e.g. "30123" → "30/1/23").
    """
    for i, tok in enumerate(tokens):
        t = tok.text.strip()
        m = _SHORT_DATE_RE.search(t)
        if m:
            return (i, m.group())
    # Second pass: try fuzzy (no-slash) dates
    for i, tok in enumerate(tokens):
        t = tok.text.strip()
        if len(t) >= 4 and t.isdigit():
            fm = _FUZZY_DATE_RE.match(t)
            if fm:
                day, month, year = fm.group(1), fm.group(2), fm.group(3)
                if 1 <= int(day) <= 31 and 1 <= int(month) <= 12:
                    return (i, f"{day}/{month}/{year}")
    return None


# Token kind literal – used as the subject in match/case blocks below.
_TokKind = str   # one of: "date" | "time" | "number" | "text"


def _classify_tok(tok: OCRToken) -> _TokKind:
    """Classify an OCR token into one of four mutually-exclusive kinds."""
    t = tok.text.strip()
    match True:
        case _ if _SHORT_DATE_RE.search(t):
            return "date"
        case _ if _TIME_RE.match(t):
            return "time"
        case _ if _DECIMAL_RE.match(t):
            return "number"
        case _:
            try:
                float(t.replace(",", ""))
                return "number"
            except ValueError:
                return "text"


def _safe_float(raw: str, default: float = 0.0) -> float:
    v = parse_float(raw)
    return v if v is not None else default


class TypeNParser(BaseParser):
    """Type-N concrete parser – implements the four ``BaseParser`` hooks."""

    # ── Hook 1 ────────────────────────────────────────────────────────────────

    def _is_header_line(self, row: OCRRow) -> bool:
        """Type-N has no explicit header-only rows to skip at this stage.

        Non-date rows (summary labels, blank lines, etc.) are already excluded
        naturally by ``_parse_row()`` returning ``None`` when no date is found.
        """
        return False

    # ── Hook 2 ────────────────────────────────────────────────────────────────

    def _parse_row(self, row: OCRRow) -> Optional[AttendanceRow]:
        """Extract one ``AttendanceRow`` from a date-bearing OCR row.

        Returns ``None`` for rows that have no recognisable date (weekends,
        blank rows, summary lines that slipped through).

        Token layout (RTL, highest-x first after the date token):
          texts   → [day_of_week]
          times   → [entry_time, exit_time]
          numbers → [total_hours]
        """
        tokens = row.tokens
        date_info = _find_date_token(tokens)
        if date_info is None:
            return None

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

        # Day of week: text before date
        day_of_week = ""
        for tok in tokens[:date_idx]:
            match _classify_tok(tok):
                case "text" if len(tok.text.strip()) > 1:
                    day_of_week = tok.text.strip()
                    break

        if not day_of_week and texts:
            day_of_week = texts.pop(0)

        entry_t = parse_time(times[0]) if len(times) >= 1 else None
        exit_t  = parse_time(times[1]) if len(times) >= 2 else None
        total_val = numbers[0] if numbers else 0.0

        # Skip empty rows (weekends / holidays with no clock data)
        if not entry_t and not exit_t and total_val == 0:
            return None

        return AttendanceRow(
            date=date_str,
            day_of_week=day_of_week or None,
            entry_time=entry_t,
            exit_time=exit_t,
            total_hours=total_val,
        )

    # ── Hook 3 ────────────────────────────────────────────────────────────────

    def _parse_summary(self, rows: List[OCRRow]) -> Optional[AttendanceSummary]:
        """Extract the top summary block (before the first data row).

        The dominant numeric column above the first date row is expected to
        contain (top → bottom): work_days, total_hours, hourly_rate, total_pay.

        Also caches ``self._first_data_y`` for callers that need the y-boundary.
        """
        # Find the y-position of the first data row
        first_data_y: Optional[float] = None
        for row in rows:
            if _find_date_token(row.tokens):
                first_data_y = row.y_center
                break
        self._first_data_y = first_data_y  # cache for potential hook use

        if first_data_y is None:
            return None

        summary_cutoff_y = first_data_y - 120
        summary_candidates: List[Tuple[float, float, float]] = []  # (y, x, value)

        for row in rows:
            if row.y_center >= summary_cutoff_y:
                break
            for tok in row.tokens:
                v = parse_float(tok.text)
                if v is not None and v >= 1.0:
                    summary_candidates.append((row.y_center, tok.x_center, v))

        if not summary_candidates:
            return None

        # Keep values from the dominant numeric column (same x-alignment)
        x_buckets: List[Tuple[float, int]] = []
        for _, x, _ in summary_candidates:
            matched = False
            for i, (cx, cnt) in enumerate(x_buckets):
                if abs(x - cx) <= 80:
                    new_cnt = cnt + 1
                    new_cx = (cx * cnt + x) / new_cnt
                    x_buckets[i] = (new_cx, new_cnt)
                    matched = True
                    break
            if not matched:
                x_buckets.append((x, 1))

        dominant_x = max(x_buckets, key=lambda it: it[1])[0]
        aligned = sorted(
            [it for it in summary_candidates if abs(it[1] - dominant_x) <= 80],
            key=lambda it: it[0],
        )
        vals = [it[2] for it in aligned]

        # Expected order top→bottom: work_days, total_hours, hourly_rate, total_pay
        work_days   = int(vals[0]) if len(vals) >= 1 else 0
        total_hours = vals[1]      if len(vals) >= 2 else 0.0
        hourly_rate = vals[2]      if len(vals) >= 3 else 0.0
        total_pay   = vals[3]      if len(vals) >= 4 else 0.0

        if work_days == 0 and total_hours == 0.0:
            return None

        return AttendanceSummary(
            work_days=work_days,
            total_hours=total_hours,
            hourly_rate=hourly_rate,
            total_pay=total_pay,
        )

    # ── Hook 4 ────────────────────────────────────────────────────────────────

    def _build_report(
        self,
        header_text: str,
        data_rows: List[AttendanceRow],
        summary: Optional[AttendanceSummary],
    ) -> AttendanceReport:
        """Derive month_year and assemble the final AttendanceReport.

        When the PDF summary block was absent, a fallback summary is computed
        from the parsed data rows (hourly_rate and total_pay default to 0).
        """
        month_year = ""
        if data_rows:
            dm = _SHORT_DATE_RE.search(data_rows[0].date)
            if dm:
                month_year = f"{dm.group(2)}/{dm.group(3)}"

        # Fallback: compute from rows if no summary was extracted
        if summary is None and data_rows:
            summary = AttendanceSummary(
                work_days=len([r for r in data_rows if r.total_hours > 0]),
                total_hours=round(sum(r.total_hours for r in data_rows), 2),
                hourly_rate=0.0,
                total_pay=0.0,
            )

        report = AttendanceReport(
            report_type=ReportType.TYPE_B,
            header_text=header_text,
            month_year=month_year,
            rows=data_rows,
            summary=summary,
        )

        logger.info(
            f"Type-N parsed: {len(data_rows)} rows, "
            f"month={report.month_year}, "
            f"summary={report.summary}"
        )
        return report
