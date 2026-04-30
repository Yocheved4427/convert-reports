"""
Strategy pattern – abstract base for row-level transformation strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.attendance import AttendanceReport, AttendanceRow


class BaseTransformationStrategy(ABC):
    """Abstract base for per-row transformation strategies.

    The only required method is ``transform_row()``.
    ``prepare()`` and ``build_summary()`` are optional hooks that
    ``TransformationService`` will call when they exist.
    """

    @abstractmethod
    def transform_row(self, row: AttendanceRow) -> AttendanceRow:
        """Transform a single attendance row and return the new row."""
        ...

    def prepare(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> None:
        """Optional: initialise per-report state before the row loop.

        Called once by ``TransformationService`` before iterating rows.
        Override in concrete strategies that need report-level context
        (e.g. true month/year, modal location).
        """

    def build_summary(
        self,
        new_rows: list[AttendanceRow],
        original_report: AttendanceReport,
    ) -> AttendanceReport:
        """Optional: rebuild the report after all rows are transformed.

        Default implementation replaces ``rows`` in-place.
        Override to also update ``summary`` or other report-level fields.
        """
        import dataclasses
        return dataclasses.replace(original_report, rows=new_rows)
