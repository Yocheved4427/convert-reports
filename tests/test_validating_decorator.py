"""
Unit tests for the ValidatingStrategyDecorator (Strategy + Decorator patterns).

Covers every validation rule:
  Rule 1 – exit_time must be strictly after entry_time
  Rule 2 – total_hours must be non-negative
  Rule 3 – break_minutes must be within [0, MAX_BREAK_HOURS]
  Rule 4 – overtime fields must not be negative
  Rule 5 – decorator forwards prepare() and build_summary() to the inner strategy
  Rule 6 – valid rows pass through unchanged

All tests are pure unit tests: no OCR, no filesystem, no PDF I/O.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from src.exceptions import TransformationError
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.models.report_type import ReportType
from src.strategies.validating_strategy_decorator import (
    MAX_BREAK_HOURS,
    ValidatingStrategyDecorator,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(
    date: str = "10/01/2023",
    entry: str = "08:00",
    exit_: str = "17:00",
    total_hours: float = 8.0,
    break_minutes: float | None = None,
    regular_hours: float | None = None,
    overtime_125: float | None = None,
    overtime_150: float | None = None,
) -> AttendanceRow:
    return AttendanceRow(
        date=date,
        entry_time=entry,
        exit_time=exit_,
        total_hours=total_hours,
        break_minutes=break_minutes,
        regular_hours=regular_hours,
        overtime_125_hours=overtime_125,
        overtime_150_hours=overtime_150,
    )


def _make_report(rows: list[AttendanceRow] | None = None) -> AttendanceReport:
    return AttendanceReport(
        report_type=ReportType.TYPE_A,
        rows=rows or [_row()],
    )


def _make_passthrough_inner(return_row: AttendanceRow) -> MagicMock:
    """Return a mock inner strategy that always returns *return_row*."""
    inner = MagicMock()
    inner.transform_row.return_value = return_row
    inner.build_summary.return_value = _make_report()
    return inner


# ── Rule 1: exit must be strictly after entry ─────────────────────────────────

class TestExitAfterEntry:
    def test_equal_times_raises(self) -> None:
        row = _row(entry="10:00", exit_="10:00", total_hours=0.0)
        inner = _make_passthrough_inner(row)
        decorator = ValidatingStrategyDecorator(inner)
        with pytest.raises(TransformationError, match="exit_time"):
            decorator.transform_row(_row())

    def test_exit_before_entry_raises(self) -> None:
        row = _row(entry="10:00", exit_="09:00", total_hours=-1.0)
        inner = _make_passthrough_inner(row)
        decorator = ValidatingStrategyDecorator(inner)
        with pytest.raises(TransformationError, match="exit_time"):
            decorator.transform_row(_row())

    def test_exit_one_minute_after_entry_passes(self) -> None:
        row = _row(entry="10:00", exit_="10:01", total_hours=0.02)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception

    def test_missing_entry_time_skips_check(self) -> None:
        row = AttendanceRow(date="10/01/2023", entry_time=None, exit_time="17:00")
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception

    def test_missing_exit_time_skips_check(self) -> None:
        row = AttendanceRow(date="10/01/2023", entry_time="08:00", exit_time=None)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception


# ── Rule 2: total_hours must be non-negative ──────────────────────────────────

class TestTotalHours:
    def test_negative_total_hours_raises(self) -> None:
        row = _row(entry="08:00", exit_="17:00", total_hours=-0.01)
        inner = _make_passthrough_inner(row)
        with pytest.raises(TransformationError, match="total_hours"):
            ValidatingStrategyDecorator(inner).transform_row(_row())

    def test_zero_total_hours_passes(self) -> None:
        row = _row(entry="08:00", exit_="17:00", total_hours=0.0)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception

    def test_positive_total_hours_passes(self) -> None:
        row = _row(entry="08:00", exit_="17:00", total_hours=8.5)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception


# ── Rule 3: break_minutes must be within [0, MAX_BREAK_HOURS] ─────────────────

class TestBreakMinutes:
    def test_negative_break_raises(self) -> None:
        row = _row(break_minutes=-0.1)
        inner = _make_passthrough_inner(row)
        with pytest.raises(TransformationError, match="break_minutes"):
            ValidatingStrategyDecorator(inner).transform_row(_row())

    def test_break_exceeds_max_raises(self) -> None:
        row = _row(break_minutes=MAX_BREAK_HOURS + 0.01)
        inner = _make_passthrough_inner(row)
        with pytest.raises(TransformationError, match="break_minutes"):
            ValidatingStrategyDecorator(inner).transform_row(_row())

    def test_break_exactly_at_max_passes(self) -> None:
        row = _row(break_minutes=MAX_BREAK_HOURS)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception

    def test_zero_break_passes(self) -> None:
        row = _row(break_minutes=0.0)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception

    def test_none_break_skips_check(self) -> None:
        row = _row(break_minutes=None)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception


# ── Rule 4: overtime fields must not be negative ──────────────────────────────

class TestOvertimeFields:
    @pytest.mark.parametrize("field_name,kwargs", [
        ("regular_hours",      {"regular_hours": -0.01}),
        ("overtime_125_hours", {"overtime_125": -0.01}),
        ("overtime_150_hours", {"overtime_150": -0.01}),
    ])
    def test_negative_overtime_field_raises(
        self, field_name: str, kwargs: dict
    ) -> None:
        row = _row(**kwargs)  # type: ignore[arg-type]
        inner = _make_passthrough_inner(row)
        with pytest.raises(TransformationError, match=field_name):
            ValidatingStrategyDecorator(inner).transform_row(_row())

    def test_zero_overtime_fields_pass(self) -> None:
        # total_hours must equal sum of buckets (0+0+0=0) to pass validation
        row = _row(total_hours=0.0, regular_hours=0.0, overtime_125=0.0, overtime_150=0.0)
        inner = _make_passthrough_inner(row)
        ValidatingStrategyDecorator(inner).transform_row(_row())  # no exception


# ── Delegation: prepare() and build_summary() must be forwarded ───────────────

class TestDelegation:
    def test_prepare_forwarded_to_inner(self) -> None:
        inner = MagicMock()
        decorator = ValidatingStrategyDecorator(inner)
        report = _make_report()
        decorator.prepare(report, seed=7, location_override="test")
        inner.prepare.assert_called_once_with(report, 7, "test")

    def test_build_summary_forwarded_to_inner(self) -> None:
        inner = MagicMock()
        expected = _make_report()
        inner.build_summary.return_value = expected
        decorator = ValidatingStrategyDecorator(inner)
        rows = [_row()]
        report = _make_report()
        result = decorator.build_summary(rows, report)
        inner.build_summary.assert_called_once_with(rows, report)
        assert result is expected

    def test_inner_transform_row_is_called(self) -> None:
        valid_row = _row()
        inner = _make_passthrough_inner(valid_row)
        decorator = ValidatingStrategyDecorator(inner)
        original = _row(entry="07:00", exit_="16:00")
        result = decorator.transform_row(original)
        inner.transform_row.assert_called_once_with(original)
        assert result is valid_row

    def test_error_carries_row_date(self) -> None:
        bad_row = _row(date="15/06/2023", entry="10:00", exit_="09:00")
        inner = _make_passthrough_inner(bad_row)
        decorator = ValidatingStrategyDecorator(inner)
        with pytest.raises(TransformationError) as exc_info:
            decorator.transform_row(_row())
        assert exc_info.value.row_date == "15/06/2023"
