"""
ReportProcessorFactory – Open/Closed factory for pipeline components.

Adding support for a new report type only requires:
  1.  Implementing the three layer classes (Parser / Transformer / Renderer).
  2.  Registering them in ``ReportProcessorFactory._registry`` – zero changes
      to ``main.py`` or any other existing code.

Container – Composition Root for dependency injection.

  Centralises all wiring of concrete strategy classes and returns fully
  configured service / factory / renderer instances.  ``main.py`` never
  needs to import strategy, decorator, renderer, or validator types directly.
"""

from __future__ import annotations

from typing import NamedTuple

from src.models import ReportType
from src.observers.logging_observer import LoggingObserver
from src.parsers.base_parser import BaseParser
from src.parsers.parser_factory import ParserFactory
from src.parsers.type_a_parser import TypeAParser
from src.parsers.type_n_parser import TypeNParser as TypeBParser
from src.renderers.base_renderer import BaseRenderer
from src.renderers.html_renderer import HtmlRenderer
from src.renderers.pdf_renderer import PdfRenderer
from src.renderers.type_a_renderer import TypeARenderer
from src.renderers.type_n_renderer import TypeNRenderer as TypeBRenderer
from src.services.transformation_service import TransformationService
from src.strategies.type_a_strategy import TypeATransformationStrategy
from src.strategies.type_b_strategy import TypeBTransformationStrategy
from src.strategies.validating_strategy_decorator import ValidatingStrategyDecorator
from src.transformers.base_transformer import BaseTransformer
from src.transformers.type_a_transformer import TypeATransformer
from src.transformers.type_n_transformer import TypeBTransformer
from src.validators.report_validator import ReportValidator


class PipelineComponents(NamedTuple):
    parser: BaseParser
    transformer: BaseTransformer
    renderer: BaseRenderer


class ReportProcessorFactory:
    """
    Returns freshly-instantiated pipeline components for a given ``ReportType``.

    Usage::

        components = ReportProcessorFactory.get(report_type)
        report     = components.parser.parse(rows, pdf_path)
        transformed = components.transformer.transform(report, seed=seed)
        components.renderer.render(transformed, output_path)
    """

    _registry: dict[ReportType, tuple[type, type, type]] = {
        ReportType.TYPE_A: (TypeAParser, TypeATransformer, TypeARenderer),
        ReportType.TYPE_B: (TypeBParser, TypeBTransformer, TypeBRenderer),
    }

    @classmethod
    def get(cls, report_type: ReportType) -> PipelineComponents:
        """Return (parser, transformer, renderer) for *report_type*.

        Resolves the report type exclusively through ``_registry``.

        Raises:
            KeyError: if *report_type* is not registered.
        """
        if report_type not in cls._registry:
            raise KeyError(
                f"No pipeline registered for ReportType '{report_type.value}'. "
                f"Registered types: {[t.value for t in cls._registry]}"
            )
        parser_cls, transformer_cls, renderer_cls = cls._registry[report_type]
        return PipelineComponents(
            parser=parser_cls(),
            transformer=transformer_cls(),
            renderer=renderer_cls(),
        )

    @classmethod
    def register(
        cls,
        report_type: ReportType,
        parser_cls: type,
        transformer_cls: type,
        renderer_cls: type,
    ) -> None:
        """Extend the factory at runtime (useful for plugins / testing)."""
        cls._registry[report_type] = (parser_cls, transformer_cls, renderer_cls)


class Container:
    """Composition Root – single place where all concrete dependencies are wired.

    ``main.py`` calls these static factory methods and remains completely
    decoupled from all concrete implementation types.
    """

    @staticmethod
    def get_transformation_service() -> TransformationService:
        """Build and return a fully-wired ``TransformationService``.

        Each strategy is wrapped in ``ValidatingStrategyDecorator`` so that
        every transformed row is automatically audited for logical consistency
        before it is accepted.

        Returns:
            A ready-to-use :class:`~src.services.transformation_service.TransformationService`.
        """
        strategy_registry = {
            "TYPE_A": ValidatingStrategyDecorator(TypeATransformationStrategy()),
            "TYPE_B": ValidatingStrategyDecorator(TypeBTransformationStrategy()),
        }
        return TransformationService(
            strategy_registry=strategy_registry,
            observers=[LoggingObserver()],
        )

    @staticmethod
    def get_parser_factory() -> ParserFactory:
        """Return a ready-to-use :class:`~src.parsers.parser_factory.ParserFactory`."""
        return ParserFactory()

    @staticmethod
    def get_html_renderer() -> HtmlRenderer:
        """Return a ready-to-use :class:`~src.renderers.html_renderer.HtmlRenderer`."""
        return HtmlRenderer()

    @staticmethod
    def get_pdf_renderer() -> PdfRenderer:
        """Return a ready-to-use :class:`~src.renderers.pdf_renderer.PdfRenderer`."""
        return PdfRenderer()

    @staticmethod
    def get_excel_renderer(report_type: ReportType) -> BaseRenderer:
        """Return the Excel/spreadsheet renderer for *report_type*.

        Delegates to :class:`ReportProcessorFactory` and returns only the
        renderer component so callers stay decoupled from pipeline internals.

        Args:
            report_type: The :class:`~src.models.ReportType` enum value.

        Returns:
            The renderer registered for *report_type*.
        """
        return ReportProcessorFactory.get(report_type).renderer

    @staticmethod
    def get_report_processor(report_type: ReportType) -> PipelineComponents:
        """Return the full pipeline components for *report_type*.

        Args:
            report_type: The :class:`~src.models.ReportType` enum value.

        Returns:
            :class:`PipelineComponents` namedtuple (parser, transformer, renderer).
        """
        return ReportProcessorFactory.get(report_type)

    @staticmethod
    def get_report_validator() -> ReportValidator:
        """Return a ready-to-use :class:`~src.validators.report_validator.ReportValidator`."""
        return ReportValidator()
