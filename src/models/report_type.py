"""
Report type enumeration.
"""

from __future__ import annotations

import enum


class ReportType(enum.Enum):
    """Two known report formats."""
    TYPE_A = "type_a"   # Detailed with overtime (100%/125%/150%), break, location
    TYPE_N = "type_n"   # Simple monthly: entry, exit, total, pay summary
