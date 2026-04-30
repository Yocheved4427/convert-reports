"""
Models package – re-exports all public symbols.

Preferred imports (unified domain model):
    from src.models import AttendanceRow, AttendanceSummary, AttendanceReport

Backward-compatible imports (still work via aliases):
    from src.models import ReportType, TypeAReport, TypeARow, TypeASummary, ...
"""

from src.models.report_type import ReportType
from src.models.attendance import AttendanceRow, AttendanceSummary, AttendanceReport

# Backward-compatible aliases
from src.models.type_a import TypeAReport, TypeARow, TypeASummary
from src.models.type_b import TypeBReport, TypeBRow, TypeBSummary
from src.models.type_n import TypeNReport, TypeNRow, TypeNSummary

__all__ = [
    # Unified domain model (preferred)
    "AttendanceRow",
    "AttendanceSummary",
    "AttendanceReport",
    # Report-type enum
    "ReportType",
    # Type-A aliases
    "TypeAReport",
    "TypeARow",
    "TypeASummary",
    # Type-B aliases
    "TypeBReport",
    "TypeBRow",
    "TypeBSummary",
    # Legacy Type-N aliases (backward compat)
    "TypeNReport",
    "TypeNRow",
    "TypeNSummary",
]
