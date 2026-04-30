"""
Type-B transformation strategy (simple monthly attendance).

Implements ``BaseTransformationStrategy`` for Type-B (simple monthly) reports.

Transformation rules (all thresholds driven by ``src.config.type_b_config``):
  1. Fix OCR month/year errors by enforcing the modal month across all rows.
  2. Shift entry time within configured bounds.
  3. Shift exit time within configured bounds.
  4. Ensure exit > entry by at least ``min_gap_minutes``.
  5. Recalculate day-of-week from the corrected date.
  6. Recalculate total_hours from corrected clock times.
  7. Recompute summary: work_days, total_hours, total_pay = total_hours × rate.
"""

from __future__ import annotations

import dataclasses
import logging
import random
from typing import List, Optional

from src.config import type_b_config as cfg
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.strategies.base_strategy import BaseTransformationStrategy
from src.transformers.helpers import (
    date_to_hebrew_day,
    fix_date_month,
    infer_true_month_year,
    minutes_to_time,
    shift_time,
    time_to_minutes,
)

logger = logging.getLogger(__name__)


class TypeBTransformationStrategy(BaseTransformationStrategy):
    """Concrete strategy for Type-B (simple monthly) attendance reports.

    The ``prepare()`` hook must be called once before the row loop so that
    report-level context (corrected month/year) is cached on ``self``.

    State set by ``prepare()`` and consumed by ``transform_row()``:
        _rng:        Seeded RNG for deterministic output.
        _true_month: Corrected month (int) or ``None``.
        _true_year:  Corrected year  (int) or ``None``.
    """

    def __init__(self) -> None:
        self._rng: random.Random = random.Random(42)
        self._true_month: Optional[int] = None
        self._true_year: Optional[int] = None

    # ── Lifecycle: prepare ────────────────────────────────────────────────────

    def prepare(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",  # unused for Type-B; kept for interface parity
    ) -> None:
        """Infer the true month/year for *report* via majority voting.

        Args:
            report:            The full parsed report (read-only).
            seed:              Random seed for deterministic output.
            location_override: Ignored for Type-B; included for interface parity.
        """
        self._rng = random.Random(seed)

        true_my = infer_true_month_year([r.date for r in report.rows])
        if true_my:
            self._true_month, self._true_year = true_my
            logger.debug(
                "Type-B inferred month/year: %02d/%d",
                self._true_month,
                self._true_year,
            )
        else:
            self._true_month = None
            self._true_year = None

    # ── Lifecycle: transform_row ──────────────────────────────────────────────

    def transform_row(self, row: AttendanceRow) -> AttendanceRow:
        """Apply all Type-B transformation rules to a single row.

        Args:
            row: Original (frozen) ``AttendanceRow`` from the parsed report.

        Returns:
            A new frozen ``AttendanceRow`` with all transformations applied.
        """
        # Step 1 – correct OCR date errors
        date = (
            fix_date_month(row.date, self._true_month, self._true_year)
            if self._true_month
            else row.date
        )

        # Rows with no clock data (weekends / holidays) – only fix the date
        if not row.entry_time or not row.exit_time:
            return dataclasses.replace(row, date=date)

        # Step 2 – shift entry time within configured bounds
        new_entry = shift_time(
            row.entry_time,
            self._rng,
            min_shift=cfg.entry_min_shift,
            max_shift=cfg.entry_max_shift,
            clamp_low=cfg.entry_clamp_low,
            clamp_high=cfg.entry_clamp_high,
        )

        # Step 3 – shift exit time within configured bounds
        new_exit = shift_time(
            row.exit_time,
            self._rng,
            min_shift=cfg.exit_min_shift,
            max_shift=cfg.exit_max_shift,
            clamp_low=cfg.exit_clamp_low,
            clamp_high=cfg.exit_clamp_high,
        )

        # Step 4 – guarantee minimum exit–entry gap
        entry_m = time_to_minutes(new_entry)
        exit_m = time_to_minutes(new_exit)
        if exit_m - entry_m < cfg.min_gap_minutes:
            exit_m = entry_m + cfg.min_gap_minutes + self._rng.randint(
                cfg.min_gap_extra_low, cfg.min_gap_extra_high
            )
            exit_m = min(exit_m, cfg.exit_clamp_high)
            new_exit = minutes_to_time(exit_m)

        # Step 5 – recalculate day-of-week from corrected date
        day = date_to_hebrew_day(date) or row.day_of_week

        # Step 6 – recalculate total hours
        net_minutes = time_to_minutes(new_exit) - time_to_minutes(new_entry)
        total_hours = round(net_minutes / 60.0, 2)

        return dataclasses.replace(
            row,
            date=date,
            entry_time=new_entry,
            exit_time=new_exit,
            day_of_week=day,
            total_hours=total_hours,
        )

    # ── Lifecycle: build_summary ──────────────────────────────────────────────

    def build_summary(
        self,
        new_rows: List[AttendanceRow],
        original_report: AttendanceReport,
    ) -> AttendanceReport:
        """Recompute work_days, total_hours, and total_pay.

        Args:
            new_rows:        All transformed rows.
            original_report: The original report (used for hourly_rate).

        Returns:
            A new frozen ``AttendanceReport`` with updated rows and summary.
        """
        rate = (
            original_report.summary.hourly_rate
            if original_report.summary
            and original_report.summary.hourly_rate is not None
            else 0.0
        )
        total_hours = round(sum(r.total_hours for r in new_rows), 2)
        summary = AttendanceSummary(
            work_days=len([r for r in new_rows if r.total_hours > 0]),
            total_hours=total_hours,
            hourly_rate=rate,
            total_pay=round(total_hours * rate, 2),
        )
        logger.info(
            "Type-B transformed: %d rows, total=%sh, pay=%s",
            len(new_rows),
            summary.total_hours,
            summary.total_pay,
        )
        return dataclasses.replace(
            original_report,
            rows=new_rows,
            summary=summary,
        )
