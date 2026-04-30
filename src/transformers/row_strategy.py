"""
Row-level transformation strategy interface.

Part of the Strategy pattern implementation for report transformation.

``RowTransformStrategy`` defines the contract that every concrete strategy
must fulfill.  A strategy is responsible for **one** report type and knows
how to transform a **single row** – it never iterates over the full report
itself.  The iteration is owned exclusively by ``TransformationService``.

Lifecycle called by ``TransformationService.transform()``
----------------------------------------------------------
1. ``prepare(report, rng, location_override)``
       Called once before the row loop.
       Use it to derive any report-level context the row transformation
       needs (e.g. the corrected month/year, the modal location record).
       Store that context on ``self`` so ``transform_row()`` can read it.

2. ``transform_row(row, rng)  →  AttendanceRow``
       Called once per row.  Returns the transformed (frozen) row.
       Must not access ``self._report`` or iterate other rows.

3. ``build_summary(new_rows, original_report)  →  (AttendanceSummary, dict)``
       Called once after the row loop with all transformed rows.
       Returns the new summary and a (possibly empty) dict of additional
       ``dataclasses.replace`` kwargs for the report (e.g.
       ``{"report_location_id": "..."}``.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary


class RowTransformStrategy(ABC):
    """Abstract base for per-row transformation strategies.

    Concrete subclasses must implement all three methods.
    """

    @abstractmethod
    def prepare(
        self,
        report: AttendanceReport,
        rng: random.Random,
        location_override: str,
    ) -> None:
        """Compute and cache all report-level context needed by ``transform_row``.

        Args:
            report:            The full parsed report (read-only – do not mutate).
            rng:               The seeded Random instance shared for the whole run.
            location_override: Optional CLI-supplied location name (may be "").
        """
        ...

    @abstractmethod
    def transform_row(
        self,
        row: AttendanceRow,
        rng: random.Random,
    ) -> AttendanceRow:
        """Transform a single attendance row.

        Args:
            row: The original (frozen) row from the parsed report.
            rng: The seeded Random instance shared for the whole run.

        Returns:
            A new frozen ``AttendanceRow`` with all transformations applied.
        """
        ...

    @abstractmethod
    def build_summary(
        self,
        new_rows: List[AttendanceRow],
        original_report: AttendanceReport,
    ) -> Tuple[AttendanceSummary, Dict[str, Any]]:
        """Compute the post-transformation summary and any extra report fields.

        Args:
            new_rows:        All transformed rows (output of ``transform_row``).
            original_report: The original report (read-only; for e.g. the
                             hourly_rate stored in its summary).

        Returns:
            A 2-tuple of:
              - ``AttendanceSummary``  – the recomputed summary block.
              - ``dict``               – extra keyword arguments forwarded to
                                        ``dataclasses.replace(report, …)``
                                        (empty dict when not needed).
        """
        ...
