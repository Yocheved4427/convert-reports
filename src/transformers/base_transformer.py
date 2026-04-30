"""
Base transformer interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.attendance import AttendanceReport


class BaseTransformer(ABC):
    """Apply deterministic logical changes to a parsed report."""

    @abstractmethod
    def transform(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> AttendanceReport:
        ...
