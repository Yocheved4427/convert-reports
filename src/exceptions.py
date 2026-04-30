"""
Custom exceptions for the attendance report pipeline.
"""

from __future__ import annotations


class TransformationError(Exception):
    """Raised when a transformed row fails validation."""

    def __init__(self, message: str, row_date: str = "") -> None:
        super().__init__(message)
        self.row_date = row_date


class UnsupportedReportTypeError(ValueError):
    """Raised when an unsupported report type is encountered."""


class ParsingError(ValueError):
    """Raised when a PDF cannot be parsed into a structured report."""


class RenderingError(RuntimeError):
    """Raised when a report cannot be rendered to the output format."""
