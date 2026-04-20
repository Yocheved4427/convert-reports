from __future__ import annotations

import logging
import random
from dataclasses import replace

from src.models import TypeNReport, TypeNSummary
from src.transformers.base_transformer import BaseTransformer
from src.transformers.helpers import (
    date_to_hebrew_day, minutes_to_time, shift_time, time_to_minutes,
)

logger = logging.getLogger(__name__)


class TypeNTransformer(BaseTransformer):

    def transform(self, report: TypeNReport, seed: int = 42, location_override: str = "") -> TypeNReport:
        rng = random.Random(seed)

        new_rows = []
        for row in report.rows:
            if not row.entry_time or not row.exit_time:
                new_rows.append(row)
                continue

            # 1) Shift entry (clamp 06:00–10:00)
            new_entry = shift_time(
                row.entry_time, rng,
                min_shift=-20, max_shift=20,
                clamp_low=360, clamp_high=600,
            )

            # 2) Shift exit (clamp 10:00–18:00)
            new_exit = shift_time(
                row.exit_time, rng,
                min_shift=-20, max_shift=20,
                clamp_low=600, clamp_high=1080,
            )

            # 3) Ensure exit > entry with at least 1-hour gap
            entry_m = time_to_minutes(new_entry)
            exit_m = time_to_minutes(new_exit)
            if exit_m - entry_m < 60:
                exit_m = entry_m + 60 + rng.randint(30, 180)
                exit_m = min(exit_m, 1080)
                new_exit = minutes_to_time(exit_m)

            # Recalculate day of week from date
            day = date_to_hebrew_day(row.date) or row.day_of_week

            # 4) Recalculate total hours
            net_minutes = time_to_minutes(new_exit) - time_to_minutes(new_entry)
            total_h = round(net_minutes / 60.0, 2)

            new_rows.append(replace(
                row,
                entry_time=new_entry,
                exit_time=new_exit,
                day_of_week=day,
                total_hours=total_h,
            ))

        # 5) Recompute summary
        rate = report.summary.hourly_rate if report.summary else 0
        total_hours = round(sum(r.total_hours for r in new_rows), 2)
        new_summary = TypeNSummary(
            work_days=len([r for r in new_rows if r.total_hours > 0]),
            total_hours=total_hours,
            hourly_rate=rate,
            total_pay=round(total_hours * rate, 2),
        )

        new_report = replace(report, rows=new_rows, summary=new_summary)

        logger.info(
            f"Type-N transformed: {len(new_rows)} rows, "
            f"total={new_summary.total_hours}h, "
            f"pay={new_summary.total_pay}"
        )
        return new_report
