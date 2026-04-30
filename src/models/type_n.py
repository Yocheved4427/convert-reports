"""
Type-N report models – backward-compatible aliases.

All public names (``TypeNRow``, ``TypeNSummary``, ``TypeNReport``) are now
aliases to the unified ``AttendanceRow`` / ``AttendanceSummary`` /
``AttendanceReport`` dataclasses defined in ``src.models.attendance``.

Existing import sites require no changes::

    from src.models.type_n import TypeNReport, TypeNRow, TypeNSummary
"""

from __future__ import annotations

# Backward-compatible aliases – now delegate to type_b
from src.models.type_b import (
    TypeBReport as TypeNReport,
    TypeBRow    as TypeNRow,
    TypeBSummary as TypeNSummary,
)

__all__ = ["TypeNReport", "TypeNRow", "TypeNSummary"]
