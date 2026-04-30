"""
Unified domain model for all attendance report types.

A single ``AttendanceRow`` and ``AttendanceReport`` dataclass replace the
separate ``TypeARow`` / ``TypeNRow`` / ``TypeAReport`` / ``TypeNReport``
classes.

Fields that apply only to one report type carry ``Optional[…] = None`` so
that instances for the other report type simply leave them unset.

Type-A–only row fields
-----------------------
location       – canonical Hebrew display name
break_minutes  – break duration in decimal hours
hours_100      – regular hours @ 100 %
hours_125      – overtime @ 125 %
hours_150      – overtime @ 150 %
notes          – free-text notes
location_id    – stable ASCII slug from LocationRegistry

Type-N–only summary fields
---------------------------
hourly_rate    – configured hourly wage
total_pay      – total_hours × hourly_rate

Type-A–only summary fields
---------------------------
hours_100 / hours_125 / hours_150  – overtime bucket totals

Type-N–only report fields
--------------------------
company_name   – employer name printed at the top of the report

Type-A–only report fields
--------------------------
report_location_id  – canonical location_id shared by all rows
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.models.report_type import ReportType


# ── Row ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AttendanceRow:
    """Single day row – shared by all report types."""

    # ── required field ─────────────────────────────────────────────
    date: str                              # dd/mm/yyyy  or  d/m/yy

    # ── common optional fields ──────────────────────────────────────
    day_of_week:        Optional[str]   = None    # Hebrew day name
    entry_time:         Optional[str]   = None    # HH:MM
    exit_time:          Optional[str]   = None    # HH:MM
    total_hours:        float           = 0.0     # Net working hours (≥ 0)

    # ── Type-A–only fields (None for Type-B rows) ───────────────────
    location:            Optional[str]   = None  # Canonical Hebrew display name
    break_minutes:       Optional[float] = None  # Break in decimal hours (≥ 0)
    regular_hours:       Optional[float] = None  # Regular hours @ 100 %   (≥ 0)
    overtime_125_hours:  Optional[float] = None  # Overtime    @ 125 %     (≥ 0)
    overtime_150_hours:  Optional[float] = None  # Overtime    @ 150 %     (≥ 0)
    notes:               Optional[str]   = None  # Free-text notes
    location_id:         Optional[str]   = None  # Stable ASCII slug from LocationRegistry

    def __post_init__(self) -> None:
        """Normalise HH.MM → HH:MM for both time fields."""
        for f_name in ("entry_time", "exit_time"):
            val = getattr(self, f_name)
            if isinstance(val, str) and "." in val:
                object.__setattr__(self, f_name, val.replace(".", ":"))


# ── Summary ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AttendanceSummary:
    """Bottom / top summary block – shared by all report types."""

    # ── common fields ─────────────────────────────────
    work_days: int     = 0    # ≥ 0
    total_hours: float = 0.0  # ≥ 0

    # ── Type-A–only fields ──────────────────────────────
    regular_hours:      Optional[float] = None  # Regular hours @ 100 %
    overtime_125_hours: Optional[float] = None  # Overtime    @ 125 %
    overtime_150_hours: Optional[float] = None  # Overtime    @ 150 %

    # ── Type-B–only fields ──────────────────────────────
    hourly_rate: Optional[float] = None  # Configured hourly wage
    total_pay:   Optional[float] = None  # total_hours × hourly_rate


# ── Report ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AttendanceReport:
    """Complete parsed (and optionally transformed) attendance report.

    ``report_type`` distinguishes Type-A from Type-N at runtime.
    ``company_name`` is populated for Type-N reports only.
    ``report_location_id`` is populated for Type-A reports only.
    """

    # ── common fields ───────────────────────────────────────────────
    report_type: Optional[ReportType]        = None
    header_text: str                         = ""
    employee_name: str                       = ""
    month_year: str                          = ""   # e.g. "10/2022"
    rows: List[AttendanceRow]                = field(default_factory=list)
    summary: Optional[AttendanceSummary]     = None

    # ── Type-A–only field ───────────────────────────────────────────
    report_location_id: Optional[str]        = None  # canonical location_id

    # ── Type-N–only field ───────────────────────────────────────────
    company_name: Optional[str]              = None  # employer name
