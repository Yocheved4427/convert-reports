"""
TransformationService – report-level orchestrator for the Strategy pattern.

This service owns the **only** transformation loop in the codebase.  Every
type-specific decision is delegated exclusively to the ``BaseTransformationStrategy``
registered for the report type — zero ``if report_type == …`` branching exists
here.

Design principles
-----------------
* **Open/Closed**: adding a new report type requires only a new strategy class
  and one registry entry; this service never changes.
* **Single Responsibility**: the service knows how to *iterate* and *dispatch*,
  but knows nothing about time-shifting, overtime buckets, or location rules.
* **Decorator transparency**: strategies should be wrapped in
  ``ValidatingStrategyDecorator`` before being registered; the service does not
  know or care whether a decorator is present.

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
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.exceptions import TransformationError
from src.models.attendance import AttendanceReport, AttendanceRow
from src.observers.base_observer import TransformationObserver
from src.strategies.base_strategy import BaseTransformationStrategy

logger = logging.getLogger(__name__)


class TransformationService:
    """Apply a per-row ``BaseTransformationStrategy`` to an ``AttendanceReport``.

    The service is completely agnostic to the report type; dispatch is handled
    purely through the ``strategy_registry`` dictionary.

    Args:
        strategy_registry: Mapping from report-type string (e.g. ``"TYPE_A"``)
                           to a ``BaseTransformationStrategy`` instance.
                           Strategies should already be wrapped in
                           ``ValidatingStrategyDecorator`` to enforce row-level
                           invariants automatically.

    Example::

        service = TransformationService(
            strategy_registry={
                "TYPE_A": ValidatingStrategyDecorator(TypeATransformationStrategy()),
                "TYPE_B": ValidatingStrategyDecorator(TypeBTransformationStrategy()),
            }
        )
    """

    def __init__(
        self,
        strategy_registry: Dict[str, BaseTransformationStrategy],
        observers: Optional[List[TransformationObserver]] = None,
    ) -> None:
        self._registry: Dict[str, BaseTransformationStrategy] = strategy_registry
        self._observers: List[TransformationObserver] = observers if observers is not None else []

    # ── Public API ────────────────────────────────────────────────────────────

    def transform(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> AttendanceReport:
        """Transform *report* using the strategy registered for its type.

        Algorithm (no type-specific branching):
          1. Look up the strategy from the registry via ``report.report_type``.
          2. Call ``strategy.prepare()`` once with report-level context.
          3. Iterate all rows, calling ``strategy.transform_row()`` on each.
             On ``TransformationError`` the original (un-transformed) row is
             kept and a WARNING is logged so failures are always traceable.
          4. Call ``strategy.build_summary()`` to assemble the final report.

        Args:
            report:            Parsed (frozen) ``AttendanceReport``.
            seed:              Random seed for fully deterministic output.
            location_override: Optional workplace name; forwarded to strategy.

        Returns:
            A new frozen ``AttendanceReport`` with all transformations applied.

        Raises:
            KeyError: if no strategy is registered for ``report.report_type``.
        """
        # ── Step 1: resolve registry key ─────────────────────────────────────
        rt = report.report_type
        key = rt.value if rt is not None else ""
        if key not in self._registry:
            raise KeyError(
                f"TransformationService: no strategy registered for "
                f"report type {key!r}.  Registered: {sorted(self._registry)}"
            )

        strategy = self._registry[key]

        # ── Step 2: let the strategy cache all report-level context ───────────
        strategy.prepare(report, seed, location_override)

        # ── Step 3: transform each row, falling back on validation failure ────
        new_rows: list[AttendanceRow] = []
        for row in report.rows:
            try:
                transformed = strategy.transform_row(row)
                for observer in self._observers:
                    observer.on_row_transformed(row, transformed)
                new_rows.append(transformed)
            except TransformationError as exc:
                logger.warning(
                    "Row %s skipped (validation failure: %s) – original row kept.",
                    row.date or "<unknown>",
                    exc,
                )
                new_rows.append(row)

        # ── Step 4: rebuild the report (summary, location_id, …) ─────────────
        return strategy.build_summary(new_rows, report)
