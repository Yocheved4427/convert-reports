"""
conftest.py – project-wide pytest configuration.

Stubs out heavy optional C-extension / binary libraries (pdfplumber, openpyxl,
weasyprint, pytesseract, PIL) so that unit tests can import any module in the
package without needing those packages installed in the test environment.

Tests that actually exercise PDF/OCR/Excel functionality are expected to mock
at the call-site level (see tests/test_parsers.py, tests/test_ocr.py, etc.).
"""

from __future__ import annotations

import sys
import types


def _make_stub(name: str, **attrs) -> types.ModuleType:
    """Return a minimal stub module registered under *name*."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# ── pdfplumber ────────────────────────────────────────────────────────────────
if "pdfplumber" not in sys.modules:
    _make_stub("pdfplumber")

# ── openpyxl ─────────────────────────────────────────────────────────────────
if "openpyxl" not in sys.modules:
    def _noop_cls(*args, **kwargs):
        return None

    class _Stub:
        def __init__(self, *args, **kwargs):
            pass

    openpyxl_stub = _make_stub("openpyxl", Workbook=_Stub)
    _make_stub(
        "openpyxl.styles",
        Font=_Stub,
        Alignment=_Stub,
        PatternFill=_Stub,
        Border=_Stub,
        Side=_Stub,
    )
    _make_stub("openpyxl.utils", get_column_letter=lambda i: "A")

# ── weasyprint ────────────────────────────────────────────────────────────────
if "weasyprint" not in sys.modules:
    _make_stub("weasyprint", HTML=object)

# ── pytesseract ───────────────────────────────────────────────────────────────
if "pytesseract" not in sys.modules:
    _make_stub("pytesseract")

# ── PIL / Pillow ──────────────────────────────────────────────────────────────
if "PIL" not in sys.modules:
    _make_stub("PIL")
    _make_stub("PIL.Image", open=lambda *a, **kw: None)
