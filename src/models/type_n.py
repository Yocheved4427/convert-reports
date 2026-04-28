"""
Models for Type-N reports (simple monthly attendance with pay summary).

Uses stdlib ``@dataclass(frozen=True)`` so instances are immutable value
objects.  Structural pattern-matching (``match``/``case``) can be used on
these classes because Python matches dataclasses by type and attribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.models.report_type import ReportType


@dataclass(frozen=True)
class TypeNRow:
    """Single day row in a Type-N (simple monthly) report."""

    date: str           # d/m/yy or dd/mm/yy
    day_of_week: str    # Hebrew day name
    entry_time: str     # HH:MM
    exit_time: str      # HH:MM
    total_hours: float = 0.0  # Working hours (≥ 0)

    def __post_init__(self) -> None:
        """Normalise HH.MM → HH:MM for both time fields."""
        for f_name in ("entry_time", "exit_time"):
            val = getattr(self, f_name)
            if isinstance(val, str) and "." in val:
                object.__setattr__(self, f_name, val.replace(".", ":"))


@dataclass(frozen=True)
class TypeNSummary:
    """Top summary block in Type-N report."""

    work_days: int     = 0    # ≥ 0
    total_hours: float = 0.0  # ≥ 0
    hourly_rate: float = 0.0  # ≥ 0
    total_pay: float   = 0.0  # ≥ 0


@dataclass(frozen=True)
class TypeNReport:
    """Complete parsed Type-N report."""

    report_type: ReportType    = field(default=ReportType.TYPE_N)
    header_text: str           = ""
    company_name: str          = ""
    employee_name: str         = ""
    month_year: str            = ""    # e.g. "1/2023"
    rows: List[TypeNRow]       = field(default_factory=list)
    summary: Optional[TypeNSummary] = None
