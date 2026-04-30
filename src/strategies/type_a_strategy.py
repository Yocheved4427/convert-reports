"""
Type-A transformation strategy (detailed attendance with overtime).

Implements ``BaseTransformationStrategy`` for Type-A (detailed/overtime) reports.

Transformation rules (all thresholds driven by ``src.config.type_a_config``):
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
from typing import List, Optional

from src.config import type_a_config as cfg
from src.location_registry import location_registry
from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.strategies.base_strategy import BaseTransformationStrategy
from src.transformers.helpers import (
    compute_overtime_buckets,
    date_to_hebrew_day,
    fix_date_month,
    infer_true_month_year,
    minutes_to_time,
    shift_time,
    time_to_minutes,
)

logger = logging.getLogger(__name__)


class TypeATransformationStrategy(BaseTransformationStrategy):
    """Concrete strategy for Type-A (detailed/overtime) attendance reports.

    The ``prepare()`` hook must be called once before the row loop so that
    report-level context (corrected month/year, modal location) is cached on
    ``self`` for use by ``transform_row()``.

    State set by ``prepare()`` and consumed by ``transform_row()``:
        _rng:               Seeded RNG for deterministic output.
        _true_month:        Corrected month (int) or ``None``.
        _true_year:         Corrected year  (int) or ``None``.
        _fallback_record:   Modal ``LocationRecord`` used when a row lacks
                            a recognisable location.
        _location_override: Original override string (kept for per-row check).
    """

    def __init__(self) -> None:
        self._rng: random.Random = random.Random(42)
        self._true_month: Optional[int] = None
        self._true_year: Optional[int] = None
        self._location_override: str = ""
        self._fallback_record = location_registry.resolve("")

    # ── Lifecycle: prepare ────────────────────────────────────────────────────

    def prepare(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> None:
        """Infer the true month/year and modal location for *report*.

        Args:
            report:            The full parsed report (read-only).
            seed:              Random seed for deterministic output.
            location_override: Optional CLI-supplied location name (may be ``""``).
        """
        self._rng = random.Random(seed)

        # ── Infer true month/year via voting ──────────────────────────────────
        true_my = infer_true_month_year([r.date for r in report.rows])
        if true_my:
            self._true_month, self._true_year = true_my
            logger.debug(
                "Type-A inferred month/year: %02d/%d",
                self._true_month,
                self._true_year,
            )
        else:
            self._true_month = None
            self._true_year = None

        # ── Resolve fallback location ─────────────────────────────────────────
        self._location_override = location_override
        if location_override:
            self._fallback_record = location_registry.resolve(location_override)
        else:
            resolved = [
                location_registry.resolve(r.location)
                for r in report.rows
                if r.location and r.location.strip()
            ]
            known = [rec for rec in resolved if rec.is_known]
            if known:
                best_id = (
                    Counter(rec.location_id for rec in known).most_common(1)[0][0]
                )
                self._fallback_record = next(
                    r for r in known if r.location_id == best_id
                )
            elif resolved:
                self._fallback_record = resolved[0]
            else:
                self._fallback_record = location_registry.resolve("")

        logger.info(
            "Type-A modal location: id=%r display=%r known=%s",
            self._fallback_record.location_id,
            self._fallback_record.display_name,
            self._fallback_record.is_known,
        )

    # ── Lifecycle: transform_row ──────────────────────────────────────────────

    def transform_row(self, row: AttendanceRow) -> AttendanceRow:
        """Apply all Type-A transformation rules to a single row.

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

        # Step 2 – shift entry time within configured bounds
        new_entry = shift_time(
            row.entry_time or "08:00",
            self._rng,
            min_shift=cfg.entry_min_shift,
            max_shift=cfg.entry_max_shift,
            clamp_low=cfg.entry_clamp_low,
            clamp_high=cfg.entry_clamp_high,
        )

        # Step 3 – shift exit time within configured bounds
        new_exit = shift_time(
            row.exit_time or "15:00",
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
                0, cfg.max_gap_extra
            )
            exit_m = min(exit_m, cfg.exit_clamp_high)
            new_exit = minutes_to_time(exit_m)

        # Step 5 – recalculate day-of-week from corrected date
        day = date_to_hebrew_day(date) or row.day_of_week

        # Step 6 – resolve canonical location
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
            loc_record.display_name
            if loc_record.is_known
            else (self._location_override or "")
        )
        logger.debug(
            "Row %s: raw=%r → id=%r known=%s",
            row.date,
            row.location,
            loc_record.location_id,
            loc_record.is_known,
        )

        # Step 7 – pick break duration from weighted pool
        new_break = self._rng.choice(cfg.break_options)

        # Step 8 – recalculate net hours and overtime buckets
        gross_hours = (time_to_minutes(new_exit) - time_to_minutes(new_entry)) / 60.0
        net_hours = round(max(0.0, gross_hours - new_break), 2)
        h100, h125, h150 = compute_overtime_buckets(net_hours)

        return dataclasses.replace(
            row,
            date=date,
            entry_time=new_entry,
            exit_time=new_exit,
            day_of_week=day,
            location=location,
            location_id=loc_record.location_id,
            break_minutes=new_break,
            total_hours=net_hours,
            regular_hours=h100,
            overtime_125_hours=h125,
            overtime_150_hours=h150,
        )

    # ── Lifecycle: build_summary ──────────────────────────────────────────────

    def build_summary(
        self,
        new_rows: List[AttendanceRow],
        original_report: AttendanceReport,
    ) -> AttendanceReport:
        """Recompute overtime bucket sums and assemble the updated report.

        Args:
            new_rows:        All transformed rows.
            original_report: The original report (used for non-row fields).

        Returns:
            A new frozen ``AttendanceReport`` with updated rows, summary,
            and ``report_location_id``.
        """
        summary = AttendanceSummary(
            work_days=len(new_rows),
            total_hours=round(sum(r.total_hours for r in new_rows), 2),
            regular_hours=round(
                sum(r.regular_hours or 0.0 for r in new_rows), 2
            ),
            overtime_125_hours=round(
                sum(r.overtime_125_hours or 0.0 for r in new_rows), 2
            ),
            overtime_150_hours=round(
                sum(r.overtime_150_hours or 0.0 for r in new_rows), 2
            ),
        )
        logger.info(
            "Type-A transformed: %d rows, total=%sh, location_id=%r",
            len(new_rows),
            summary.total_hours,
            self._fallback_record.location_id,
        )
        return dataclasses.replace(
            original_report,
            rows=new_rows,
            summary=summary,
            report_location_id=self._fallback_record.location_id,
        )
