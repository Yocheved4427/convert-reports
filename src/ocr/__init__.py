"""
OCR package – PDF text extraction.

Public API
----------
* ``extract_text(pdf_path) -> str``      – pytesseract-based full-page text
* ``ocr_pdf(pdf_path)   -> list[OCRRow]``– pdfplumber-based structured rows
* ``OCRRow``, ``OCRToken``               – row/token data classes
* ``parse_time``, ``parse_float``        – token parsing helpers
"""

from src.ocr.pdfplumber_ocr import (
    OCRRow,
    OCRToken,
    cluster_into_rows,
    extract_pdf_words,
    is_numeric_token,
    ocr_pdf,
    parse_float,
    parse_time,
)
from src.ocr.pytesseract_ocr import extract_text

__all__ = [
    "extract_text",
    "ocr_pdf",
    "OCRRow",
    "OCRToken",
    "cluster_into_rows",
    "extract_pdf_words",
    "is_numeric_token",
    "parse_float",
    "parse_time",
]
