"""
TransformationService – orchestrates row transformation via the Strategy pattern.

Usage::

    from src.strategies import (
        TypeATransformationStrategy,
        TypeBTransformationStrategy,
        ValidatingStrategyDecorator,
    )
    from src.services.transformation_service import TransformationService

    registry = {
        "TYPE_A": ValidatingStrategyDecorator(TypeATransformationStrategy()),
        "TYPE_B": ValidatingStrategyDecorator(TypeBTransformationStrategy()),
    }
    service = TransformationService(strategy_registry=registry)
    transformed = service.transform(report, seed=42, location_override="")

Design constraints
------------------
* No ``if report_type == "TYPE_A"`` branching – dispatch is purely via registry.
* Row-level ``TransformationError`` is caught here; the original row is kept.
* Adding a new report type requires only a new strategy + one registry entry.
"""

from __future__ import annotations

import logging

from src.exceptions import TransformationError
from src.models.attendance import AttendanceReport, AttendanceRow
from src.strategies.base_strategy import BaseTransformationStrategy

logger = logging.getLogger(__name__)


class TransformationService:
    """Apply a per-row strategy to every row in an ``AttendanceReport``.

    Args:
        strategy_registry: Mapping from report-type string (e.g. ``"TYPE_A"``)
                           to a ``BaseTransformationStrategy`` instance.
                           Strategies should already be wrapped in
                           ``ValidatingStrategyDecorator``.
    """

    def __init__(
        self,
        strategy_registry: dict[str, BaseTransformationStrategy],
    ) -> None:
        self._registry = strategy_registry

    # ── Public API ────────────────────────────────────────────────────────────

    def transform(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> AttendanceReport:
        """Transform *report* using the strategy registered for its type.

        Args:
            report:            Parsed (frozen) ``AttendanceReport``.
            seed:              Random seed for deterministic output.
            location_override: Optional location name override.

        Returns:
            A new ``AttendanceReport`` with all transformations applied.

        Raises:
            KeyError: if no strategy is registered for the report type.
        """
        # Resolve the registry key from the report type
        rt = report.report_type
        key = rt.value if rt is not None else ""
        if key not in self._registry:
            raise KeyError(
                f"TransformationService: no strategy registered for "
                f"report type '{key}'.  Registered: {list(self._registry)}"
            )

        strategy = self._registry[key]

        # Let the strategy initialise report-level context
        strategy.prepare(report, seed, location_override)

        # Transform each row; fall back to original on validation failure
        new_rows: list[AttendanceRow] = []
        for row in report.rows:
            try:
                new_rows.append(strategy.transform_row(row))
            except TransformationError as exc:
                logger.warning(
                    "Row %s: validation failed (%s) – keeping original row",
                    row.date or "<unknown>",
                    exc,
                )
                new_rows.append(row)

        # Let the strategy rebuild the report (updates summary, location_id, etc.)
        return strategy.build_summary(new_rows, report)
