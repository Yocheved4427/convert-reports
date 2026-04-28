"""
Base parser interface.

``BaseParser`` exposes two entry points:

* ``parse(rows, pdf_path)``  – abstract; accepts pre-extracted OCR rows.
  Used directly by tests and internally by ``parse_pdf``.
* ``parse_pdf(pdf_path)``    – **concrete**; runs OCR internally, then
  delegates to ``parse()``.  Production callers only need the PDF path.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union

from src.models import TypeAReport, TypeNReport
from src.ocr_utils import OCRRow, ocr_pdf

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Parse a PDF (or pre-extracted OCR rows) into a structured report."""

    # ── Abstract ──────────────────────────────────────────────────────────────

    @abstractmethod
    def parse(
        self,
        rows: List[OCRRow],
        pdf_path: str | Path = "",
    ) -> Union[TypeAReport, TypeNReport]:
        """Parse already-extracted OCR *rows* into a report dataclass.

        Args:
            rows:     OCR rows produced by ``ocr_pdf()`` or equivalent.
            pdf_path: Original PDF path (used only for metadata / logging).

        Returns:
            A frozen ``TypeAReport`` or ``TypeNReport`` dataclass instance.
        """
        ...

    # ── Concrete ──────────────────────────────────────────────────────────────

    def parse_pdf(
        self,
        pdf_path: str | Path,
    ) -> Union[TypeAReport, TypeNReport]:
        """Run OCR on *pdf_path* and parse the result in one call.

        This is the preferred entry-point for production code.  Tests that
        supply synthetic rows should continue to call ``parse()`` directly.

        Args:
            pdf_path: Path to the source PDF file.

        Returns:
            A frozen ``TypeAReport`` or ``TypeNReport`` dataclass instance.
        """
        pdf_path = Path(pdf_path)
        logger.info(f"parse_pdf: starting OCR → '{pdf_path.name}'")
        rows = ocr_pdf(pdf_path)
        logger.debug(f"parse_pdf: {len(rows)} OCR rows extracted from '{pdf_path.name}'")
        return self.parse(rows, pdf_path)
