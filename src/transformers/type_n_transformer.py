"""
Transformer for Type-B reports (simple monthly attendance).

Rules (all thresholds driven by ``src.config.type_b_config``):
  1. Fix OCR month/year errors by enforcing the modal month across all rows.
  2. Shift entry time within configured bounds.
  3. Shift exit time within configured bounds.
  4. Ensure exit > entry by at least ``min_gap_minutes``.
  5. Recalculate day-of-week from the corrected date.
  6. Recalculate total_hours.
  7. Recompute summary: work_days, total_hours, total_pay = total_hours × rate.
"""

from __future__ import annotations

import dataclasses
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from src.config import type_b_config as cfg
from src.models import ReportType
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.transformers.base_transformer import BaseTransformer
from src.transformers.helpers import (
    date_to_hebrew_day,
    fix_date_month,
    infer_true_month_year,
    minutes_to_time,
    shift_time,
    time_to_minutes,
)
from src.transformers.row_strategy import RowTransformStrategy

logger = logging.getLogger(__name__)


class TypeBRowStrategy(RowTransformStrategy):
    """Per-row transformation strategy for Type-B (simple monthly) reports.

    State set by ``prepare()`` and consumed by ``transform_row()``:
      _true_month – corrected month (int) or None
      _true_year  – corrected year  (int) or None
    """

    # ── Hook 1 ────────────────────────────────────────────────────────────────

    def prepare(
        self,
        report: AttendanceReport,
        rng: random.Random,
        location_override: str,  # unused by Type-N; kept for interface parity
    ) -> None:
        """Infer the true month/year for this report."""
        true_my = infer_true_month_year([r.date for r in report.rows])
        if true_my:
            self._true_month: Optional[int] = true_my[0]
            self._true_year:  Optional[int] = true_my[1]
            logger.debug(
                f"Type-N inferred month/year: "
                f"{self._true_month:02d}/{self._true_year}"
            )
        else:
            self._true_month = None
            self._true_year  = None

    # ── Hook 2 ────────────────────────────────────────────────────────────────

    def transform_row(
        self,
        row: AttendanceRow,
        rng: random.Random,
    ) -> AttendanceRow:
        """Apply all Type-N transformation rules to a single row."""
        # Step 1 – correct date
        date = (
            fix_date_month(row.date, self._true_month, self._true_year)
            if self._true_month
            else row.date
        )

        # Rows with no clock data (weekends, holidays) – only fix the date
        if not row.entry_time or not row.exit_time:
            return dataclasses.replace(row, date=date)

        # Step 2 – shift entry
        new_entry = shift_time(
            row.entry_time, rng,
            min_shift=cfg.entry_min_shift,
            max_shift=cfg.entry_max_shift,
            clamp_low=cfg.entry_clamp_low,
            clamp_high=cfg.entry_clamp_high,
        )

        # Step 3 – shift exit
        new_exit = shift_time(
            row.exit_time, rng,
            min_shift=cfg.exit_min_shift,
            max_shift=cfg.exit_max_shift,
            clamp_low=cfg.exit_clamp_low,
            clamp_high=cfg.exit_clamp_high,
        )

        # Step 4 – guarantee minimum gap
        entry_m = time_to_minutes(new_entry)
        exit_m  = time_to_minutes(new_exit)
        if exit_m - entry_m < cfg.min_gap_minutes:
            exit_m = entry_m + cfg.min_gap_minutes + rng.randint(
                cfg.min_gap_extra_low, cfg.min_gap_extra_high
            )
            exit_m = min(exit_m, cfg.exit_clamp_high)
            new_exit = minutes_to_time(exit_m)

        # Step 5 – day-of-week
        day = date_to_hebrew_day(date) or row.day_of_week

        # Step 6 – total hours
        net_minutes = time_to_minutes(new_exit) - time_to_minutes(new_entry)
        total_h = round(net_minutes / 60.0, 2)

        return dataclasses.replace(
            row,
            date=date,
            entry_time=new_entry,
            exit_time=new_exit,
            day_of_week=day,
            total_hours=total_h,
        )

    # ── Hook 3 ────────────────────────────────────────────────────────────────

    def build_summary(
        self,
        new_rows: List[AttendanceRow],
        original_report: AttendanceReport,
    ) -> Tuple[AttendanceSummary, Dict[str, Any]]:
        """Recompute work_days, total_hours, and total_pay."""
        rate = (
            original_report.summary.hourly_rate
            if original_report.summary and original_report.summary.hourly_rate is not None
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
            f"Type-B transformed: {len(new_rows)} rows, "
            f"total={summary.total_hours}h, "
            f"pay={summary.total_pay}"
        )
        return summary, {}


# ── Backward-compatible wrappers ────────────────────────────────────────────

class TypeBTransformer(BaseTransformer, TypeBRowStrategy):
    """Concrete ``BaseTransformer`` for Type-B reports."""

    def transform(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> AttendanceReport:
        from src.transformers.transformation_service import TransformationService

        if report.report_type is None:
            report = dataclasses.replace(report, report_type=ReportType.TYPE_B)

        service = TransformationService({ReportType.TYPE_B: self})
        return service.transform(report, seed=seed, location_override=location_override)


# Keep TypeNTransformer as an alias for backward compat
TypeNTransformer = TypeBTransformer
TypeNRowStrategy = TypeBRowStrategy
