"""
TransformationService – Strategy-pattern orchestrator.

This service owns the **only** transformation loop in the codebase.  It
delegates every type-specific decision to the ``RowTransformStrategy``
registered for the report's type.

Key design constraints
----------------------
* The service contains **no** ``if report_type == TYPE_A`` (or similar)
  branching.  Dispatch is handled entirely through the ``strategy_registry``
  dict look-up.
* The service does not know about time-shifting, location resolution, overtime
  buckets, or any other domain rule.  All of that lives in the strategies.
* Adding a new report type requires only registering a new strategy – zero
  changes to this class.

Usage
-----
    from src.models import ReportType
    from src.transformers.transformation_service import TransformationService
    from src.transformers.type_a_transformer import TypeATransformer
    from src.transformers.type_n_transformer import TypeNTransformer

    service = TransformationService({
        ReportType.TYPE_A: TypeATransformer(),
        ReportType.TYPE_N: TypeNTransformer(),
    })

    transformed = service.transform(report, seed=42, location_override="")
"""

from __future__ import annotations

import dataclasses
import logging
import random
from typing import Dict

from src.models import ReportType
from src.models.attendance import AttendanceReport
from src.transformers.row_strategy import RowTransformStrategy
from src.transformers.validating_decorator import TransformationError, ValidatingStrategyDecorator

logger = logging.getLogger(__name__)


class TransformationService:
    """Apply per-row transformation strategies to an ``AttendanceReport``.

    Args:
        strategy_registry: Mapping from ``ReportType`` to a concrete
                           ``RowTransformStrategy`` instance.
    """

    def __init__(self, strategy_registry: Dict[ReportType, RowTransformStrategy]) -> None:
        # Wrap every strategy with the validating decorator so that all
        # row-level invariants are enforced automatically, regardless of
        # which concrete strategy is registered.
        self._registry: Dict[ReportType, RowTransformStrategy] = {
            rt: ValidatingStrategyDecorator(s)
            for rt, s in strategy_registry.items()
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def transform(
        self,
        report: AttendanceReport,
        seed: int = 42,
        location_override: str = "",
    ) -> AttendanceReport:
        """Transform *report* using the strategy registered for its type.

        Algorithm (no type-specific branching here):
          1. Look up the strategy for ``report.report_type``.
          2. Build a seeded ``Random`` instance.
          3. Call ``strategy.prepare()`` once for report-level context.
          4. Iterate all rows, calling ``strategy.transform_row()`` on each.
          5. Call ``strategy.build_summary()`` to get the new summary and any
             extra report-level fields.
          6. Return a frozen copy of the report with updated rows, summary,
             and any extra fields.

        Args:
            report:            Parsed (frozen) ``AttendanceReport``.
            seed:              Random seed for deterministic output.
            location_override: Optional location name; passed straight through
                               to the strategy.

        Returns:
            A new frozen ``AttendanceReport`` with all transformations applied.

        Raises:
            KeyError: if no strategy is registered for ``report.report_type``.
        """
        report_type = report.report_type
        if report_type not in self._registry:
            raise KeyError(
                f"TransformationService: no strategy registered for "
                f"ReportType '{report_type}'.  "
                f"Registered: {list(self._registry)}"
            )

        strategy = self._registry[report_type]
        rng = random.Random(seed)

        # ── Step 1: let the strategy cache all report-level context ───────
        strategy.prepare(report, rng, location_override)

        # ── Step 2: transform each row (fall back on validation failure) ──
        new_rows = []
        for row in report.rows:
            try:
                new_rows.append(strategy.transform_row(row, rng))
            except TransformationError as exc:
                logger.warning(
                    "Row %s: transform validation failed (%s) – keeping original row",
                    row.date or "<unknown>",
                    exc,
                )
                new_rows.append(row)

        # ── Step 3: recompute summary + gather any extra report fields ────
        new_summary, extra_kwargs = strategy.build_summary(new_rows, report)

        # ── Step 4: assemble the transformed report ───────────────────────
        return dataclasses.replace(
            report,
            rows=new_rows,
            summary=new_summary,
            **extra_kwargs,
        )

    # ── Registry management ───────────────────────────────────────────────────

    def register(self, report_type: ReportType, strategy: RowTransformStrategy) -> None:
        """Add or replace the strategy for *report_type* at runtime."""
        self._registry[report_type] = strategy
