"""
Type-A transformer – backward-compatible ``BaseTransformer`` wrapper.

``TypeATransformer`` implements the legacy ``BaseTransformer`` interface used
by ``ReportProcessorFactory``.  All transformation logic lives in
``TypeATransformationStrategy``; this class is a thin delegation shell.

Downstream callers (``ReportProcessorFactory``, legacy tests) require zero
changes.
"""

from __future__ import annotations

import dataclasses

from src.models.attendance import AttendanceReport
from src.models.report_type import ReportType
from src.transformers.base_transformer import BaseTransformer


class TypeATransformer(BaseTransformer):
    """Backward-compatible ``BaseTransformer`` for Type-A reports.

    Delegates to ``ValidatingStrategyDecorator(TypeATransformationStrategy())``
    via ``TransformationService``.  Existing callers (``ReportProcessorFactory``,
    legacy tests) require zero changes.
    """

    def transform(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> AttendanceReport:
        """Transform *report* using the canonical Type-A strategy.

        Args:
            report:            Parsed ``AttendanceReport`` (frozen).
            seed:              Random seed for deterministic output.
            location_override: Optional workplace location override.

        Returns:
            A new frozen ``AttendanceReport`` with all transformations applied.
        """
        if report.report_type is None:
            report = dataclasses.replace(report, report_type=ReportType.TYPE_A)

        from src.services.transformation_service import TransformationService  # lazy – avoids circular import
        from src.strategies.type_a_strategy import TypeATransformationStrategy  # lazy
        from src.strategies.validating_strategy_decorator import ValidatingStrategyDecorator  # lazy
        service = TransformationService(
            strategy_registry={
                ReportType.TYPE_A.value: ValidatingStrategyDecorator(
                    TypeATransformationStrategy()
                )
            }
        )
        return service.transform(report, seed=seed, location_override=location_override)
