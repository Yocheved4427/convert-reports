"""
Base parser interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union

from src.models import TypeAReport, TypeNReport
from src.ocr_utils import OCRRow


class BaseParser(ABC):
    """Parse OCR rows into a structured report dataclass."""

    @abstractmethod
    def parse(self, rows: List[OCRRow], pdf_path: str | Path = "") -> Union[TypeAReport, TypeNReport]:
        ...
