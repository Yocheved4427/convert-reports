"""
Models for Type-A reports (detailed attendance with overtime breakdown).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.report_type import ReportType


class TypeARow(BaseModel):
    """Single day row in a Type-A (detailed/overtime) report."""

    model_config = ConfigDict(frozen=True)

    date: str            # dd/mm/yyyy
    day_of_week: str     # Hebrew day name
    location: str        # Work location
    entry_time: str      # HH:MM
    exit_time: str       # HH:MM
    break_minutes: float = Field(ge=0.0, description="Break in decimal hours")
    total_hours: float   = Field(ge=0.0, description="Net working hours")
    hours_100: float     = Field(ge=0.0, description="Regular hours at 100%")
    hours_125: float     = Field(ge=0.0, description="Overtime at 125%")
    hours_150: float     = Field(ge=0.0, description="Overtime at 150%")
    notes: str = ""

    @field_validator("entry_time", "exit_time", mode="before")
    @classmethod
    def _normalise_time(cls, v: str) -> str:
        """Accept HH.MM as well as HH:MM."""
        return v.replace(".", ":") if isinstance(v, str) else v


class TypeASummary(BaseModel):
    """Bottom summary block in Type-A report."""

    model_config = ConfigDict(frozen=True)

    work_days: int   = Field(ge=0)
    total_hours: float = Field(ge=0.0)
    hours_100: float   = Field(ge=0.0)
    hours_125: float   = Field(ge=0.0)
    hours_150: float   = Field(ge=0.0)


class TypeAReport(BaseModel):
    """Complete parsed Type-A report."""

    model_config = ConfigDict(frozen=True)

    report_type: ReportType = ReportType.TYPE_A
    header_text: str = ""
    employee_name: str = ""
    month_year: str = ""                          # e.g. "10/2022"
    rows: List[TypeARow] = Field(default_factory=list)
    summary: Optional[TypeASummary] = None
