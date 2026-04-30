"""
Decorator pattern – ValidatingStrategyDecorator.

Wraps any ``BaseTransformationStrategy``, calls it, then validates the
transformed row.  If validation fails, raises ``TransformationError``.
``TransformationService`` catches that error and falls back to the original row.

Validation rules
----------------
1. exit_time must be strictly after entry_time (when both are present).
2. entry_time and exit_time must be valid HH:MM strings when present.
3. total_hours must not be negative.
4. break_minutes must be within [0, MAX_BREAK_HOURS] when present.
5. Overtime fields (regular_hours, overtime_125_hours, overtime_150_hours)
   must not be negative when present.
"""

from __future__ import annotations

from src.exceptions import TransformationError
from src.models.attendance import AttendanceRow
from src.models.attendance import AttendanceReport
from src.strategies.base_strategy import BaseTransformationStrategy
from src.transformers.helpers import time_to_minutes

MAX_BREAK_HOURS: float = 2.0
BUCKET_SUM_TOLERANCE: float = 0.05


class ValidatingStrategyDecorator(BaseTransformationStrategy):
    """Decorator that validates each row returned by the inner strategy.

    Args:
        inner: Any ``BaseTransformationStrategy`` instance to decorate.
    """

    def __init__(self, inner: BaseTransformationStrategy) -> None:
        self.inner = inner

    # ── Forwarded lifecycle hooks ─────────────────────────────────────────────

    def prepare(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> None:
        self.inner.prepare(report, seed, location_override)

    def build_summary(
        self,
        new_rows: list[AttendanceRow],
        original_report: AttendanceReport,
    ) -> AttendanceReport:
        return self.inner.build_summary(new_rows, original_report)

    # ── Decorated method ──────────────────────────────────────────────────────

    def transform_row(self, row: AttendanceRow) -> AttendanceRow:
        """Delegate to inner strategy then validate the result."""
        transformed = self.inner.transform_row(row)
        self._validate(transformed)
        return transformed

    # ── Validation suite ──────────────────────────────────────────────────────

    @staticmethod
    def _validate(row: AttendanceRow) -> None:
        """Run all row-level validation checks.

        Raises:
            TransformationError: describing the first failing check.
        """
        date = row.date

        # Rule 1 – exit must be strictly after entry (when both present)
        if row.entry_time and row.exit_time:
            entry_m = time_to_minutes(row.entry_time)
            exit_m  = time_to_minutes(row.exit_time)
            if exit_m <= entry_m:
                raise TransformationError(
                    f"exit_time {row.exit_time!r} is not after "
                    f"entry_time {row.entry_time!r}",
                    row_date=date,
                )

        # Rule 2 – total_hours must be non-negative
        if row.total_hours < 0:
            raise TransformationError(
                f"total_hours {row.total_hours} is negative",
                row_date=date,
            )

        # Rule 3 – break_minutes must be within [0, MAX_BREAK_HOURS]
        if row.break_minutes is not None:
            if row.break_minutes < 0:
                raise TransformationError(
                    f"break_minutes {row.break_minutes} is negative",
                    row_date=date,
                )
            if row.break_minutes > MAX_BREAK_HOURS:
                raise TransformationError(
                    f"break_minutes {row.break_minutes} exceeds "
                    f"maximum allowed {MAX_BREAK_HOURS} hours",
                    row_date=date,
                )

        # Rule 4 – overtime fields must not be negative
        for field_name, val in (
            ("regular_hours", row.regular_hours),
            ("overtime_125_hours", row.overtime_125_hours),
            ("overtime_150_hours", row.overtime_150_hours),
        ):
            if val is not None and val < 0:
                raise TransformationError(
                    f"{field_name} {val} is negative",
                    row_date=date,
                )

        # Rule 5 – overtime buckets must sum to total_hours (when all present)
        if (
            row.regular_hours is not None
            and row.overtime_125_hours is not None
            and row.overtime_150_hours is not None
        ):
            bucket_sum = row.regular_hours + row.overtime_125_hours + row.overtime_150_hours
            if abs(bucket_sum - row.total_hours) > BUCKET_SUM_TOLERANCE:
                raise TransformationError(
                    f"overtime buckets sum {bucket_sum:.4f} differs from "
                    f"total_hours {row.total_hours:.4f} "
                    f"(tolerance ±{BUCKET_SUM_TOLERANCE})",
                    row_date=date,
                )
