"""
Location Registry – canonical workplace (מקום עבודה) identification.

Problem
-------
OCR extracts Hebrew location names from the "מקום עבודה" column, but the
same workplace can appear as several surface forms across rows or reports:

    "גליליון", "גלילאון", "גלילון ", "גלילי"  →  all the same site

This module:
  1.  Cleans raw OCR text (strips noise characters, normalises whitespace,
      removes quotation marks common in Hebrew abbreviations).
  2.  Resolves the cleaned string against a known-alias table.
  3.  Returns a stable ``LocationRecord`` containing a machine-readable
      ``location_id`` (ASCII slug) and a human-readable ``display_name``
      (canonical Hebrew).

Usage in the transformer
------------------------
>>> reg = LocationRegistry()
>>> rec = reg.resolve("גלילאון ")
>>> rec.location_id          # "galilyon"
>>> rec.display_name         # "גליליון"
>>> rec.is_known             # True

>>> rec2 = reg.resolve("משרד ראשי")
>>> rec2.location_id         # "unknown_משרד_ראשי"  (not in alias table)
>>> rec2.is_known             # False
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LocationRecord:
    """Immutable result of resolving a raw OCR location string."""

    location_id: str    # Stable ASCII slug used as an identifier
    display_name: str   # Canonical Hebrew display name
    raw: str            # Original OCR text before any cleaning
    is_known: bool      # True  → matched a known entry in the alias table
                        # False → cleaned but not in the alias table


# ---------------------------------------------------------------------------
# Alias table
# ---------------------------------------------------------------------------
# Maps every known OCR surface form (after cleaning) → (location_id, display_name).
# Add new rows here to teach the registry about additional workplaces.

_ALIAS_TABLE: dict[str, tuple[str, str]] = {
    # ── גליליון ────────────────────────────────────────────────────────────
    "גליליון":   ("galilyon",   "גליליון"),
    "גלילאון":   ("galilyon",   "גליליון"),
    "גלילון":    ("galilyon",   "גליליון"),
    "גלילי":     ("galilyon",   "גליליון"),
    "גלילין":    ("galilyon",   "גליליון"),
    # ── אשדוד ─────────────────────────────────────────────────────────────
    "אשדוד":     ("ashdod",     "אשדוד"),
    "אשדד":      ("ashdod",     "אשדוד"),
    # ── תל אביב ───────────────────────────────────────────────────────────
    "תל אביב":   ("tel_aviv",   "תל אביב"),
    "ת אביב":    ("tel_aviv",   "תל אביב"),
    "תלאביב":    ("tel_aviv",   "תל אביב"),
    # ── חיפה ──────────────────────────────────────────────────────────────
    "חיפה":      ("haifa",      "חיפה"),
    "חיפא":      ("haifa",      "חיפה"),
    # ── ירושלים ───────────────────────────────────────────────────────────
    "ירושלים":   ("jerusalem",  "ירושלים"),
    "ירושלם":    ("jerusalem",  "ירושלים"),
    # ── באר שבע ───────────────────────────────────────────────────────────
    "באר שבע":   ("beer_sheva", "באר שבע"),
    "בירשבע":    ("beer_sheva", "באר שבע"),
    # ── נתניה ─────────────────────────────────────────────────────────────
    "נתניה":     ("netanya",    "נתניה"),
    "נתניא":     ("netanya",    "נתניה"),
    # ── רמת גן ────────────────────────────────────────────────────────────
    "רמת גן":    ("ramat_gan",  "רמת גן"),
    "רמתגן":     ("ramat_gan",  "רמת גן"),
    # ── Office (English fallback) ─────────────────────────────────────────
    "office":    ("office",     "Office"),
    "offices":   ("office",     "Office"),
}

# Regex for characters that are pure OCR noise when they appear in Hebrew text
_NOISE_RE = re.compile(r'["\'\u05F4\u05F3\u2019\u201C\u201D|@#$%^&*_+=<>]')
# Collapse runs of whitespace
_WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class LocationRegistry:
    """Resolve raw OCR location strings to canonical ``LocationRecord``s.

    The registry is stateless and thread-safe; a single instance can be
    shared across the whole pipeline.  The alias table is module-level so
    it is loaded once.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, raw: str) -> LocationRecord:
        """Clean *raw* and look it up in the alias table.

        Args:
            raw: OCR-extracted location text, possibly noisy.

        Returns:
            A ``LocationRecord`` with a stable ``location_id`` and canonical
            ``display_name``.  ``is_known`` is ``False`` when the text is not
            in the alias table; in that case the cleaned text is used as-is
            and the ``location_id`` is a prefixed slug for traceability.
        """
        cleaned = self._clean(raw)

        # Direct lookup
        if cleaned in _ALIAS_TABLE:
            loc_id, display = _ALIAS_TABLE[cleaned]
            return LocationRecord(
                location_id=loc_id,
                display_name=display,
                raw=raw,
                is_known=True,
            )

        # Case-insensitive fallback
        lower = cleaned.lower()
        for alias, (loc_id, display) in _ALIAS_TABLE.items():
            if alias.lower() == lower:
                return LocationRecord(
                    location_id=loc_id,
                    display_name=display,
                    raw=raw,
                    is_known=True,
                )

        # Unknown location – build a deterministic slug so it can still be
        # tracked downstream.
        slug = "unknown_" + re.sub(r"\s+", "_", cleaned) if cleaned else "unknown"
        return LocationRecord(
            location_id=slug,
            display_name=cleaned or raw,
            raw=raw,
            is_known=False,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean(text: str) -> str:
        """Remove OCR noise and normalise whitespace."""
        # Strip noise punctuation
        text = _NOISE_RE.sub("", text)
        # Normalise Unicode (e.g. decomposed Hebrew forms)
        text = unicodedata.normalize("NFC", text)
        # Collapse whitespace
        text = _WS_RE.sub(" ", text).strip()
        return text


# Module-level singleton – import this in transformer code.
location_registry = LocationRegistry()
