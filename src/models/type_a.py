"""
Models for Type-A reports (detailed attendance with overtime breakdown).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.models.report_type import ReportType


@dataclass(frozen=True)
class TypeARow:
    """Single day row in a Type-A (detailed/overtime) report."""
    date: str            # dd/mm/yyyy
    day_of_week: str     # Hebrew day name
    location: str        # Work location
    entry_time: str      # HH:MM or HH.MM
    exit_time: str       # HH:MM or HH.MM
    break_minutes: float # Break duration in decimal hours (e.g. 0.50)
    total_hours: float   # Net working hours
    hours_100: float     # Regular hours (100%)
    hours_125: float     # Overtime at 125%
    hours_150: float     # Overtime at 150%
    notes: str = ""


@dataclass(frozen=True)
class TypeASummary:
    """Bottom summary block in Type-A report."""
    work_days: int
    total_hours: float
    hours_100: float
    hours_125: float
    hours_150: float


@dataclass(frozen=True)
class TypeAReport:
    """Complete parsed Type-A report."""
    report_type: ReportType = ReportType.TYPE_A
    header_text: str = ""
    employee_name: str = ""
    month_year: str = ""                              # e.g. "10/2022"
    rows: List[TypeARow] = field(default_factory=list)
    summary: Optional[TypeASummary] = None
