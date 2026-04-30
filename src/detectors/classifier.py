"""
Classifier – determine report type from raw OCR text using keyword scoring.

Returns exactly ``"TYPE_A"`` or ``"TYPE_B"``.

Scoring logic
-------------
Each registered type accumulates score points when its keywords appear in the
text.  The type with the highest score wins.  Ties default to ``"TYPE_B"``.

Adding a third report type requires only a new entry in ``_KEYWORD_SCORES`` –
no other code changes are needed.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Each entry: (report_type_string, list_of_(keyword, score_points))
# Keywords are matched case-insensitively anywhere in the text.
_KEYWORD_SCORES: list[tuple[str, list[tuple[str, int]]]] = [
    (
        "TYPE_A",
        [
            ("100%",       5),
            ("125%",       5),
            ("150%",       5),
            ("שעות נוספות", 4),   # overtime hours (Hebrew)
            ("הפסקה",      3),   # break (Hebrew)
            ("מקום עבודה", 3),   # workplace (Hebrew)
            ("שעות רגילות", 3),  # regular hours (Hebrew)
        ],
    ),
    (
        "TYPE_B",
        [
            ("מחיר לשעה",   5),  # hourly rate (Hebrew)
            ("לתשלום",      4),  # for payment (Hebrew)
            ("שכר",         3),  # salary (Hebrew)
            ("תשלום",       3),  # payment (Hebrew)
            ("חברה",        2),  # company (Hebrew)
        ],
    ),
]

_DEFAULT_TYPE = "TYPE_B"


def classify(raw_text: str) -> str:
    """Score raw OCR text and return the most likely report type.

    Args:
        raw_text: Plain-text output from ``ocr.extract_text()``.

    Returns:
        ``"TYPE_A"`` or ``"TYPE_B"``.
    """
    scores: dict[str, int] = {}
    text_lower = raw_text.lower()

    for report_type, keywords in _KEYWORD_SCORES:
        total = 0
        for keyword, points in keywords:
            if keyword.lower() in text_lower:
                total += points
                logger.debug(f"  [{report_type}] +{points} for '{keyword}'")
        scores[report_type] = total
        logger.debug(f"  [{report_type}] total score = {total}")

    best = max(scores, key=lambda k: scores[k]) if scores else _DEFAULT_TYPE

    # Tie-break: if all scores are equal, use default
    max_score = max(scores.values()) if scores else 0
    if list(scores.values()).count(max_score) > 1:
        logger.info(f"Classify: tie at score {max_score}, defaulting to '{_DEFAULT_TYPE}'")
        return _DEFAULT_TYPE

    logger.info(f"Classify: '{best}' (scores={scores})")
    return best
