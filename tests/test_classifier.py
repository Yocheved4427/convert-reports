"""
Unit tests for src/detectors/classifier.py

Covers:
  - Type-A keyword scoring
  - Type-B keyword scoring
  - Tie-breaking defaults to TYPE_B
  - Empty / whitespace text defaults to TYPE_B
  - Case-insensitivity
  - Mixed text with both keyword sets
"""

from __future__ import annotations

import pytest

from src.detectors.classifier import classify


class TestClassifyTypeA:
    """Texts that should be classified as TYPE_A."""

    def test_all_type_a_keywords(self) -> None:
        text = "100% 125% 150% שעות נוספות הפסקה מקום עבודה שעות רגילות"
        assert classify(text) == "TYPE_A"

    def test_single_strong_type_a_keyword(self) -> None:
        # "100%" alone scores 5 – enough to beat an empty TYPE_B score
        assert classify("100%") == "TYPE_A"

    def test_overtime_keyword_hebrew(self) -> None:
        assert classify("שעות נוספות") == "TYPE_A"

    def test_type_a_dominant_in_mixed_text(self) -> None:
        # Many TYPE_A keywords outvote the few TYPE_B ones
        text = "100% 125% 150% שעות נוספות הפסקה מקום עבודה שכר"
        assert classify(text) == "TYPE_A"

    def test_case_insensitive(self) -> None:
        # Keywords should match regardless of case
        assert classify("100% שעות נוספות") == "TYPE_A"


class TestClassifyTypeB:
    """Texts that should be classified as TYPE_B."""

    def test_all_type_b_keywords(self) -> None:
        text = "מחיר לשעה לתשלום שכר תשלום חברה"
        assert classify(text) == "TYPE_B"

    def test_single_strong_type_b_keyword(self) -> None:
        assert classify("מחיר לשעה") == "TYPE_B"

    def test_payment_keyword(self) -> None:
        assert classify("לתשלום") == "TYPE_B"


class TestClassifyEdgeCases:
    """Edge cases and tie-breaking behaviour."""

    def test_empty_text_defaults_to_type_b(self) -> None:
        assert classify("") == "TYPE_B"

    def test_whitespace_only_defaults_to_type_b(self) -> None:
        assert classify("   \n\t  ") == "TYPE_B"

    def test_no_matching_keywords_defaults_to_type_b(self) -> None:
        assert classify("Lorem ipsum dolor sit amet") == "TYPE_B"

    def test_tie_defaults_to_type_b(self) -> None:
        # Craft a text that gives both types an identical score
        # TYPE_A: "100%" = 5;  TYPE_B: "מחיר לשעה" = 5  →  tie → TYPE_B
        assert classify("100% מחיר לשעה") == "TYPE_B"

    def test_returns_string_not_enum(self) -> None:
        result = classify("100% 125%")
        assert isinstance(result, str)
        assert result in ("TYPE_A", "TYPE_B")
