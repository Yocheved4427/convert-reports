"""
PDF renderer – render an ``AttendanceReport`` to a PDF file.

Strategy: build an HTML representation first, then convert it to PDF
using WeasyPrint (if available) or fall back to writing the HTML with a
``.pdf.html`` extension and logging a warning.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.exceptions import RenderingError
from src.models.attendance import AttendanceReport
from src.renderers.base_renderer import BaseRenderer
from src.renderers.html_renderer import HtmlRenderer

logger = logging.getLogger(__name__)


class PdfRenderer(BaseRenderer):
    """Render an ``AttendanceReport`` to a PDF file via WeasyPrint.

    Falls back to an HTML file (with ``.html`` suffix) if WeasyPrint is not
    installed, so the pipeline never crashes in minimal environments.
    """

    def render(self, report: AttendanceReport, output_path: str | Path) -> None:
        """Write a PDF (or HTML fallback) to *output_path*.

        Args:
            report:      The (transformed) attendance report.
            output_path: Destination file path; should end in ``.pdf``.

        Raises:
            RenderingError: on any I/O error.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build HTML content using the shared renderer
        html_renderer = HtmlRenderer()
        html_content = html_renderer._build_html(report)

        try:
            import weasyprint  # type: ignore[import]
            try:
                weasyprint.HTML(string=html_content).write_pdf(str(output_path))
                logger.info(f"PdfRenderer: wrote '{output_path}' via WeasyPrint")
                return
            except Exception as exc:
                raise RenderingError(
                    f"WeasyPrint failed to write PDF '{output_path}': {exc}"
                ) from exc
        except ImportError:
            logger.warning(
                "WeasyPrint not installed – writing HTML fallback instead of PDF. "
                "Install weasyprint to enable true PDF output."
            )

        # Fallback: write HTML with renamed extension
        html_path = output_path.with_suffix(".html")
        try:
            html_path.write_text(html_content, encoding="utf-8")
            logger.info(f"PdfRenderer (HTML fallback): wrote '{html_path}'")
        except OSError as exc:
            raise RenderingError(
                f"Failed to write HTML fallback to '{html_path}': {exc}"
            ) from exc
