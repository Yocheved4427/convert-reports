"""
Base renderer interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

from src.models import TypeAReport, TypeNReport


class BaseRenderer(ABC):
    """Render a structured report to an Excel file."""

    @abstractmethod
    def render(self, report: Union[TypeAReport, TypeNReport],
               output_path: str | Path) -> None:
        ...
