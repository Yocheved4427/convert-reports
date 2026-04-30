"""
Type-A report models – backward-compatible aliases.

All public names (``TypeARow``, ``TypeASummary``, ``TypeAReport``) are now
aliases to the unified ``AttendanceRow`` / ``AttendanceSummary`` /
``AttendanceReport`` dataclasses defined in ``src.models.attendance``.

Existing import sites require no changes::

    from src.models.type_a import TypeAReport, TypeARow, TypeASummary
"""

from __future__ import annotations

from src.models.attendance import (
    AttendanceReport as TypeAReport,
    AttendanceRow    as TypeARow,
    AttendanceSummary as TypeASummary,
)

__all__ = ["TypeAReport", "TypeARow", "TypeASummary"]
