"""
Models for Type-N reports (simple monthly attendance with pay summary).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.models.report_type import ReportType


@dataclass(frozen=True)
class TypeNRow:
    """Single day row in a Type-N (simple monthly) report."""
    date: str            # d/m/yy or dd/mm/yy
    day_of_week: str     # Hebrew day name
    entry_time: str      # HH:MM or HH.MM
    exit_time: str       # HH:MM or HH.MM
    total_hours: float   # Working hours


@dataclass(frozen=True)
class TypeNSummary:
    """Top summary block in Type-N report."""
    work_days: int
    total_hours: float
    hourly_rate: float
    total_pay: float


@dataclass(frozen=True)
class TypeNReport:
    """Complete parsed Type-N report."""
    report_type: ReportType = ReportType.TYPE_N
    header_text: str = ""
    company_name: str = ""
    employee_name: str = ""
    month_year: str = ""                              # e.g. "1/2023"
    rows: List[TypeNRow] = field(default_factory=list)
    summary: Optional[TypeNSummary] = None
