"""
Transformer for Type-A reports (detailed attendance with overtime).

Rules (all thresholds driven by ``src.config.type_a_config``):
  1. Fix OCR month/year errors by enforcing the modal month across all rows.
  2. Shift entry time within configured bounds.
  3. Shift exit time within configured bounds.
  4. Ensure exit > entry by at least ``min_gap_minutes``.
  5. Recalculate day-of-week from the corrected date.
  6. Randomly select break duration from the configured pool.
  7. Recalculate net hours and overtime buckets (Israeli labour law).
  8. Resolve מקום עבודה via LocationRegistry → canonical ID + display name.
  9. Recompute summary totals.
"""

from __future__ import annotations

import dataclasses
import logging
import random
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from src.config import type_a_config as cfg
from src.location_registry import location_registry
from src.models import ReportType
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.transformers.base_transformer import BaseTransformer
from src.transformers.helpers import (
    compute_overtime_buckets,
    date_to_hebrew_day,
    fix_date_month,
    infer_true_month_year,
    minutes_to_time,
    shift_time,
    time_to_minutes,
)
from src.transformers.row_strategy import RowTransformStrategy

logger = logging.getLogger(__name__)


class TypeARowStrategy(RowTransformStrategy):
    """Per-row transformation strategy for Type-A (detailed/overtime) reports.

    State set by ``prepare()`` and consumed by ``transform_row()``:
      _true_month       – corrected month (int) or None
      _true_year        – corrected year  (int) or None
      _fallback_record  – modal LocationRecord used when a row lacks location
      _location_override – original override string (kept for per-row check)
    """

    # ── Hook 1 ────────────────────────────────────────────────────────────────

    def prepare(
        self,
        report: AttendanceReport,
        rng: random.Random,
        location_override: str,
    ) -> None:
        """Infer the true month/year and modal location for this report."""
        true_my = infer_true_month_year([r.date for r in report.rows])
        if true_my:
            self._true_month: Optional[int] = true_my[0]
            self._true_year:  Optional[int] = true_my[1]
            logger.debug(
                f"Type-A inferred month/year: "
                f"{self._true_month:02d}/{self._true_year}"
            )
        else:
            self._true_month = None
            self._true_year  = None

        self._location_override = location_override
        if location_override:
            self._fallback_record = location_registry.resolve(location_override)
        else:
            _resolved = [
                location_registry.resolve(r.location)
                for r in report.rows
                if r.location and r.location.strip()
            ]
            _known = [rec for rec in _resolved if rec.is_known]
            if _known:
                best_id = (
                    Counter(rec.location_id for rec in _known).most_common(1)[0][0]
                )
                self._fallback_record = next(
                    r for r in _known if r.location_id == best_id
                )
            elif _resolved:
                self._fallback_record = _resolved[0]
            else:
                self._fallback_record = location_registry.resolve("")

        logger.info(
            f"Type-A modal location: id='{self._fallback_record.location_id}' "
            f"display='{self._fallback_record.display_name}' "
            f"known={self._fallback_record.is_known}"
        )

    # ── Hook 2 ────────────────────────────────────────────────────────────────

    def transform_row(
        self,
        row: AttendanceRow,
        rng: random.Random,
    ) -> AttendanceRow:
        """Apply all Type-A transformation rules to a single row."""
        # Step 1 – correct date
        date = (
            fix_date_month(row.date, self._true_month, self._true_year)
            if self._true_month
            else row.date
        )

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
            exit_m = entry_m + cfg.min_gap_minutes + rng.randint(0, cfg.max_gap_extra)
            exit_m = min(exit_m, cfg.exit_clamp_high)
            new_exit = minutes_to_time(exit_m)

        # Step 5 – day-of-week
        day = date_to_hebrew_day(date) or row.day_of_week

        # Step 8b – resolve location for this row
        if self._location_override:
            loc_record = self._fallback_record
        else:
            raw_location = (row.location or "").strip()
            if raw_location:
                loc_record = location_registry.resolve(raw_location)
                if not loc_record.is_known and self._fallback_record.is_known:
                    loc_record = self._fallback_record
            else:
                loc_record = self._fallback_record
        location = (
            loc_record.display_name if loc_record.is_known
            else (self._location_override if self._location_override else "")
        )
        logger.debug(
            f"Row {row.date}: raw='{row.location}' "
            f"→ id='{loc_record.location_id}' known={loc_record.is_known}"
        )

        # Step 6 – pick break
        new_break = rng.choice(cfg.break_options)

        # Step 7 – net hours + overtime buckets
        gross_h = (time_to_minutes(new_exit) - time_to_minutes(new_entry)) / 60.0
        net_h   = round(max(0.0, gross_h - new_break), 2)
        h100, h125, h150 = compute_overtime_buckets(net_h)

        return dataclasses.replace(
            row,
            date=date,
            entry_time=new_entry,
            exit_time=new_exit,
            day_of_week=day,
            location=location,
            location_id=loc_record.location_id,
            break_minutes=new_break,
            total_hours=net_h,
            regular_hours=h100,
            overtime_125_hours=h125,
            overtime_150_hours=h150,
        )

    # ── Hook 3 ────────────────────────────────────────────────────────────────

    def build_summary(
        self,
        new_rows: List[AttendanceRow],
        original_report: AttendanceReport,
    ) -> Tuple[AttendanceSummary, Dict[str, Any]]:
        """Compute overtime bucket sums and report-level location ID."""
        summary = AttendanceSummary(
            work_days=len(new_rows),
            total_hours=round(sum(r.total_hours for r in new_rows), 2),
            regular_hours=round(sum(r.regular_hours or 0.0 for r in new_rows), 2),
            overtime_125_hours=round(sum(r.overtime_125_hours or 0.0 for r in new_rows), 2),
            overtime_150_hours=round(sum(r.overtime_150_hours or 0.0 for r in new_rows), 2),
        )
        extra: Dict[str, Any] = {
            "report_location_id": self._fallback_record.location_id,
        }
        logger.info(
            f"Type-A transformed: {len(new_rows)} rows, "
            f"total={summary.total_hours}h, "
            f"location_id='{self._fallback_record.location_id}'"
        )
        return summary, extra


# ── Backward-compatible wrapper ───────────────────────────────────────────────

class TypeATransformer(BaseTransformer, TypeARowStrategy):
    """Backward-compatible ``BaseTransformer`` that delegates to
    ``TransformationService`` with itself as the Type-A strategy.

    Existing callers (``ReportProcessorFactory``, tests) require zero changes.
    """

    def transform(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> AttendanceReport:
        from src.transformers.transformation_service import TransformationService

        # Ensure report_type is set so the service can dispatch correctly.
        if report.report_type is None:
            report = dataclasses.replace(report, report_type=ReportType.TYPE_A)

        service = TransformationService({ReportType.TYPE_A: self})
        return service.transform(report, seed=seed, location_override=location_override)
