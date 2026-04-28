"""
Models for Type-A reports (detailed attendance with overtime breakdown).

Uses stdlib ``@dataclass(frozen=True)`` so instances are immutable value
objects.  Structural pattern-matching (``match``/``case``) can be used on
these classes because Python matches dataclasses by type and attribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.models.report_type import ReportType


@dataclass(frozen=True)
class TypeARow:
    """Single day row in a Type-A (detailed/overtime) report."""

    date: str                      # dd/mm/yyyy
    day_of_week: str               # Hebrew day name
    location: str                  # Canonical Hebrew display name
    entry_time: str                # HH:MM
    exit_time: str                 # HH:MM
    break_minutes: float = 0.0    # Break in decimal hours (≥ 0)
    total_hours: float   = 0.0    # Net working hours      (≥ 0)
    hours_100: float     = 0.0    # Regular hours @ 100%   (≥ 0)
    hours_125: float     = 0.0    # Overtime    @ 125%     (≥ 0)
    hours_150: float     = 0.0    # Overtime    @ 150%     (≥ 0)
    notes: str = ""
    location_id: str = ""         # Stable ASCII slug from LocationRegistry

    def __post_init__(self) -> None:
        """Normalise HH.MM → HH:MM for both time fields."""
        for f_name in ("entry_time", "exit_time"):
            val = getattr(self, f_name)
            if isinstance(val, str) and "." in val:
                object.__setattr__(self, f_name, val.replace(".", ":"))


@dataclass(frozen=True)
class TypeASummary:
    """Bottom summary block in Type-A report."""

    work_days: int     = 0    # ≥ 0
    total_hours: float = 0.0  # ≥ 0
    hours_100: float   = 0.0  # ≥ 0
    hours_125: float   = 0.0  # ≥ 0
    hours_150: float   = 0.0  # ≥ 0


@dataclass(frozen=True)
class TypeAReport:
    """Complete parsed Type-A report."""

    report_type: ReportType    = field(default=ReportType.TYPE_A)
    header_text: str           = ""
    employee_name: str         = ""
    month_year: str            = ""    # e.g. "10/2022"
    report_location_id: str    = ""    # canonical location_id shared by all rows
    rows: List[TypeARow]       = field(default_factory=list)
    summary: Optional[TypeASummary] = None
