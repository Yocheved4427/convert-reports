"""
ReportProcessorFactory – Open/Closed factory for pipeline components.

Adding support for a new report type only requires:
  1.  Implementing the three layer classes (Parser / Transformer / Renderer).
  2.  Registering them in ``ReportProcessorFactory._registry`` – zero changes
      to ``main.py`` or any other existing code.
"""

from __future__ import annotations

from typing import NamedTuple

from src.models import ReportType
from src.parsers.base_parser import BaseParser
from src.parsers.type_a_parser import TypeAParser
from src.parsers.type_n_parser import TypeNParser as TypeBParser
from src.renderers.base_renderer import BaseRenderer
from src.renderers.type_a_renderer import TypeARenderer
from src.renderers.type_n_renderer import TypeNRenderer as TypeBRenderer
from src.transformers.base_transformer import BaseTransformer
from src.transformers.type_a_transformer import TypeATransformer
from src.transformers.type_n_transformer import TypeBTransformer


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
