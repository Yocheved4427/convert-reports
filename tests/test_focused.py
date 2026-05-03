"""
Focused tests for:

  1. ValidatingStrategyDecorator — delegation and invalid-row detection
  2. TransformationService       — fallback on TransformationError
  3. ParserFactory               — registry dispatch and unknown-type guard
  4. CLI smoke test              — main() end-to-end with all I/O mocked

These tests do not duplicate any coverage already present in
test_validating_decorator.py, test_transformation_service.py, or
test_parsers.py.  They add the specific scenarios called out in the spec.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Inject stub modules so src.parsers (and src.ocr) can be imported ─────────
# pdfplumber, PIL, and easyocr are not installed in the dev environment.
# The stubs allow all imports to resolve without the real packages.

def _ensure_stubs() -> None:
    if "pdfplumber" not in sys.modules:
        sys.modules["pdfplumber"] = types.ModuleType("pdfplumber")
    if "PIL" not in sys.modules:
        pil = types.ModuleType("PIL")
        img = types.ModuleType("PIL.Image")
        img.Image = MagicMock()  # type: ignore[attr-defined]
        pil.Image = img  # type: ignore[attr-defined]
        sys.modules["PIL"] = pil
        sys.modules["PIL.Image"] = img
    if "easyocr" not in sys.modules:
        sys.modules["easyocr"] = types.ModuleType("easyocr")


_ensure_stubs()

# ── Domain / application imports (after stubs) ───────────────────────────────
from src.exceptions import TransformationError, UnsupportedReportTypeError
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.models.report_type import ReportType
from src.parsers.parser_factory import ParserFactory
from src.parsers.type_a_parser import TypeAParser
from src.parsers.type_b_parser import TypeBParser
from src.parsers.type_n_parser import TypeNParser
from src.services.transformation_service import TransformationService
from src.strategies.base_strategy import BaseTransformationStrategy
from src.strategies.validating_strategy_decorator import ValidatingStrategyDecorator


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _row(date: str = "01/01/2023", entry: str = "08:00", exit_: str = "17:00") -> AttendanceRow:
    return AttendanceRow(date=date, entry_time=entry, exit_time=exit_, total_hours=9.0)


def _report(report_type: ReportType = ReportType.TYPE_A, rows=None) -> AttendanceReport:
    return AttendanceReport(report_type=report_type, rows=rows or [_row()])


def _passthrough_inner(return_row: AttendanceRow) -> MagicMock:
    inner = MagicMock(spec=BaseTransformationStrategy)
    inner.transform_row.return_value = return_row
    inner.build_summary.return_value = _report()
    return inner


# ─────────────────────────────────────────────────────────────────────────────
# 1. ValidatingStrategyDecorator
# ─────────────────────────────────────────────────────────────────────────────

class TestValidatingDecoratorDelegation:
    """The decorator must delegate to the inner strategy for every call."""

    def test_transform_row_calls_inner(self) -> None:
        good = _row()
        inner = _passthrough_inner(good)
        ValidatingStrategyDecorator(inner).transform_row(_row())
        inner.transform_row.assert_called_once()

    def test_transform_row_returns_inner_result_when_valid(self) -> None:
        good = _row(entry="08:30", exit_="17:30")
        inner = _passthrough_inner(good)
        result = ValidatingStrategyDecorator(inner).transform_row(_row())
        assert result == good

    def test_prepare_delegated_to_inner(self) -> None:
        inner = _passthrough_inner(_row())
        report = _report()
        ValidatingStrategyDecorator(inner).prepare(report, seed=7, location_override="x")
        inner.prepare.assert_called_once_with(report, 7, "x")

    def test_build_summary_delegated_to_inner(self) -> None:
        inner = _passthrough_inner(_row())
        rows = [_row()]
        report = _report()
        ValidatingStrategyDecorator(inner).build_summary(rows, report)
        inner.build_summary.assert_called_once_with(rows, report)


class TestValidatingDecoratorInvalidRows:
    """The decorator must raise TransformationError for invalid transformed rows."""

    def test_exit_before_entry_raises(self) -> None:
        bad = AttendanceRow(date="01/01/2023", entry_time="10:00", exit_time="09:00", total_hours=0.0)
        inner = _passthrough_inner(bad)
        with pytest.raises(TransformationError):
            ValidatingStrategyDecorator(inner).transform_row(_row())

    def test_exit_equal_to_entry_raises(self) -> None:
        bad = AttendanceRow(date="01/01/2023", entry_time="09:00", exit_time="09:00", total_hours=0.0)
        inner = _passthrough_inner(bad)
        with pytest.raises(TransformationError):
            ValidatingStrategyDecorator(inner).transform_row(_row())

    def test_error_carries_row_date(self) -> None:
        bad = AttendanceRow(date="15/03/2023", entry_time="10:00", exit_time="09:00", total_hours=0.0)
        inner = _passthrough_inner(bad)
        with pytest.raises(TransformationError) as exc_info:
            ValidatingStrategyDecorator(inner).transform_row(_row())
        assert exc_info.value.row_date == "15/03/2023"


# ─────────────────────────────────────────────────────────────────────────────
# 2. TransformationService fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformationServiceFallback:
    """When a strategy raises TransformationError the service keeps the original
    row and continues processing rather than aborting the whole report."""

    def _make_strategy(self, raises: bool = False, return_row: AttendanceRow | None = None):
        strategy = MagicMock(spec=BaseTransformationStrategy)
        if raises:
            strategy.transform_row.side_effect = TransformationError(
                "bad row", row_date="01/01/2023"
            )
        else:
            strategy.transform_row.return_value = return_row or _row()
        strategy.build_summary.side_effect = (
            lambda new_rows, orig: AttendanceReport(report_type=orig.report_type, rows=new_rows)
        )
        return strategy

    def test_original_row_preserved_on_error(self) -> None:
        original = _row(date="01/01/2023")
        strategy = self._make_strategy(raises=True)
        service = TransformationService({"TYPE_A": strategy})

        with patch("src.services.transformation_service.logger"):
            result = service.transform(_report(rows=[original]))

        assert result.rows == [original]

    def test_service_continues_after_failing_row(self) -> None:
        row_a = _row("01/01/2023")
        row_b = _row("02/01/2023")  # this one will fail
        row_c = _row("03/01/2023")
        transformed_a = _row("01/01/2023", entry="08:30", exit_="17:30")
        transformed_c = _row("03/01/2023", entry="08:15", exit_="17:15")

        def side_effect(row: AttendanceRow) -> AttendanceRow:
            if row.date == "02/01/2023":
                raise TransformationError("bad", row_date="02/01/2023")
            return transformed_a if row.date == "01/01/2023" else transformed_c

        strategy = MagicMock(spec=BaseTransformationStrategy)
        strategy.transform_row.side_effect = side_effect
        strategy.build_summary.side_effect = (
            lambda new_rows, orig: AttendanceReport(report_type=orig.report_type, rows=new_rows)
        )

        service = TransformationService({"TYPE_A": strategy})
        report = _report(rows=[row_a, row_b, row_c])

        with patch("src.services.transformation_service.logger"):
            result = service.transform(report)

        assert result.rows == [transformed_a, row_b, transformed_c]
        assert strategy.transform_row.call_count == 3  # all three rows attempted


# ─────────────────────────────────────────────────────────────────────────────
# 3. ParserFactory
# ─────────────────────────────────────────────────────────────────────────────

class TestParserFactory:
    def test_returns_type_a_parser_for_type_a_string(self) -> None:
        parser = ParserFactory().get_parser("TYPE_A")
        assert isinstance(parser, TypeAParser)

    def test_returns_type_b_parser_for_type_b_string(self) -> None:
        parser = ParserFactory().get_parser("TYPE_B")
        assert isinstance(parser, TypeBParser)

    def test_type_b_parser_is_type_n_parser(self) -> None:
        # TypeBParser is an alias for TypeNParser — both names must resolve to the same class
        parser = ParserFactory().get_parser("TYPE_B")
        assert isinstance(parser, TypeNParser)

    def test_returns_correct_parser_for_report_type_enum(self) -> None:
        factory = ParserFactory()
        assert isinstance(factory.get_parser(ReportType.TYPE_A), TypeAParser)
        assert isinstance(factory.get_parser(ReportType.TYPE_B), TypeBParser)

    def test_unknown_type_raises_unsupported_report_type_error(self) -> None:
        with pytest.raises(UnsupportedReportTypeError, match="UNKNOWN"):
            ParserFactory().get_parser("UNKNOWN")

    def test_error_message_lists_known_types(self) -> None:
        with pytest.raises(UnsupportedReportTypeError) as exc_info:
            ParserFactory().get_parser("GARBAGE")
        assert "TYPE_A" in str(exc_info.value)

    def test_custom_registry_is_used(self) -> None:
        mock_parser = MagicMock()
        factory = ParserFactory(registry={"CUSTOM": mock_parser})
        assert factory.get_parser("CUSTOM") is mock_parser

    def test_custom_registry_does_not_see_default_types(self) -> None:
        factory = ParserFactory(registry={"CUSTOM": MagicMock()})
        with pytest.raises(UnsupportedReportTypeError):
            factory.get_parser("TYPE_A")


# ─────────────────────────────────────────────────────────────────────────────
# 4. CLI smoke test
# ─────────────────────────────────────────────────────────────────────────────

class TestCLISmoke:
    """End-to-end smoke test for main().

    All I/O-heavy dependencies (OCR, PDF parsing, rendering) are mocked so the
    test exercises the full argument-parsing → pipeline wiring → output path
    creation logic without touching disk or real PDFs.
    """

    def _make_report(self) -> AttendanceReport:
        row = AttendanceRow(
            date="01/01/2023",
            day_of_week="ראשון",
            entry_time="08:00",
            exit_time="17:00",
            total_hours=9.0,
        )
        return AttendanceReport(
            report_type=ReportType.TYPE_A,
            month_year="01/2023",
            rows=[row],
            summary=AttendanceSummary(work_days=1, total_hours=9.0),
        )

    def test_single_pdf_produces_outputs(self, tmp_path: Path) -> None:
        # Create a dummy PDF so the path-existence check passes
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 dummy")
        out_dir = tmp_path / "out"

        report = self._make_report()

        # Wire the parser mock
        mock_parser = MagicMock()
        mock_parser.parse_pdf.return_value = report

        # Wire the service mock
        mock_service = MagicMock()
        mock_service.transform.return_value = report

        # Wire HTML renderer to write a real file so output list is non-empty
        html_out = out_dir / "test.html"

        def fake_html_render(rpt, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<html/>", encoding="utf-8")

        mock_html_renderer = MagicMock()
        mock_html_renderer.render.side_effect = fake_html_render

        mock_pdf_renderer = MagicMock()
        mock_pdf_renderer.render.return_value = None

        mock_validator = MagicMock()
        mock_validator.validate.return_value = None

        mock_excel_renderer = MagicMock()
        mock_excel_renderer.render.return_value = None

        mock_container = MagicMock()
        mock_container.get_parser_factory.return_value.get_parser.return_value = mock_parser
        mock_container.get_transformation_service.return_value = mock_service
        mock_container.get_html_renderer.return_value = mock_html_renderer
        mock_container.get_pdf_renderer.return_value = mock_pdf_renderer
        mock_container.get_report_validator.return_value = mock_validator
        mock_container.get_excel_renderer.return_value = mock_excel_renderer

        with (
            patch("main.ocr_module.extract_text", return_value="דוח נוכחות TYPE_A"),
            patch("main.classify", return_value="TYPE_A"),
            patch("main.Container", mock_container),
        ):
            from main import main
            sys.argv = ["attendance-report", str(pdf), "-o", str(out_dir)]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 0, f"main() exited with non-zero code {exc.code}"

        assert html_out.exists(), "HTML output file was not created"

    def test_nonexistent_input_exits_with_code_1(self, tmp_path: Path) -> None:
        from main import main

        sys.argv = [
            "attendance-report",
            str(tmp_path / "does_not_exist.pdf"),
            "-o", str(tmp_path / "out"),
        ]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
