"""
Pipeline configuration.

Transformation rules are loaded from environment variables or a `.env` file,
falling back to sensible defaults.  Override any value without touching source
code, e.g.:

    TYPEA_ENTRY_MIN_SHIFT=-15 python main.py ...
    # or place the variables in a .env file at the project root.

All time-boundary values are in *minutes since midnight*:
    360 → 06:00,  600 → 10:00,  780 → 13:00,  1080 → 18:00,  1320 → 22:00
"""

from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TypeATransformConfig(BaseSettings):
    """Knobs for the Type-A (detailed/overtime) transformer."""

    model_config = SettingsConfigDict(
        env_prefix="TYPEA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Entry-time shift window (minutes)
    entry_min_shift: int = Field(default=-30, description="Max leftward shift for entry time")
    entry_max_shift: int = Field(default=30,  description="Max rightward shift for entry time")
    entry_clamp_low: int = Field(default=360, description="Earliest allowed entry (06:00)")
    entry_clamp_high: int = Field(default=600, description="Latest allowed entry (10:00)")

    # Exit-time shift window (minutes)
    exit_min_shift: int = Field(default=-30,  description="Max leftward shift for exit time")
    exit_max_shift: int = Field(default=30,   description="Max rightward shift for exit time")
    exit_clamp_low: int = Field(default=780,  description="Earliest allowed exit (13:00)")
    exit_clamp_high: int = Field(default=1320, description="Latest allowed exit (22:00)")

    # Gap constraints
    min_gap_minutes: int = Field(default=240, description="Minimum exit-entry gap (4 h)")
    max_gap_extra: int = Field(default=120,   description="Extra random minutes added when gap is too small")

    # Break choices (decimal hours)
    break_options: List[float] = Field(
        default=[0.0, 0.25, 0.50, 0.50, 0.50, 0.75, 1.0],
        description="Weighted pool of break durations in hours",
    )


class TypeBTransformConfig(BaseSettings):
    """Knobs for the Type-B (simple monthly) transformer."""

    model_config = SettingsConfigDict(
        env_prefix="TYPEB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Entry-time shift window (minutes)
    entry_min_shift: int = Field(default=-20, description="Max leftward shift for entry time")
    entry_max_shift: int = Field(default=20,  description="Max rightward shift for entry time")
    entry_clamp_low: int = Field(default=360, description="Earliest allowed entry (06:00)")
    entry_clamp_high: int = Field(default=600, description="Latest allowed entry (10:00)")

    # Exit-time shift window (minutes)
    exit_min_shift: int = Field(default=-20,  description="Max leftward shift for exit time")
    exit_max_shift: int = Field(default=20,   description="Max rightward shift for exit time")
    exit_clamp_low: int = Field(default=600,  description="Earliest allowed exit (10:00)")
    exit_clamp_high: int = Field(default=1080, description="Latest allowed exit (18:00)")

    # Gap constraints
    min_gap_minutes: int = Field(default=60,  description="Minimum exit-entry gap (1 h)")
    min_gap_extra_low: int = Field(default=30,  description="Lower bound of extra gap randomisation")
    min_gap_extra_high: int = Field(default=180, description="Upper bound of extra gap randomisation")


# Module-level singletons – import these in transformer code.
type_a_config = TypeATransformConfig()
type_b_config = TypeBTransformConfig()
type_n_config = type_b_config  # backward-compat alias
