"""
pytesseract_ocr.py – extract raw text from PDF files using Tesseract.

Uses ``pdf2image`` to render PDF pages to PIL images, then
``pytesseract`` to run Tesseract OCR with Hebrew + English support.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text(pdf_path: str | Path, lang: str = "heb+eng") -> str:
    """OCR a PDF file and return the raw text.

    Args:
        pdf_path: Path to the source PDF.
        lang:     Tesseract language string (default ``"heb+eng"``).

    Returns:
        Plain-text OCR output (may be empty if Tesseract finds nothing).

    Raises:
        FileNotFoundError: if *pdf_path* does not exist.
        RuntimeError: if pdf2image or pytesseract are unavailable.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image and pytesseract are required for OCR.  "
            "Install them with: pip install pdf2image pytesseract"
        ) from exc

    logger.info(f"OCR: converting '{pdf_path.name}' to images …")
    images = convert_from_path(str(pdf_path), dpi=300)

    pages: list[str] = []
    for i, image in enumerate(images):
        logger.debug(f"OCR: processing page {i + 1}/{len(images)} …")
        page_text = pytesseract.image_to_string(image, lang=lang)
        pages.append(page_text)

    full_text = "\n".join(pages)
    logger.info(f"OCR: extracted {len(full_text)} characters from '{pdf_path.name}'")
    return full_text
