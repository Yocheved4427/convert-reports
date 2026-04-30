"""
Type-B report models – backward-compatible aliases.

All public names (``TypeBReport``, ``TypeBSummary``, ``TypeBRow``) are
aliases to the unified ``AttendanceRow`` / ``AttendanceSummary`` /
``AttendanceReport`` dataclasses defined in ``src.models.attendance``.

Existing import sites::

    from src.models.type_b import TypeBReport, TypeBRow, TypeBSummary
"""

from __future__ import annotations

from src.models.attendance import (
    AttendanceReport  as TypeBReport,
    AttendanceRow     as TypeBRow,
    AttendanceSummary as TypeBSummary,
)

__all__ = ["TypeBReport", "TypeBRow", "TypeBSummary"]
