"""
Parser for Type-N reports (simple monthly attendance with pay summary).

Uses a dynamic, position-agnostic approach:
  - Summary block extracted from top rows (numbers before data rows)
  - Data rows identified by d/m/yy date pattern
  - Remaining tokens mapped by type: time → entry/exit, decimal → total hours
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from src.models import TypeNReport, TypeNRow, TypeNSummary
from src.ocr_utils import OCRRow, OCRToken, parse_float, parse_time
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
            # Try to split as d(d)m(m)yy
            fm = _FUZZY_DATE_RE.match(t)
            if fm:
                day, month, year = fm.group(1), fm.group(2), fm.group(3)
                if 1 <= int(day) <= 31 and 1 <= int(month) <= 12:
                    return (i, f"{day}/{month}/{year}")
    return None


# Token kind literal – used as the subject in match/case blocks below.
_TokKind = str   # one of: "date" | "time" | "number" | "text"


def _classify_tok(tok: OCRToken) -> _TokKind:
    """Classify an OCR token into one of four mutually-exclusive kinds.

    Returns a string literal so callers can use ``match kind: case "time": …``
    (structural pattern-matching on string values).
    """
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
    """Parse OCR rows into a TypeNReport."""

    def parse(self, rows: List[OCRRow], pdf_path: str | Path = "") -> TypeNReport:
        header_text = Path(pdf_path).stem if pdf_path else ""

        # ── Find the first data-row y-position to separate summary ──
        first_data_y = None
        for row in rows:
            if _find_date_token(row.tokens):
                first_data_y = row.y_center
                break

        # ── Parse summary block (rows before first data row) ────────
        summary_candidates: List[Tuple[float, float, float]] = []  # (y, x, value)
        if first_data_y is not None:
            summary_cutoff_y = first_data_y - 120
            for row in rows:
                if row.y_center >= summary_cutoff_y:
                    break
                for tok in row.tokens:
                    v = parse_float(tok.text)
                    if v is not None and v >= 1.0:
                        summary_candidates.append((row.y_center, tok.x_center, v))

        # Keep values from the dominant numeric column (same x-alignment)
        selected_summary_vals: List[float] = []
        if summary_candidates:
            x_buckets: List[Tuple[float, int]] = []  # (center_x, count)
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
            aligned = [it for it in summary_candidates if abs(it[1] - dominant_x) <= 80]
            aligned.sort(key=lambda it: it[0])
            selected_summary_vals = [it[2] for it in aligned]

        # Expected order top→bottom in summary block:
        # work_days, total_hours, hourly_rate, total_pay
        work_days = int(selected_summary_vals[0]) if len(selected_summary_vals) >= 1 else 0
        total_hours = selected_summary_vals[1] if len(selected_summary_vals) >= 2 else 0.0
        hourly_rate = selected_summary_vals[2] if len(selected_summary_vals) >= 3 else 0.0
        total_pay = selected_summary_vals[3] if len(selected_summary_vals) >= 4 else 0.0

        if work_days > 0 or total_hours > 0:
            parsed_summary: Optional[TypeNSummary] = TypeNSummary(
                work_days=work_days,
                total_hours=total_hours,
                hourly_rate=hourly_rate,
                total_pay=total_pay,
            )
        else:
            parsed_summary = None

        # ── Parse data rows ─────────────────────────────────────────
        data_rows: List[TypeNRow] = []
        for row in rows:
            tokens = row.tokens  # sorted RTL (highest-x first)
            date_info = _find_date_token(tokens)
            if date_info is None:
                continue

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
                        # time-like but already have 2 → treat as number
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

            # Times: entry (first) and exit (second) in RTL order
            entry_t = parse_time(times[0]) if len(times) >= 1 else ""
            exit_t = parse_time(times[1]) if len(times) >= 2 else ""

            # Total hours: first decimal number
            total_val = numbers[0] if numbers else 0.0

            # Skip empty rows (weekends)
            if not entry_t and not exit_t and total_val == 0:
                continue

            data_rows.append(TypeNRow(
                date=date_str,
                day_of_week=day_of_week,
                entry_time=entry_t or "",
                exit_time=exit_t or "",
                total_hours=total_val,
            ))

        month_year = ""
        if data_rows:
            dm = _SHORT_DATE_RE.search(data_rows[0].date)
            if dm:
                month_year = f"{dm.group(2)}/{dm.group(3)}"

        # If summary not extracted, compute from rows
        if parsed_summary is None and data_rows:
            parsed_summary = TypeNSummary(
                work_days=len([r for r in data_rows if r.total_hours > 0]),
                total_hours=round(sum(r.total_hours for r in data_rows), 2),
                hourly_rate=0,
                total_pay=0,
            )

        report = TypeNReport(
            header_text=header_text,
            month_year=month_year,
            rows=data_rows,
            summary=parsed_summary,
        )

        logger.info(
            f"Type-N parsed: {len(data_rows)} rows, "
            f"month={report.month_year}, "
            f"summary={report.summary}"
        )
        return report
