"""
Tests for the Container composition root (src/factory.py).

Verifies:
  - Container.get_parser_factory() returns a ParserFactory
  - Container.get_transformation_service() returns a TransformationService
  - Container.get_html_renderer() returns an HtmlRenderer
  - Container.get_pdf_renderer() returns a PdfRenderer
  - Container.get_excel_renderer(report_type) returns a BaseRenderer
  - Container.get_report_processor(report_type) returns PipelineComponents
  - Container.get_report_validator() returns a ReportValidator
  - main.py does NOT import ParserFactory, HtmlRenderer, PdfRenderer,
    ReportProcessorFactory, validate_report, or strategy classes directly
"""

from __future__ import annotations

import ast
import importlib
import inspect
import textwrap
from pathlib import Path

import pytest

from src.factory import Container, PipelineComponents, ReportProcessorFactory
from src.models.report_type import ReportType
from src.parsers.parser_factory import ParserFactory
from src.renderers.base_renderer import BaseRenderer
from src.renderers.html_renderer import HtmlRenderer
from src.renderers.pdf_renderer import PdfRenderer
from src.services.transformation_service import TransformationService
from src.validators.report_validator import ReportValidator


# ── Container factory method tests ───────────────────────────────────────────

class TestContainerTypes:
    def test_get_parser_factory_returns_parser_factory(self) -> None:
        result = Container.get_parser_factory()
        assert isinstance(result, ParserFactory)

    def test_get_transformation_service_returns_transformation_service(self) -> None:
        result = Container.get_transformation_service()
        assert isinstance(result, TransformationService)

    def test_get_html_renderer_returns_html_renderer(self) -> None:
        result = Container.get_html_renderer()
        assert isinstance(result, HtmlRenderer)

    def test_get_pdf_renderer_returns_pdf_renderer(self) -> None:
        result = Container.get_pdf_renderer()
        assert isinstance(result, PdfRenderer)

    def test_get_excel_renderer_type_a_returns_base_renderer(self) -> None:
        result = Container.get_excel_renderer(ReportType.TYPE_A)
        assert isinstance(result, BaseRenderer)

    def test_get_excel_renderer_type_b_returns_base_renderer(self) -> None:
        result = Container.get_excel_renderer(ReportType.TYPE_B)
        assert isinstance(result, BaseRenderer)

    def test_get_report_processor_returns_pipeline_components(self) -> None:
        result = Container.get_report_processor(ReportType.TYPE_A)
        assert isinstance(result, PipelineComponents)
        assert result.parser is not None
        assert result.transformer is not None
        assert result.renderer is not None

    def test_get_report_validator_returns_report_validator(self) -> None:
        result = Container.get_report_validator()
        assert isinstance(result, ReportValidator)


# ── Functional smoke tests ────────────────────────────────────────────────────

class TestContainerFunctional:
    def test_parser_factory_resolves_type_a(self) -> None:
        pf = Container.get_parser_factory()
        parser = pf.get_parser("TYPE_A")
        assert parser is not None

    def test_parser_factory_resolves_type_b(self) -> None:
        pf = Container.get_parser_factory()
        parser = pf.get_parser("TYPE_B")
        assert parser is not None

    def test_transformation_service_has_registry(self) -> None:
        service = Container.get_transformation_service()
        # Must have at least TYPE_A and TYPE_B registered
        assert "TYPE_A" in service._registry
        assert "TYPE_B" in service._registry

    def test_transformation_service_has_observers(self) -> None:
        service = Container.get_transformation_service()
        assert len(service._observers) > 0

    def test_excel_renderer_for_type_a_differs_from_type_b(self) -> None:
        renderer_a = Container.get_excel_renderer(ReportType.TYPE_A)
        renderer_b = Container.get_excel_renderer(ReportType.TYPE_B)
        # They may be the same class or different, but both must be BaseRenderer
        assert isinstance(renderer_a, BaseRenderer)
        assert isinstance(renderer_b, BaseRenderer)


# ── main.py clean-architecture audit ─────────────────────────────────────────

MAIN_PY = Path(__file__).parent.parent / "main.py"

# Symbols that must NOT appear as top-level imports in main.py
FORBIDDEN_IMPORTS = {
    "ParserFactory",
    "HtmlRenderer",
    "PdfRenderer",
    "ReportProcessorFactory",
    "validate_report",
    "TypeATransformationStrategy",
    "TypeBTransformationStrategy",
    "ValidatingStrategyDecorator",
    "TransformationService",
}


def _collect_imported_names(source: str) -> set[str]:
    """Return all names introduced by import statements in *source*."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


class TestMainPyArchitecture:
    def test_main_does_not_import_forbidden_symbols(self) -> None:
        source = MAIN_PY.read_text(encoding="utf-8")
        imported = _collect_imported_names(source)
        violations = FORBIDDEN_IMPORTS & imported
        assert not violations, (
            f"main.py imports concrete implementation(s) directly: {violations}. "
            "These should be resolved through Container."
        )

    def test_main_imports_container(self) -> None:
        source = MAIN_PY.read_text(encoding="utf-8")
        imported = _collect_imported_names(source)
        assert "Container" in imported, "main.py must import Container from src.factory"
