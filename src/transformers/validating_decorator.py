"""
Decorator Pattern – ValidatingStrategyDecorator.

``ValidatingStrategyDecorator`` wraps any ``RowTransformStrategy`` and adds
row-level validation after each ``transform_row()`` call.

If the transformed row fails any check, a ``TransformationError`` is raised.
``TransformationService`` catches that error and falls back to the original,
untransformed row, logging a warning so the failure is always traceable.

Validation rules applied to every transformed row
--------------------------------------------------
1. When both ``entry_time`` and ``exit_time`` are non-empty, exit must be
   strictly after entry.
2. ``total_hours`` must be non-negative.
3. When ``break_minutes`` is set it must be non-negative and must not
   exceed ``MAX_BREAK_HOURS`` (2 hours – well above any configured pool
   maximum of 1 h, giving a safe guard against wild OCR values).
4. When Type-A overtime buckets (``hours_100 / 125 / 150``) are all set,
   their sum must equal ``total_hours`` within a small tolerance.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.transformers.helpers import time_to_minutes
from src.transformers.row_strategy import RowTransformStrategy

logger = logging.getLogger(__name__)

# Maximum acceptable break in hours (guard against wild values)
MAX_BREAK_HOURS: float = 2.0
# Tolerance for overtime-bucket sum check
BUCKET_SUM_TOLERANCE: float = 0.05


class TransformationError(Exception):
    """Raised by ``ValidatingStrategyDecorator`` when a transformed row fails
    validation.  Caught by ``TransformationService`` to trigger fallback."""

    def __init__(self, message: str, row_date: str = "") -> None:
        super().__init__(message)
        self.row_date = row_date


class ValidatingStrategyDecorator(RowTransformStrategy):
    """Decorator that validates each row returned by an inner strategy.

    Transparently forwards ``prepare()`` and ``build_summary()`` to the
    wrapped strategy.  Only ``transform_row()`` is augmented: after the inner
    call it runs the validation suite and raises ``TransformationError`` on
    any failure.

    Args:
        inner: The concrete ``RowTransformStrategy`` to decorate.
    """

    def __init__(self, inner: RowTransformStrategy) -> None:
        self._inner = inner

    # ── Forwarded hooks ───────────────────────────────────────────────────────

    def prepare(
        self,
        report: AttendanceReport,
        rng: random.Random,
        location_override: str,
    ) -> None:
        """Forward to the inner strategy's ``prepare()``."""
        self._inner.prepare(report, rng, location_override)

    def build_summary(
        self,
        new_rows: List[AttendanceRow],
        original_report: AttendanceReport,
    ) -> Tuple[AttendanceSummary, Dict[str, Any]]:
        """Forward to the inner strategy's ``build_summary()``."""
        return self._inner.build_summary(new_rows, original_report)

    # ── Decorated hook ────────────────────────────────────────────────────────

    def transform_row(
        self,
        row: AttendanceRow,
        rng: random.Random,
    ) -> AttendanceRow:
        """Call the inner ``transform_row()`` then validate the result.

        Raises:
            TransformationError: if any validation rule is violated.
        """
        result = self._inner.transform_row(row, rng)
        self._validate(result)
        return result

    # ── Validation suite ──────────────────────────────────────────────────────

    @staticmethod
    def _validate(row: AttendanceRow) -> None:
        """Run all row-level validation checks.

        Raises:
            TransformationError: describing the first failing check.
        """
        date = row.date  # used in error messages

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

        # Rule 4 – overtime buckets must sum to total_hours (Type-A rows)
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
