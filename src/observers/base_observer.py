"""
TransformationObserver – abstract base for all transformation observers.

Any class that wishes to be notified after a row is successfully transformed
must subclass ``TransformationObserver`` and implement ``on_row_transformed``.
``TransformationService`` depends only on this interface, keeping it fully
decoupled from concrete observer implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.attendance import AttendanceRow


class TransformationObserver(ABC):
    """Abstract observer notified after each successfully transformed row."""

    @abstractmethod
    def on_row_transformed(
        self,
        original_row: AttendanceRow,
        transformed_row: AttendanceRow,
    ) -> None:
        """Called once per row immediately after a successful transformation.

        Args:
            original_row:    The row as it appeared in the parsed report.
            transformed_row: The row after the strategy has been applied.
        """
