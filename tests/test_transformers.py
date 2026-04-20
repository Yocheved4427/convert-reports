"""
Integration tests for TypeATransformer and TypeNTransformer.

These tests build minimal synthetic reports (no I/O, no OCR) and assert
the invariants that the transformers must preserve.
"""

from __future__ import annotations

import pytest

from src.models.type_a import TypeAReport, TypeARow, TypeASummary
from src.models.type_n import TypeNReport, TypeNRow, TypeNSummary
from src.transformers.helpers import time_to_minutes
from src.transformers.type_a_transformer import TypeATransformer
from src.transformers.type_n_transformer import TypeNTransformer


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_type_a_row(
    date: str = "10/01/2023",
    entry: str = "08:00",
    exit_: str = "17:00",
) -> TypeARow:
    return TypeARow(
        date=date,
        day_of_week="שלישי",
        location="Office",
        entry_time=entry,
        exit_time=exit_,
        break_minutes=0.5,
        total_hours=8.5,
        hours_100=8.0,
        hours_125=0.5,
        hours_150=0.0,
    )


def _make_type_n_row(
    date: str = "10/01/2023",
    entry: str = "08:00",
    exit_: str = "16:00",
) -> TypeNRow:
    return TypeNRow(
        date=date,
        day_of_week="שלישי",
        entry_time=entry,
        exit_time=exit_,
        total_hours=8.0,
    )


def _type_a_report(rows: list[TypeARow] | None = None) -> TypeAReport:
    rows = rows or [_make_type_a_row(date=f"{d:02d}/01/2023") for d in range(1, 11)]
    return TypeAReport(
        employee_name="Test Employee",
        month_year="1/2023",
        rows=rows,
        summary=TypeASummary(
            work_days=len(rows),
            total_hours=9.0 * len(rows),
            hours_100=8.0 * len(rows),
            hours_125=1.0 * len(rows),
            hours_150=0.0,
        ),
    )


def _type_n_report(rows: list[TypeNRow] | None = None) -> TypeNReport:
    rows = rows or [_make_type_n_row(date=f"{d:02d}/01/2023") for d in range(1, 11)]
    return TypeNReport(
        employee_name="Test Employee",
        company_name="Test Co",
        month_year="1/2023",
        rows=rows,
        summary=TypeNSummary(
            work_days=len(rows),
            total_hours=8.0 * len(rows),
            hourly_rate=50.0,
            total_pay=50.0 * 8.0 * len(rows),
        ),
    )


# ─── TypeATransformer ─────────────────────────────────────────────────────────

class TestTypeATransformer:
    transformer = TypeATransformer()

    def test_exit_always_after_entry(self):
        report = _type_a_report()
        result = self.transformer.transform(report, seed=0)
        for row in result.rows:
            assert time_to_minutes(row.exit_time) > time_to_minutes(row.entry_time), (
                f"exit {row.exit_time} should be > entry {row.entry_time}"
            )

    def test_overtime_buckets_sum_to_net_hours(self):
        report = _type_a_report()
        result = self.transformer.transform(report, seed=1)
        for row in result.rows:
            bucket_sum = round(row.hours_100 + row.hours_125 + row.hours_150, 6)
            assert bucket_sum == pytest.approx(row.total_hours, abs=1e-4), (
                f"Bucket sum {bucket_sum} != total_hours {row.total_hours}"
            )

    def test_result_is_immutable_pydantic_model(self):
        result = self.transformer.transform(_type_a_report(), seed=2)
        with pytest.raises(Exception):   # frozen model – assignment must raise
            result.employee_name = "hacked"  # type: ignore[misc]

    def test_summary_totals_match_rows(self):
        report = _type_a_report()
        result = self.transformer.transform(report, seed=3)
        assert result.summary is not None
        expected_days = len(result.rows)
        assert result.summary.work_days == expected_days
        expected_hours = round(sum(r.total_hours for r in result.rows), 4)
        assert result.summary.total_hours == pytest.approx(expected_hours, abs=0.01)

    def test_location_override_applied(self):
        report = _type_a_report()
        result = self.transformer.transform(report, seed=0, location_override="Tel Aviv")
        for row in result.rows:
            assert row.location == "Tel Aviv"

    def test_location_cleared_when_no_override(self):
        report = _type_a_report()
        result = self.transformer.transform(report, seed=0, location_override="")
        for row in result.rows:
            assert row.location == ""

    def test_ocr_month_error_corrected(self):
        """Most rows claim month=1; two rows have OCR error month=11 → modal wins."""
        rows = [_make_type_a_row(date=f"{d:02d}/01/2023") for d in range(1, 19)]
        rows += [
            _make_type_a_row(date="01/11/2023"),
            _make_type_a_row(date="02/11/2023"),
        ]
        report = _type_a_report(rows=rows)
        result = self.transformer.transform(report, seed=0)
        for row in result.rows:
            month_part = row.date.split("/")[1]
            assert month_part == "01", f"Expected month 01 in {row.date}"

    def test_deterministic_with_same_seed(self):
        report = _type_a_report()
        r1 = self.transformer.transform(report, seed=99)
        r2 = self.transformer.transform(report, seed=99)
        assert [r.entry_time for r in r1.rows] == [r.entry_time for r in r2.rows]
        assert [r.exit_time  for r in r1.rows] == [r.exit_time  for r in r2.rows]

    def test_different_seeds_produce_different_times(self):
        report = _type_a_report()
        r1 = self.transformer.transform(report, seed=1)
        r2 = self.transformer.transform(report, seed=2)
        # At least one row should differ (astronomically unlikely to match)
        assert [r.entry_time for r in r1.rows] != [r.entry_time for r in r2.rows]

    def test_no_input_rows_produces_empty_output(self):
        report = TypeAReport(employee_name="X", month_year="1/2023", rows=[])
        result = self.transformer.transform(report, seed=0)
        assert result.rows == []

    def test_time_normaliser_dot_separator_accepted(self):
        """Parser may emit '08.30'; field_validator should normalise to '08:30'."""
        row = _make_type_a_row(entry="08.30", exit_="17.00")
        assert row.entry_time == "08:30"
        assert row.exit_time == "17:00"


# ─── TypeNTransformer ─────────────────────────────────────────────────────────

class TestTypeNTransformer:
    transformer = TypeNTransformer()

    def test_exit_always_after_entry(self):
        report = _type_n_report()
        result = self.transformer.transform(report, seed=0)
        for row in result.rows:
            if row.entry_time and row.exit_time:
                assert time_to_minutes(row.exit_time) > time_to_minutes(row.entry_time)

    def test_total_hours_matches_gap(self):
        """total_hours must equal (exit - entry) in hours, within rounding."""
        report = _type_n_report()
        result = self.transformer.transform(report, seed=5)
        for row in result.rows:
            if row.entry_time and row.exit_time:
                gap_h = (time_to_minutes(row.exit_time) - time_to_minutes(row.entry_time)) / 60.0
                assert row.total_hours == pytest.approx(gap_h, abs=0.01)

    def test_summary_recalculated(self):
        report = _type_n_report()
        result = self.transformer.transform(report, seed=7)
        assert result.summary is not None
        assert result.summary.work_days == len(result.rows)
        assert result.summary.total_hours == pytest.approx(
            round(sum(r.total_hours for r in result.rows), 2), abs=0.01
        )

    def test_total_pay_equals_hours_times_rate(self):
        report = _type_n_report()
        result = self.transformer.transform(report, seed=8)
        if result.summary:
            rate = result.summary.hourly_rate
            expected_pay = round(result.summary.total_hours * rate, 2)
            assert result.summary.total_pay == pytest.approx(expected_pay, abs=0.01)

    def test_ocr_month_error_corrected(self):
        rows = [_make_type_n_row(date=f"{d:02d}/01/2023") for d in range(1, 19)]
        rows += [
            _make_type_n_row(date="01/11/2023"),
            _make_type_n_row(date="02/11/2023"),
        ]
        report = _type_n_report(rows=rows)
        result = self.transformer.transform(report, seed=0)
        for row in result.rows:
            month_part = row.date.split("/")[1]
            assert month_part == "01", f"Expected month 01 in {row.date}"

    def test_missing_times_row_preserved(self):
        """Rows with empty entry/exit must be passed through (no crash)."""
        rows = [
            TypeNRow(date="05/01/2023", day_of_week="חמישי",
                     entry_time="", exit_time="", total_hours=0.0),
        ]
        report = _type_n_report(rows=rows)
        result = self.transformer.transform(report, seed=0)
        assert len(result.rows) == 1
        assert result.rows[0].entry_time == ""
        assert result.rows[0].exit_time == ""

    def test_result_is_immutable(self):
        result = self.transformer.transform(_type_n_report(), seed=0)
        with pytest.raises(Exception):
            result.employee_name = "hacked"  # type: ignore[misc]
