"""
Layer 4 – Post-transformation validation.

Runs sanity checks on transformed reports to ensure logical consistency.
Raises ValidationError with a descriptive message if any check fails.
"""

from __future__ import annotations

import logging
from typing import Union

from src.models import TypeAReport, TypeNReport
from src.transformers.helpers import time_to_minutes

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when a report fails validation."""
    pass


def _validate_type_a(report: TypeAReport) -> None:
    errors: list[str] = []

    for i, row in enumerate(report.rows):
        entry_m = time_to_minutes(row.entry_time)
        exit_m = time_to_minutes(row.exit_time)

        # exit must be after entry
        if exit_m <= entry_m:
            errors.append(
                f"Row {i} ({row.date}): exit {row.exit_time} <= entry {row.entry_time}"
            )

        # daily hours between 1–14
        if not (0.5 <= row.total_hours <= 14):
            errors.append(
                f"Row {i} ({row.date}): total_hours={row.total_hours} out of range [0.5, 14]"
            )

        # overtime buckets should sum to ≈ total
        bucket_sum = (row.regular_hours or 0) + (row.overtime_125_hours or 0) + (row.overtime_150_hours or 0)
        if abs(bucket_sum - row.total_hours) > 0.1:
            errors.append(
                f"Row {i} ({row.date}): bucket sum {bucket_sum} ≠ total {row.total_hours}"
            )

    if report.summary:
        # Summary total should match row sum
        row_total = round(sum(r.total_hours for r in report.rows), 2)
        if abs(report.summary.total_hours - row_total) > 0.5:
            errors.append(
                f"Summary total_hours {report.summary.total_hours} ≠ row sum {row_total}"
            )

        # Work days should match row count
        if report.summary.work_days != len(report.rows):
            errors.append(
                f"Summary work_days {report.summary.work_days} ≠ row count {len(report.rows)}"
            )

    if errors:
        msg = "Type-A validation failed:\n  " + "\n  ".join(errors)
        raise ValidationError(msg)

    logger.info(f"Type-A validation passed ({len(report.rows)} rows)")


def _validate_type_n(report: TypeNReport) -> None:
    errors: list[str] = []

    for i, row in enumerate(report.rows):
        if not row.entry_time or not row.exit_time:
            continue

        entry_m = time_to_minutes(row.entry_time)
        exit_m = time_to_minutes(row.exit_time)

        if exit_m <= entry_m:
            errors.append(
                f"Row {i} ({row.date}): exit {row.exit_time} <= entry {row.entry_time}"
            )

        if not (0.5 <= row.total_hours <= 14):
            errors.append(
                f"Row {i} ({row.date}): total_hours={row.total_hours} out of range [0.5, 14]"
            )

    if report.summary:
        row_total = round(sum(r.total_hours for r in report.rows), 2)
        if abs(report.summary.total_hours - row_total) > 0.5:
            errors.append(
                f"Summary total_hours {report.summary.total_hours} ≠ row sum {row_total}"
            )

        # Pay should = hours × rate (if rate > 0)
        if report.summary.hourly_rate > 0:
            expected_pay = round(row_total * report.summary.hourly_rate, 2)
            if abs(report.summary.total_pay - expected_pay) > 1.0:
                errors.append(
                    f"Summary pay {report.summary.total_pay} ≠ "
                    f"hours×rate {expected_pay}"
                )

    if errors:
        msg = "Type-N validation failed:\n  " + "\n  ".join(errors)
        raise ValidationError(msg)

    logger.info(f"Type-N validation passed ({len(report.rows)} rows)")


def validate_report(report: Union[TypeAReport, TypeNReport]) -> None:
    """
    Validate a report after transformation.
    Raises ValidationError if any check fails.

    Uses structural pattern-matching to dispatch per report type.
    Each ``case`` matches the *class* of the frozen dataclass instance.
    """
    match report:
        case TypeAReport():
            _validate_type_a(report)
        case TypeNReport():
            _validate_type_n(report)
        case _:
            raise TypeError(f"Unknown report type: {type(report)}")
