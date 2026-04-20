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
  8. Recompute summary totals.
"""

from __future__ import annotations

import logging
import random

from src.config import type_a_config as cfg
from src.models import TypeAReport, TypeASummary
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

logger = logging.getLogger(__name__)


class TypeATransformer(BaseTransformer):

    def transform(
        self,
        report: TypeAReport,
        seed: int = 42,
        location_override: str = "",
    ) -> TypeAReport:
        rng = random.Random(seed)

        # ── Step 1: Fix OCR month/year errors ─────────────────────
        true_my = infer_true_month_year([r.date for r in report.rows])
        if true_my:
            true_month, true_year = true_my
            logger.debug(f"Type-A inferred month/year: {true_month:02d}/{true_year}")
        else:
            true_month, true_year = None, None

        new_rows = []
        for row in report.rows:
            # Correct the date if OCR garbled the month
            date = (
                fix_date_month(row.date, true_month, true_year)
                if true_month
                else row.date
            )

            # ── Step 2: Shift entry ────────────────────────────────
            new_entry = shift_time(
                row.entry_time, rng,
                min_shift=cfg.entry_min_shift,
                max_shift=cfg.entry_max_shift,
                clamp_low=cfg.entry_clamp_low,
                clamp_high=cfg.entry_clamp_high,
            )

            # ── Step 3: Shift exit ─────────────────────────────────
            new_exit = shift_time(
                row.exit_time, rng,
                min_shift=cfg.exit_min_shift,
                max_shift=cfg.exit_max_shift,
                clamp_low=cfg.exit_clamp_low,
                clamp_high=cfg.exit_clamp_high,
            )

            # ── Step 4: Guarantee minimum gap ─────────────────────
            entry_m = time_to_minutes(new_entry)
            exit_m  = time_to_minutes(new_exit)
            if exit_m - entry_m < cfg.min_gap_minutes:
                exit_m = entry_m + cfg.min_gap_minutes + rng.randint(0, cfg.max_gap_extra)
                exit_m = min(exit_m, cfg.exit_clamp_high)
                new_exit = minutes_to_time(exit_m)

            # ── Step 5: Recalculate day-of-week ───────────────────
            day = date_to_hebrew_day(date) or row.day_of_week

            # ── Location override / clear garbled OCR text ────────
            location = location_override if location_override else ""

            # ── Step 6: Pick break ────────────────────────────────
            new_break = rng.choice(cfg.break_options)

            # ── Step 7: Net hours + buckets ───────────────────────
            gross_h = (time_to_minutes(new_exit) - time_to_minutes(new_entry)) / 60.0
            net_h   = round(max(0.0, gross_h - new_break), 2)
            h100, h125, h150 = compute_overtime_buckets(net_h)

            new_rows.append(row.model_copy(update=dict(
                date=date,
                entry_time=new_entry,
                exit_time=new_exit,
                day_of_week=day,
                location=location,
                break_minutes=new_break,
                total_hours=net_h,
                hours_100=h100,
                hours_125=h125,
                hours_150=h150,
            )))

        # ── Step 8: Recompute summary ──────────────────────────────
        new_summary = TypeASummary(
            work_days=len(new_rows),
            total_hours=round(sum(r.total_hours for r in new_rows), 2),
            hours_100=round(sum(r.hours_100 for r in new_rows), 2),
            hours_125=round(sum(r.hours_125 for r in new_rows), 2),
            hours_150=round(sum(r.hours_150 for r in new_rows), 2),
        )

        new_report = report.model_copy(update=dict(rows=new_rows, summary=new_summary))

        logger.info(
            f"Type-A transformed: {len(new_rows)} rows, "
            f"total={new_summary.total_hours}h"
        )
        return new_report
