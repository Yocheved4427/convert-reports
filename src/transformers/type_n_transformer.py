"""
Transformer for Type-N reports (simple monthly attendance).

Rules (all thresholds driven by ``src.config.type_n_config``):
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

from src.config import type_n_config as cfg
from src.models import TypeNReport, TypeNSummary
from src.transformers.base_transformer import BaseTransformer
from src.transformers.helpers import (
    date_to_hebrew_day,
    fix_date_month,
    infer_true_month_year,
    minutes_to_time,
    shift_time,
    time_to_minutes,
)

logger = logging.getLogger(__name__)


class TypeNTransformer(BaseTransformer):

    def transform(
        self,
        report: TypeNReport,
        seed: int = 42,
        location_override: str = "",  # not used by Type-N, kept for interface parity
    ) -> TypeNReport:
        rng = random.Random(seed)

        # ── Step 1: Fix OCR month/year errors ─────────────────────
        true_my = infer_true_month_year([r.date for r in report.rows])
        if true_my:
            true_month, true_year = true_my
            logger.debug(f"Type-N inferred month/year: {true_month:02d}/{true_year}")
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

            if not row.entry_time or not row.exit_time:
                new_rows.append(dataclasses.replace(row, date=date))
                continue

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
                exit_m = entry_m + cfg.min_gap_minutes + rng.randint(
                    cfg.min_gap_extra_low, cfg.min_gap_extra_high
                )
                exit_m = min(exit_m, cfg.exit_clamp_high)
                new_exit = minutes_to_time(exit_m)

            # ── Step 5: Recalculate day-of-week ───────────────────
            day = date_to_hebrew_day(date) or row.day_of_week

            # ── Step 6: Total hours ────────────────────────────────
            net_minutes = time_to_minutes(new_exit) - time_to_minutes(new_entry)
            total_h = round(net_minutes / 60.0, 2)

            new_rows.append(dataclasses.replace(
                row,
                date=date,
                entry_time=new_entry,
                exit_time=new_exit,
                day_of_week=day,
                total_hours=total_h,
            ))

        # ── Step 7: Recompute summary ──────────────────────────────
        rate = report.summary.hourly_rate if report.summary else 0.0
        total_hours = round(sum(r.total_hours for r in new_rows), 2)
        new_summary = TypeNSummary(
            work_days=len([r for r in new_rows if r.total_hours > 0]),
            total_hours=total_hours,
            hourly_rate=rate,
            total_pay=round(total_hours * rate, 2),
        )

        new_report = dataclasses.replace(report, rows=new_rows, summary=new_summary)

        logger.info(
            f"Type-N transformed: {len(new_rows)} rows, "
            f"total={new_summary.total_hours}h, "
            f"pay={new_summary.total_pay}"
        )
        return new_report
