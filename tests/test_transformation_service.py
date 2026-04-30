"""
Unit tests for TransformationService (services/transformation_service.py).

Verifies:
  - Correct strategy dispatch via registry (no type-branching in service)
  - ``TransformationError`` fallback: original row is kept, warning is logged
  - ``KeyError`` for unregistered report types
  - Service remains agnostic to concrete strategy implementations
  - ``prepare()`` and ``build_summary()`` lifecycle hooks are called correctly
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from src.exceptions import TransformationError
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.models.report_type import ReportType
from src.services.transformation_service import TransformationService
from src.strategies.base_strategy import BaseTransformationStrategy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(date: str = "10/01/2023", entry: str = "08:00", exit_: str = "17:00") -> AttendanceRow:
    return AttendanceRow(date=date, entry_time=entry, exit_time=exit_, total_hours=9.0)


def _report(report_type: ReportType, rows: list[AttendanceRow] | None = None) -> AttendanceReport:
    return AttendanceReport(report_type=report_type, rows=rows or [_row()])


def _mock_strategy(transformed_row: AttendanceRow | None = None) -> MagicMock:
    """Return a mock strategy that transforms each row to *transformed_row*."""
    strategy = MagicMock(spec=BaseTransformationStrategy)
    if transformed_row is not None:
        strategy.transform_row.return_value = transformed_row
    # build_summary returns a new report with the new_rows
    strategy.build_summary.side_effect = lambda new_rows, orig: (
        orig.__class__(
            report_type=orig.report_type,
            rows=new_rows,
            summary=orig.summary,
        )
    )
    return strategy


# ── Dispatch tests ────────────────────────────────────────────────────────────

class TestDispatch:
    def test_correct_strategy_used_for_type_a(self) -> None:
        transformed = _row(entry="08:30", exit_="17:30")
        strategy_a = _mock_strategy(transformed)
        strategy_b = _mock_strategy(_row())

        service = TransformationService({"TYPE_A": strategy_a, "TYPE_B": strategy_b})
        report = _report(ReportType.TYPE_A)
        service.transform(report)

        strategy_a.transform_row.assert_called()
        strategy_b.transform_row.assert_not_called()

    def test_correct_strategy_used_for_type_b(self) -> None:
        strategy_a = _mock_strategy(_row())
        transformed = _row(entry="09:00", exit_="16:00")
        strategy_b = _mock_strategy(transformed)

        service = TransformationService({"TYPE_A": strategy_a, "TYPE_B": strategy_b})
        report = _report(ReportType.TYPE_B)
        service.transform(report)

        strategy_b.transform_row.assert_called()
        strategy_a.transform_row.assert_not_called()

    def test_unregistered_type_raises_key_error(self) -> None:
        service = TransformationService({"TYPE_A": _mock_strategy(_row())})
        report = _report(ReportType.TYPE_B)
        with pytest.raises(KeyError, match="TYPE_B"):
            service.transform(report)

    def test_none_report_type_raises_key_error(self) -> None:
        service = TransformationService({"TYPE_A": _mock_strategy(_row())})
        report = AttendanceReport(report_type=None, rows=[_row()])
        with pytest.raises(KeyError):
            service.transform(report)


# ── Lifecycle tests ───────────────────────────────────────────────────────────

class TestLifecycle:
    def test_prepare_called_once_with_seed_and_override(self) -> None:
        strategy = _mock_strategy(_row())
        service = TransformationService({"TYPE_A": strategy})
        report = _report(ReportType.TYPE_A)
        service.transform(report, seed=99, location_override="Tel Aviv")
        strategy.prepare.assert_called_once_with(report, 99, "Tel Aviv")

    def test_build_summary_called_once_after_row_loop(self) -> None:
        orig_row = _row("01/01/2023")
        new_row = _row("01/01/2023", entry="08:15", exit_="17:15")
        strategy = _mock_strategy(new_row)
        service = TransformationService({"TYPE_A": strategy})
        report = _report(ReportType.TYPE_A, rows=[orig_row])
        service.transform(report)
        strategy.build_summary.assert_called_once()
        call_args = strategy.build_summary.call_args
        assert call_args[0][0] == [new_row]
        assert call_args[0][1] is report

    def test_transform_row_called_once_per_row(self) -> None:
        rows = [_row(f"0{i}/01/2023") for i in range(1, 4)]
        strategy = _mock_strategy(_row())
        service = TransformationService({"TYPE_A": strategy})
        service.transform(_report(ReportType.TYPE_A, rows=rows))
        assert strategy.transform_row.call_count == 3


# ── Fallback tests ────────────────────────────────────────────────────────────

class TestValidationFallback:
    def test_original_row_kept_on_transformation_error(self) -> None:
        original = _row("05/01/2023")
        strategy = MagicMock(spec=BaseTransformationStrategy)
        strategy.transform_row.side_effect = TransformationError(
            "exit before entry", row_date="05/01/2023"
        )
        captured_new_rows: list[list[AttendanceRow]] = []

        def capture_build_summary(new_rows: list, orig: AttendanceReport) -> AttendanceReport:
            captured_new_rows.append(list(new_rows))
            return AttendanceReport(report_type=ReportType.TYPE_A, rows=new_rows)

        strategy.build_summary.side_effect = capture_build_summary

        service = TransformationService({"TYPE_A": strategy})
        report = _report(ReportType.TYPE_A, rows=[original])

        with patch("src.services.transformation_service.logger") as mock_log:
            result = service.transform(report)
            mock_log.warning.assert_called_once()

        assert captured_new_rows == [[original]]

    def test_mix_of_valid_and_failing_rows(self) -> None:
        row_ok_1 = _row("01/01/2023")
        row_fail = _row("02/01/2023")
        row_ok_2 = _row("03/01/2023")

        transformed_ok_1 = _row("01/01/2023", entry="08:30", exit_="17:30")
        transformed_ok_2 = _row("03/01/2023", entry="08:15", exit_="17:15")

        def mock_transform(row: AttendanceRow) -> AttendanceRow:
            if row.date == "02/01/2023":
                raise TransformationError("bad row", row_date="02/01/2023")
            if row.date == "01/01/2023":
                return transformed_ok_1
            return transformed_ok_2

        strategy = MagicMock(spec=BaseTransformationStrategy)
        strategy.transform_row.side_effect = mock_transform

        final_rows: list[list[AttendanceRow]] = []

        def capture(new_rows: list, orig: AttendanceReport) -> AttendanceReport:
            final_rows.append(list(new_rows))
            return AttendanceReport(report_type=ReportType.TYPE_A, rows=new_rows)

        strategy.build_summary.side_effect = capture

        service = TransformationService({"TYPE_A": strategy})
        report = _report(ReportType.TYPE_A, rows=[row_ok_1, row_fail, row_ok_2])

        with patch("src.services.transformation_service.logger"):
            service.transform(report)

        # The failing row must be the original, not the transformed one
        assert final_rows == [[transformed_ok_1, row_fail, transformed_ok_2]]
