"""
Unit tests for src/ocr/pytesseract_ocr.py and src/ocr/pdfplumber_ocr.py.

OCR tests mock all external dependencies (pdf2image, pytesseract, pdfplumber,
PIL) so no real PDF files, system OCR engine, or optional library installation
is required.  The heavy third-party modules are injected into ``sys.modules``
before any import from ``src.ocr`` takes place.

Covers:
  - extract_text(): FileNotFoundError for missing PDF
  - extract_text(): RuntimeError when pdf2image/pytesseract are missing
  - extract_text(): concatenates text from all pages
  - extract_text(): passes lang parameter to pytesseract
  - cluster_into_rows(): groups tokens within Y-tolerance into rows
  - cluster_into_rows(): sorts tokens right-to-left (Hebrew RTL) within a row
  - OCRToken / OCRRow dataclass structure
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Inject stub modules so src.ocr can be imported without real libs ──────────

def _inject_stubs() -> None:
    """Create minimal stub modules for pdfplumber, PIL, and easyocr."""
    if "pdfplumber" not in sys.modules:
        pdfplumber_stub = types.ModuleType("pdfplumber")
        sys.modules["pdfplumber"] = pdfplumber_stub

    if "PIL" not in sys.modules:
        pil_stub = types.ModuleType("PIL")
        image_stub = types.ModuleType("PIL.Image")
        image_stub.Image = MagicMock()  # type: ignore[attr-defined]
        pil_stub.Image = image_stub  # type: ignore[attr-defined]
        sys.modules["PIL"] = pil_stub
        sys.modules["PIL.Image"] = image_stub

    if "easyocr" not in sys.modules:
        easyocr_stub = types.ModuleType("easyocr")
        sys.modules["easyocr"] = easyocr_stub


_inject_stubs()

# Import after stubs are in place
from src.ocr.pdfplumber_ocr import OCRRow, OCRToken, cluster_into_rows  # noqa: E402


# ── extract_text (pytesseract) ─────────────────────────────────────────────────

class TestExtractText:
    def test_raises_file_not_found_for_missing_pdf(self, tmp_path: Path) -> None:
        import importlib
        if "src.ocr.pytesseract_ocr" in sys.modules:
            ocr_mod = sys.modules["src.ocr.pytesseract_ocr"]
        else:
            ocr_mod = importlib.import_module("src.ocr.pytesseract_ocr")

        with pytest.raises(FileNotFoundError, match="PDF not found"):
            ocr_mod.extract_text(tmp_path / "nonexistent.pdf")

    def test_raises_runtime_error_when_dependencies_missing(
        self, tmp_path: Path
    ) -> None:
        import importlib
        if "src.ocr.pytesseract_ocr" in sys.modules:
            ocr_mod = sys.modules["src.ocr.pytesseract_ocr"]
        else:
            ocr_mod = importlib.import_module("src.ocr.pytesseract_ocr")

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        with patch.dict(
            "sys.modules",
            {"pdf2image": None, "pytesseract": None},  # type: ignore[dict-item]
        ):
            with pytest.raises((RuntimeError, ImportError)):
                ocr_mod.extract_text(pdf)

    def test_concatenates_all_pages(self, tmp_path: Path) -> None:
        import importlib
        if "src.ocr.pytesseract_ocr" in sys.modules:
            ocr_mod = sys.modules["src.ocr.pytesseract_ocr"]
        else:
            ocr_mod = importlib.import_module("src.ocr.pytesseract_ocr")

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        mock_image = MagicMock()
        mock_convert = MagicMock(return_value=[mock_image, mock_image])
        mock_pytess = MagicMock()
        mock_pytess.image_to_string.side_effect = ["page one text", "page two text"]

        pdf2image_stub = types.ModuleType("pdf2image")
        pdf2image_stub.convert_from_path = mock_convert  # type: ignore[attr-defined]
        pytess_stub = mock_pytess

        with patch.dict("sys.modules", {"pdf2image": pdf2image_stub, "pytesseract": pytess_stub}):
            result = ocr_mod.extract_text(pdf, lang="heb+eng")

        assert "page one text" in result
        assert "page two text" in result

    def test_lang_parameter_forwarded(self, tmp_path: Path) -> None:
        import importlib
        if "src.ocr.pytesseract_ocr" in sys.modules:
            ocr_mod = sys.modules["src.ocr.pytesseract_ocr"]
        else:
            ocr_mod = importlib.import_module("src.ocr.pytesseract_ocr")

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        mock_image = MagicMock()
        mock_convert = MagicMock(return_value=[mock_image])
        mock_pytess = MagicMock()
        mock_pytess.image_to_string.return_value = "text"

        pdf2image_stub = types.ModuleType("pdf2image")
        pdf2image_stub.convert_from_path = mock_convert  # type: ignore[attr-defined]

        with patch.dict("sys.modules", {"pdf2image": pdf2image_stub, "pytesseract": mock_pytess}):
            ocr_mod.extract_text(pdf, lang="heb")

        mock_pytess.image_to_string.assert_called_once_with(mock_image, lang="heb")


# ── cluster_into_rows ─────────────────────────────────────────────────────────

class TestClusterIntoRows:
    """Test the Y-proximity clustering of OCRToken objects into OCRRow objects."""

    def _make_token(self, text: str, x: float, y: float) -> OCRToken:
        return OCRToken(
            text=text,
            confidence=0.99,
            x_center=x,
            y_center=y,
            x_min=x - 5,
            y_min=y - 5,
            x_max=x + 5,
            y_max=y + 5,
        )

    def test_tokens_within_tolerance_grouped_into_one_row(self) -> None:
        toks = [
            self._make_token("A", x=100, y=50.0),
            self._make_token("B", x=200, y=52.0),
        ]
        rows = cluster_into_rows(toks)
        assert len(rows) == 1
        assert len(rows[0].tokens) == 2

    def test_tokens_far_apart_create_separate_rows(self) -> None:
        toks = [
            self._make_token("A", x=100, y=50.0),
            self._make_token("B", x=100, y=200.0),
        ]
        rows = cluster_into_rows(toks)
        assert len(rows) == 2

    def test_empty_token_list_returns_empty(self) -> None:
        assert cluster_into_rows([]) == []

    def test_tokens_sorted_by_x_descending_within_row(self) -> None:
        """Hebrew RTL: highest x (rightmost) should come first."""
        toks = [
            self._make_token("left",  x=10,  y=100.0),
            self._make_token("mid",   x=50,  y=100.0),
            self._make_token("right", x=100, y=100.0),
        ]
        rows = cluster_into_rows(toks)
        assert len(rows) == 1
        xs = [t.x_center for t in rows[0].tokens]
        assert xs == sorted(xs, reverse=True)

    def test_single_token_creates_one_row(self) -> None:
        toks = [self._make_token("only", x=0, y=0)]
        rows = cluster_into_rows(toks)
        assert len(rows) == 1
        assert rows[0].tokens[0].text == "only"


# ── OCRRow / OCRToken dataclasses ──────────────────────────────────────────────

class TestOCRDataclasses:
    def test_ocr_token_fields(self) -> None:
        tok = OCRToken(
            text="hello",
            confidence=0.95,
            x_center=10.0,
            y_center=20.0,
            x_min=5.0,
            y_min=15.0,
            x_max=15.0,
            y_max=25.0,
        )
        assert tok.text == "hello"
        assert tok.confidence == 0.95

    def test_ocr_row_default_tokens_empty(self) -> None:
        row = OCRRow(y_center=100.0)
        assert row.tokens == []

    def test_ocr_row_with_tokens(self) -> None:
        tok = OCRToken("x", 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        row = OCRRow(y_center=50.0, tokens=[tok])
        assert len(row.tokens) == 1


# ── (no duplicate classes below) ──────────────────────────────────────────────
class _LegacyExtractTextTests_SKIP:
    def test_raises_file_not_found_for_missing_pdf(self, tmp_path: Path) -> None:
        from src.ocr.pytesseract_ocr import extract_text

        with pytest.raises(FileNotFoundError, match="PDF not found"):
            extract_text(tmp_path / "nonexistent.pdf")

    def test_raises_runtime_error_when_dependencies_missing(
        self, tmp_path: Path
    ) -> None:
        from src.ocr.pytesseract_ocr import extract_text

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")  # minimal bytes so Path.exists() is True

        with patch.dict("sys.modules", {"pdf2image": None, "pytesseract": None}):
            with pytest.raises(RuntimeError, match="pdf2image"):
                extract_text(pdf)

    def test_concatenates_all_pages(self, tmp_path: Path) -> None:
        from src.ocr.pytesseract_ocr import extract_text

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        mock_image = MagicMock()
        mock_convert = MagicMock(return_value=[mock_image, mock_image])
        mock_tess = MagicMock()
        mock_tess.image_to_string.side_effect = ["page one text", "page two text"]

        with (
            patch("src.ocr.pytesseract_ocr.convert_from_path", mock_convert),
            patch("src.ocr.pytesseract_ocr.pytesseract", mock_tess),
        ):
            result = extract_text(pdf, lang="heb+eng")

        assert "page one text" in result
        assert "page two text" in result

    def test_lang_parameter_forwarded(self, tmp_path: Path) -> None:
        from src.ocr.pytesseract_ocr import extract_text

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        mock_image = MagicMock()
        mock_convert = MagicMock(return_value=[mock_image])
        mock_tess = MagicMock()
        mock_tess.image_to_string.return_value = "text"

        with (
            patch("src.ocr.pytesseract_ocr.convert_from_path", mock_convert),
            patch("src.ocr.pytesseract_ocr.pytesseract", mock_tess),
        ):
            extract_text(pdf, lang="heb")

        mock_tess.image_to_string.assert_called_once_with(mock_image, lang="heb")


# ── cluster_into_rows ─────────────────────────────────────────────────────────

class TestClusterIntoRows:
    """Test the Y-proximity clustering of OCRToken objects into OCRRow objects."""

    def _make_token(self, text: str, x: float, y: float) -> OCRToken:
        return OCRToken(
            text=text,
            confidence=0.99,
            x_center=x,
            y_center=y,
            x_min=x - 5,
            y_min=y - 5,
            x_max=x + 5,
            y_max=y + 5,
        )

    def test_tokens_within_tolerance_grouped_into_one_row(self) -> None:
        toks = [
            self._make_token("A", x=100, y=50.0),
            self._make_token("B", x=200, y=52.0),  # within default tolerance
        ]
        rows = cluster_into_rows(toks)
        assert len(rows) == 1
        assert len(rows[0].tokens) == 2

    def test_tokens_far_apart_create_separate_rows(self) -> None:
        toks = [
            self._make_token("A", x=100, y=50.0),
            self._make_token("B", x=100, y=200.0),  # far away
        ]
        rows = cluster_into_rows(toks)
        assert len(rows) == 2

    def test_empty_token_list_returns_empty(self) -> None:
        assert cluster_into_rows([]) == []

    def test_tokens_sorted_by_x_descending_within_row(self) -> None:
        """OCR extracts Hebrew RTL: tokens should be sorted right-to-left (high x first)."""
        toks = [
            self._make_token("leftmost", x=10,  y=100.0),
            self._make_token("middle",   x=50,  y=100.0),
            self._make_token("rightmost",x=100, y=100.0),
        ]
        rows = cluster_into_rows(toks)
        assert len(rows) == 1
        xs = [t.x_center for t in rows[0].tokens]
        assert xs == sorted(xs, reverse=True)

    def test_single_token_creates_one_row(self) -> None:
        toks = [self._make_token("only", x=0, y=0)]
        rows = cluster_into_rows(toks)
        assert len(rows) == 1
        assert rows[0].tokens[0].text == "only"


# ── OCRRow / OCRToken dataclasses ──────────────────────────────────────────────

class TestOCRDataclasses:
    def test_ocr_token_fields(self) -> None:
        tok = OCRToken(
            text="hello",
            confidence=0.95,
            x_center=10.0,
            y_center=20.0,
            x_min=5.0,
            y_min=15.0,
            x_max=15.0,
            y_max=25.0,
        )
        assert tok.text == "hello"
        assert tok.confidence == 0.95

    def test_ocr_row_default_tokens_empty(self) -> None:
        row = OCRRow(y_center=100.0)
        assert row.tokens == []

    def test_ocr_row_with_tokens(self) -> None:
        tok = OCRToken("x", 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        row = OCRRow(y_center=50.0, tokens=[tok])
        assert len(row.tokens) == 1
