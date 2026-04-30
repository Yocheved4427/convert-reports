"""
Report type enumeration.
"""

from __future__ import annotations

import enum


class ReportType(enum.Enum):
    """Two known report formats."""
    TYPE_A = "TYPE_A"   # Detailed with overtime (100%/125%/150%), break, location
    TYPE_B = "TYPE_B"   # Simple monthly: entry, exit, total, pay summary
