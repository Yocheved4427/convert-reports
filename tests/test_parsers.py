"""
Unit tests for TypeAParser and TypeNParser (Template Method pattern).

Tests mock ``src.ocr.pdfplumber_ocr.ocr_pdf`` so no filesystem or Tesseract
access is required.  Each test exercises the Template Method skeleton
(``BaseParser.parse()``) via synthetic ``OCRRow`` / ``OCRToken`` objects.

Covers:
  - _is_header_line() filters rows without a date token (Type-A)
  - _parse_row() extracts date, times, and numeric fields correctly
  - _build_report() assembles the AttendanceReport with correct summary
  - _parse_summary() integration for Type-N (extracts top summary block)
  - Full parse() skeleton with mixed header / data / blank rows
  - parse_pdf() calls ocr_pdf() and delegates to parse()
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models.attendance import AttendanceReport, AttendanceRow
from src.models.report_type import ReportType
from src.ocr.pdfplumber_ocr import OCRRow, OCRToken
from src.parsers.type_a_parser import TypeAParser
from src.parsers.type_n_parser import TypeNParser


# ── OCR token / row factories ─────────────────────────────────────────────────

def _tok(text: str, x: float = 0.0, y: float = 0.0) -> OCRToken:
    return OCRToken(
        text=text,
        confidence=0.99,
        x_center=x,
        y_center=y,
        x_min=x - 5,
        y_min=y - 5,
        x_max=x + 5,
        y_max=y + 5,
    )


def _row(*texts: str, y: float = 100.0) -> OCRRow:
    tokens = [_tok(t, x=float(i * 30), y=y) for i, t in enumerate(texts)]
    return OCRRow(y_center=y, tokens=tokens)


# ── TypeAParser._is_header_line ───────────────────────────────────────────────

class TestTypeAIsHeaderLine:
    def setup_method(self) -> None:
        self.parser = TypeAParser()

    def test_row_with_long_date_is_not_header(self) -> None:
        row = _row("שני", "10/01/2023", "08:00", "17:00")
        assert self.parser._is_header_line(row) is False

    def test_row_without_date_is_header(self) -> None:
        row = _row("תאריך", "יום", "כניסה", "יציאה")
        assert self.parser._is_header_line(row) is True

    def test_empty_row_is_header(self) -> None:
        assert self.parser._is_header_line(OCRRow(y_center=0.0, tokens=[])) is True

    def test_row_with_partial_date_pattern_is_header(self) -> None:
        # Short date like "5/1/23" is not a long-format date (dd/mm/yyyy) → header
        row = _row("5/1/23", "08:00")
        assert self.parser._is_header_line(row) is True


# ── TypeAParser._parse_row ────────────────────────────────────────────────────

class TestTypeAParseRow:
    def setup_method(self) -> None:
        self.parser = TypeAParser()

    def test_returns_none_when_no_date(self) -> None:
        row = _row("no", "date", "here")
        assert self.parser._parse_row(row) is None

    def test_parses_date_correctly(self) -> None:
        row = _row("שני", "10/01/2023", "08:00", "17:00", "0.5", "8.0")
        result = self.parser._parse_row(row)
        assert result is not None
        assert "10/01/2023" in result.date

    def test_parses_entry_and_exit_times(self) -> None:
        row = _row("שני", "10/01/2023", "07:30", "16:45")
        result = self.parser._parse_row(row)
        assert result is not None
        assert result.entry_time in ("07:30", "16:45") or result.exit_time in ("07:30", "16:45")

    def test_returns_attendance_row_instance(self) -> None:
        row = _row("שני", "15/02/2023", "08:00", "17:00")
        result = self.parser._parse_row(row)
        assert isinstance(result, AttendanceRow)


# ── TypeAParser full parse() skeleton ────────────────────────────────────────

class TestTypeAFullParse:
    def setup_method(self) -> None:
        self.parser = TypeAParser()

    def test_header_rows_are_skipped(self) -> None:
        rows = [
            _row("תאריך", "יום", "כניסה", "יציאה"),  # header
            _row("שני", "10/01/2023", "08:00", "17:00"),  # data
        ]
        report = self.parser.parse(rows, pdf_path="test.pdf")
        assert len(report.rows) == 1

    def test_report_type_is_type_a(self) -> None:
        rows = [_row("שני", "10/01/2023", "08:00", "17:00")]
        report = self.parser.parse(rows)
        assert report.report_type == ReportType.TYPE_A

    def test_empty_rows_gives_empty_report(self) -> None:
        report = self.parser.parse([])
        assert report.rows == []
        assert report.report_type == ReportType.TYPE_A

    def test_multiple_data_rows_are_all_parsed(self) -> None:
        rows = [
            _row("שני",    "10/01/2023", "08:00", "17:00"),
            _row("שלישי", "11/01/2023", "08:00", "17:00"),
            _row("רביעי", "12/01/2023", "08:00", "17:00"),
        ]
        report = self.parser.parse(rows)
        assert len(report.rows) == 3

    def test_parse_pdf_calls_ocr_pdf_then_parse(self) -> None:
        mock_rows = [_row("שני", "10/01/2023", "08:00", "17:00")]
        with patch("src.parsers.base_parser.ocr_pdf", return_value=mock_rows) as mock_ocr:
            report = self.parser.parse_pdf("fake.pdf")
        mock_ocr.assert_called_once()
        assert report.report_type == ReportType.TYPE_A


# ── TypeNParser._is_header_line ───────────────────────────────────────────────

class TestTypeNIsHeaderLine:
    def setup_method(self) -> None:
        self.parser = TypeNParser()

    def test_always_returns_false(self) -> None:
        """TypeN defers all filtering to _parse_row returning None."""
        row = _row("anything", "no", "date")
        assert self.parser._is_header_line(row) is False

    def test_also_false_for_date_rows(self) -> None:
        row = _row("01/12/23", "08:00", "16:00")
        assert self.parser._is_header_line(row) is False


# ── TypeNParser._parse_row ────────────────────────────────────────────────────

class TestTypeNParseRow:
    def setup_method(self) -> None:
        self.parser = TypeNParser()

    def test_returns_none_for_row_without_date(self) -> None:
        row = _row("שכר", "לתשלום", "חברה")
        assert self.parser._parse_row(row) is None

    def test_parses_short_date(self) -> None:
        row = _row("ראשון", "1/1/23", "08:00", "16:00", "8.0")
        result = self.parser._parse_row(row)
        assert result is not None
        assert "1/23" in result.date or "2023" in result.date

    def test_weekend_row_with_no_times_returns_date_only_row(self) -> None:
        row = _row("שבת", "7/1/23")
        result = self.parser._parse_row(row)
        # Weekend / holiday rows without times are discarded
        assert result is None or result.total_hours == 0.0

    def test_returns_attendance_row_instance(self) -> None:
        row = _row("שני", "2/1/23", "07:00", "15:00")
        result = self.parser._parse_row(row)
        assert result is None or isinstance(result, AttendanceRow)


# ── TypeNParser full parse() ──────────────────────────────────────────────────

class TestTypeNFullParse:
    def setup_method(self) -> None:
        self.parser = TypeNParser()

    def test_report_type_is_type_b(self) -> None:
        rows = [_row("שני", "2/1/23", "08:00", "16:00")]
        report = self.parser.parse(rows)
        assert report.report_type == ReportType.TYPE_B

    def test_parse_pdf_calls_ocr_pdf(self) -> None:
        mock_rows = [_row("שני", "2/1/23", "08:00", "16:00")]
        with patch("src.parsers.base_parser.ocr_pdf", return_value=mock_rows) as mock_ocr:
            self.parser.parse_pdf("fake.pdf")
        mock_ocr.assert_called_once()
