"""
Base parser – Template Method pattern.

``BaseParser.parse()`` is the **template method**: it owns the fixed
algorithm skeleton and delegates each variable step to abstract hooks that
concrete subclasses must implement.

Algorithm skeleton (in ``parse()``)
-------------------------------------
1. Derive ``header_text`` from the PDF path (concrete helper).
2. Call ``_parse_summary(rows)`` – subclass extracts the summary block.
3. Iterate every OCR row:
       - Skip it if ``_is_header_line(row)`` returns True.
       - Otherwise call ``_parse_row(row)`` to convert it to an
         ``AttendanceRow`` (or ``None`` to skip blank/invalid rows).
4. Call ``_build_report(header_text, data_rows, summary)`` to assemble the
   final ``AttendanceReport``.

Public entry-points
--------------------
* ``parse(rows, pdf_path)``  – concrete template method; used by tests.
* ``parse_pdf(pdf_path)``    – concrete; runs OCR then calls ``parse()``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from src.models.attendance import AttendanceReport, AttendanceRow, AttendanceSummary
from src.ocr import OCRRow, ocr_pdf

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Parse a PDF (or pre-extracted OCR rows) into a structured report.

    Subclasses implement the four abstract hooks; they must **not** override
    ``parse()`` or ``parse_pdf()``.
    """

    # ── Abstract hooks ────────────────────────────────────────────────────────

    @abstractmethod
    def _is_header_line(self, row: OCRRow) -> bool:
        """Return ``True`` if *row* is a non-data line that should be skipped.

        Examples: column-header rows, separator lines, page-number lines.
        Returning ``False`` (default) means the row is passed to
        ``_parse_row()``.
        """
        ...

    @abstractmethod
    def _parse_row(self, row: OCRRow) -> Optional[AttendanceRow]:
        """Convert a single OCR data row into an ``AttendanceRow``.

        Return ``None`` to discard the row (e.g. blank weekends, rows without
        a recognisable date).
        """
        ...

    @abstractmethod
    def _parse_summary(self, rows: List[OCRRow]) -> Optional[AttendanceSummary]:
        """Extract the summary block from the full list of OCR rows.

        May return ``None`` when no summary is present in the source PDF.
        Called once before the per-row loop so that subclasses can set any
        state they need (e.g. the y-coordinate boundary of the summary area).
        """
        ...

    @abstractmethod
    def _build_report(
        self,
        header_text: str,
        data_rows: List[AttendanceRow],
        summary: Optional[AttendanceSummary],
    ) -> AttendanceReport:
        """Assemble the final ``AttendanceReport`` from the parsed pieces.

        The subclass fills in report-type–specific fields (``report_type``,
        ``employee_name``, ``company_name``, ``report_location_id``, …) and
        derives ``month_year`` from the first data row.
        """
        ...

    # ── Template method (concrete – do not override) ──────────────────────────

    def parse(
        self,
        rows: List[OCRRow],
        pdf_path: str | Path = "",
    ) -> AttendanceReport:
        """Parse already-extracted OCR *rows* into an ``AttendanceReport``.

        This is the **template method**: the algorithm skeleton is fixed here;
        subclasses customise behaviour exclusively via the abstract hooks.

        Args:
            rows:     OCR rows produced by ``ocr_pdf()`` or equivalent.
            pdf_path: Original PDF path (used only for metadata / logging).

        Returns:
            A frozen ``AttendanceReport`` dataclass instance.
        """
        # Step 1 – header text
        header_text = Path(pdf_path).stem if pdf_path else ""

        # Step 2 – summary block (may also set instance state used by hooks)
        summary = self._parse_summary(rows)

        # Step 3 – iterate rows
        data_rows: List[AttendanceRow] = []
        for row in rows:
            if self._is_header_line(row):
                continue
            parsed = self._parse_row(row)
            if parsed is not None:
                data_rows.append(parsed)

        # Step 4 – assemble report
        return self._build_report(header_text, data_rows, summary)

    # ── Concrete convenience method ───────────────────────────────────────────

    def parse_pdf(self, pdf_path: str | Path) -> AttendanceReport:
        """Run OCR on *pdf_path* and parse the result in one call.

        This is the preferred entry-point for production code.  Tests that
        supply synthetic rows should continue to call ``parse()`` directly.

        Args:
            pdf_path: Path to the source PDF file.

        Returns:
            A frozen ``AttendanceReport`` dataclass instance.
        """
        pdf_path = Path(pdf_path)
        logger.info(f"parse_pdf: starting OCR → '{pdf_path.name}'")
        rows = ocr_pdf(pdf_path)
        logger.debug(f"parse_pdf: {len(rows)} OCR rows extracted from '{pdf_path.name}'")
        return self.parse(rows, pdf_path)
