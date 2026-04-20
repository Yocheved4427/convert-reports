"""
Transformer for Type-A reports (detailed attendance with overtime).

Rules:
  1. Shift entry time by ±15–45 min (stay within 06:00–10:00)
  2. Shift exit time by ±15–45 min (stay within 13:00–22:00)
  3. Ensure exit > entry, total hours between 4–14 hrs
  4. Keep break the same or adjust slightly (0–1 hr)
  5. Recalculate total_hours = (exit - entry) - break
  6. Re-split into 100%/125%/150% buckets (Israeli labour law)
  7. Recompute summary totals
"""

from __future__ import annotations

import logging
import random
from dataclasses import replace

from src.models import TypeAReport, TypeASummary
from src.transformers.base_transformer import BaseTransformer
from src.transformers.helpers import (
    compute_overtime_buckets, date_to_hebrew_day, minutes_to_time, shift_time,
    time_to_minutes,
)

logger = logging.getLogger(__name__)


class TypeATransformer(BaseTransformer):

    def transform(self, report: TypeAReport, seed: int = 42, location_override: str = "") -> TypeAReport:
        rng = random.Random(seed)

        new_rows = []
        for row in report.rows:
            # 1) Shift entry (clamp 06:00–10:00)
            new_entry = shift_time(
                row.entry_time, rng,
                min_shift=-30, max_shift=30,
                clamp_low=360, clamp_high=600,
            )

            # 2) Shift exit (clamp 13:00–22:00)
            new_exit = shift_time(
                row.exit_time, rng,
                min_shift=-30, max_shift=30,
                clamp_low=780, clamp_high=1320,
            )

            # 3) Ensure exit > entry with at least 4 hours gap
            entry_m = time_to_minutes(new_entry)
            exit_m = time_to_minutes(new_exit)
            if exit_m - entry_m < 240:
                exit_m = entry_m + 240 + rng.randint(0, 120)
                exit_m = min(exit_m, 1320)
                new_exit = minutes_to_time(exit_m)

            # Recalculate day of week from date
            day = date_to_hebrew_day(row.date) or row.day_of_week

            # Clear garbled location; apply override if provided
            location = location_override if location_override else ""

            # 4) Adjust break slightly
            break_options = [0.0, 0.25, 0.50, 0.50, 0.50, 0.75, 1.0]
            new_break = rng.choice(break_options)

            # 5) Calculate net hours
            gross_hours = (time_to_minutes(new_exit) - time_to_minutes(new_entry)) / 60.0
            net_hours = max(0.0, gross_hours - new_break)
            total_h = round(net_hours, 2)

            # 6) Split into overtime buckets
            h100, h125, h150 = compute_overtime_buckets(net_hours)

            new_rows.append(replace(
                row,
                entry_time=new_entry,
                exit_time=new_exit,
                day_of_week=day,
                location=location,
                break_minutes=new_break,
                total_hours=total_h,
                hours_100=h100,
                hours_125=h125,
                hours_150=h150,
            ))

        # 7) Recompute summary
        new_summary = TypeASummary(
            work_days=len(new_rows),
            total_hours=round(sum(r.total_hours for r in new_rows), 2),
            hours_100=round(sum(r.hours_100 for r in new_rows), 2),
            hours_125=round(sum(r.hours_125 for r in new_rows), 2),
            hours_150=round(sum(r.hours_150 for r in new_rows), 2),
        )

        new_report = replace(report, rows=new_rows, summary=new_summary)

        logger.info(
            f"Type-A transformed: {len(new_rows)} rows, "
            f"total={new_summary.total_hours}h"
        )
        return new_report
