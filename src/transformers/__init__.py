"""
Transformers package.

Public API::

    from src.transformers import (
        TransformationService,
        RowTransformStrategy,
        TransformationError,
        ValidatingStrategyDecorator,
        TypeATransformer, TypeARowStrategy,
        TypeNTransformer, TypeNRowStrategy,
    )
"""

from src.transformers.row_strategy import RowTransformStrategy
from src.transformers.transformation_service import TransformationService
from src.transformers.type_a_transformer import TypeARowStrategy, TypeATransformer
from src.transformers.type_n_transformer import TypeNRowStrategy, TypeNTransformer
from src.transformers.validating_decorator import TransformationError, ValidatingStrategyDecorator

__all__ = [
    "RowTransformStrategy",
    "TransformationService",
    "TransformationError",
    "ValidatingStrategyDecorator",
    "TypeARowStrategy",
    "TypeATransformer",
    "TypeNRowStrategy",
    "TypeNTransformer",
]
