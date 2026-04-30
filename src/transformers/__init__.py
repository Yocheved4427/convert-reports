"""
Transformers package – backward-compatible legacy wrappers.

The canonical transformation logic lives in ``src.strategies``.
These wrappers exist solely for ``ReportProcessorFactory`` and legacy callers.

Public API::

    from src.transformers import TypeATransformer, TypeBTransformer, TypeNTransformer
"""

from src.transformers.type_a_transformer import TypeATransformer
from src.transformers.type_n_transformer import TypeBTransformer, TypeNTransformer

__all__ = [
    "TypeATransformer",
    "TypeBTransformer",
    "TypeNTransformer",
]
