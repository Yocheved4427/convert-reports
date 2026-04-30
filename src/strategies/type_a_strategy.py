"""
Type-A transformation strategy (detailed attendance with overtime).
Delegates to the existing TypeARowStrategy internals.
"""

from __future__ import annotations

import dataclasses
import random

from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.models.report_type import ReportType
from src.strategies.base_strategy import BaseTransformationStrategy
from src.transformers.type_a_transformer import TypeARowStrategy


class TypeATransformationStrategy(BaseTransformationStrategy):
    """Strategy for Type-A (detailed/overtime) reports."""

    def __init__(self) -> None:
        self._inner = TypeARowStrategy()
        self._rng: random.Random = random.Random(42)

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    def prepare(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> None:
        self._rng = random.Random(seed)
        self._inner.prepare(report, self._rng, location_override)

    def transform_row(self, row: AttendanceRow) -> AttendanceRow:
        return self._inner.transform_row(row, self._rng)

    def build_summary(
        self,
        new_rows: list[AttendanceRow],
        original_report: AttendanceReport,
    ) -> AttendanceReport:
        summary, extra_kwargs = self._inner.build_summary(new_rows, original_report)
        return dataclasses.replace(original_report, rows=new_rows, summary=summary, **extra_kwargs)
