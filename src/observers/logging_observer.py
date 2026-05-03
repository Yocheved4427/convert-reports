"""
LoggingObserver – concrete observer that logs each row transformation.
"""

from __future__ import annotations

import logging

from src.models.attendance import AttendanceRow
from src.observers.base_observer import TransformationObserver

logger = logging.getLogger(__name__)


class LoggingObserver(TransformationObserver):
    """Logs a DEBUG-level message for every successfully transformed row."""

    def on_row_transformed(
        self,
        original_row: AttendanceRow,
        transformed_row: AttendanceRow,
    ) -> None:
        logger.debug(
            "Row transformed | date=%s | original=%r | transformed=%r",
            original_row.date,
            original_row,
            transformed_row,
        )
