"""
Models for Type-N reports (simple monthly attendance with pay summary).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.report_type import ReportType


class TypeNRow(BaseModel):
    """Single day row in a Type-N (simple monthly) report."""

    model_config = ConfigDict(frozen=True)

    date: str          # d/m/yy or dd/mm/yy
    day_of_week: str   # Hebrew day name
    entry_time: str    # HH:MM
    exit_time: str     # HH:MM
    total_hours: float = Field(ge=0.0, description="Working hours")

    @field_validator("entry_time", "exit_time", mode="before")
    @classmethod
    def _normalise_time(cls, v: str) -> str:
        """Accept HH.MM as well as HH:MM."""
        return v.replace(".", ":") if isinstance(v, str) else v


class TypeNSummary(BaseModel):
    """Top summary block in Type-N report."""

    model_config = ConfigDict(frozen=True)

    work_days: int     = Field(ge=0)
    total_hours: float = Field(ge=0.0)
    hourly_rate: float = Field(ge=0.0)
    total_pay: float   = Field(ge=0.0)


class TypeNReport(BaseModel):
    """Complete parsed Type-N report."""

    model_config = ConfigDict(frozen=True)

    report_type: ReportType = ReportType.TYPE_N
    header_text: str = ""
    company_name: str = ""
    employee_name: str = ""
    month_year: str = ""                          # e.g. "1/2023"
    rows: List[TypeNRow] = Field(default_factory=list)
    summary: Optional[TypeNSummary] = None
