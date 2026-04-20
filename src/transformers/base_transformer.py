"""
Base transformer interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Union

from src.models import TypeAReport, TypeNReport


class BaseTransformer(ABC):
    """Apply deterministic logical changes to a parsed report."""

    @abstractmethod
    def transform(self, report: Union[TypeAReport, TypeNReport],
                  seed: int = 42,
                  location_override: str = "") -> Union[TypeAReport, TypeNReport]:
        ...
