"""
Parser for Type-B reports (simple monthly attendance with pay summary).

Alias of TypeNParser; delegates all logic to the shared implementation.
"""

from __future__ import annotations

# TypeBParser is functionally identical to TypeNParser.
# Import the updated class and expose it under the canonical TYPE_B name.
from src.parsers.type_n_parser import TypeNParser as TypeBParser

__all__ = ["TypeBParser"]
