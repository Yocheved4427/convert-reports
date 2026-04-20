"""
Shared transformation helpers used by both type-specific transformers.
"""

from __future__ import annotations

import random
from datetime import datetime


_HEBREW_DAYS = {
    0: "שני",       # Monday
    1: "שלישי",     # Tuesday
    2: "רביעי",     # Wednesday
    3: "חמישי",     # Thursday
    4: "שישי",      # Friday
    5: "שבת",       # Saturday
    6: "ראשון",     # Sunday
}


def date_to_hebrew_day(date_str: str) -> str:
    """
    Given a date string in dd/mm/yyyy, dd/mm/yy, d/m/yy or d/m/yyyy format,
    return the Hebrew name of the day of week.
    Returns empty string if the date cannot be parsed.
    """
    if not date_str:
        return ""
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%-d/%-m/%Y", "%-d/%-m/%y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return _HEBREW_DAYS[dt.weekday()]
        except ValueError:
            continue
    # Try splitting manually to handle single-digit day/month
    parts = date_str.strip().split("/")
    if len(parts) == 3:
        try:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 100:
                year += 2000
            if 1 <= day <= 31 and 1 <= month <= 12:
                dt = datetime(year, month, day)
                return _HEBREW_DAYS[dt.weekday()]
        except (ValueError, OverflowError):
            pass
    return ""


def time_to_minutes(t: str) -> int:
    """Convert 'HH:MM' to total minutes since midnight."""
    if not t:
        return 0
    parts = t.replace(".", ":").split(":")
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(m: int) -> str:
    """Convert minutes since midnight to 'HH:MM'."""
    m = max(0, m)
    return f"{m // 60:02d}:{m % 60:02d}"


def shift_time(time_str: str, rng: random.Random,
               min_shift: int = -30, max_shift: int = 30,
               clamp_low: int = 360, clamp_high: int = 1320) -> str:
    """
    Shift a time string by a random amount of minutes.

    Args:
        time_str:   'HH:MM'
        rng:        seeded Random instance
        min_shift:  min delta in minutes (can be negative)
        max_shift:  max delta in minutes
        clamp_low:  earliest allowed time in minutes (default 06:00)
        clamp_high: latest allowed time in minutes (default 22:00)

    Returns:
        Shifted time as 'HH:MM'.
    """
    mins = time_to_minutes(time_str)
    if mins == 0:
        return time_str
    delta = rng.randint(min_shift, max_shift)
    mins = max(clamp_low, min(clamp_high, mins + delta))
    return minutes_to_time(mins)


def compute_overtime_buckets(total_hours: float) -> tuple[float, float, float]:
    """
    Split total working hours into Israeli-law overtime buckets:
      ≤ 8.0 h  → 100%
      8.0–10.0 → 125%
      > 10.0   → 150%

    Returns (hours_100, hours_125, hours_150).
    """
    if total_hours <= 0:
        return (0.0, 0.0, 0.0)
    h100 = min(total_hours, 8.0)
    remainder = total_hours - h100
    h125 = min(remainder, 2.0) if remainder > 0 else 0.0
    h150 = max(0.0, total_hours - 10.0)
    return (round(h100, 2), round(h125, 2), round(h150, 2))


# ── OCR Date Correction ────────────────────────────────────────────────────────

def infer_true_month_year(dates: list[str]) -> tuple[int, int] | None:
    """
    Determine the *true* (month, year) for a report by voting.

    The OCR occasionally mis-reads a digit (e.g. January → November).
    Taking the **mode** over all parsed row-dates gives the correct answer
    in all realistic cases (one or two bad rows out of ~20).

    Args:
        dates: list of date strings in d/m/yy, d/m/yyyy, dd/mm/yy, dd/mm/yyyy.

    Returns:
        ``(month, year)`` tuple where year is always 4-digit, or ``None`` if
        the list is empty / unparseable.
    """
    from collections import Counter

    counts: Counter[tuple[int, int]] = Counter()
    for d in dates:
        parts = d.strip().split("/")
        if len(parts) != 3:
            continue
        try:
            month = int(parts[1])
            year = int(parts[2])
            if year < 100:
                year += 2000
            if 1 <= month <= 12 and 2000 <= year <= 2100:
                counts[(month, year)] += 1
        except ValueError:
            continue

    if not counts:
        return None
    return counts.most_common(1)[0][0]


def fix_date_month(date_str: str, true_month: int, true_year: int) -> str:
    """
    Return *date_str* with its month and year replaced by *true_month* /
    *true_year*, preserving the original day number.

    If the resulting date would be invalid (e.g. 31 February), the original
    string is returned unchanged.

    Args:
        date_str:   Original date string – any of d/m/yy, dd/mm/yy, …
        true_month: Correct month (1-12).
        true_year:  Correct year (4-digit).

    Returns:
        Corrected date string in dd/mm/yyyy format, or the original on error.
    """
    parts = date_str.strip().split("/")
    if len(parts) != 3:
        return date_str
    try:
        day = int(parts[0])
        if not (1 <= day <= 31):
            return date_str
        # Validate that this day actually exists in the target month/year
        from datetime import datetime
        dt = datetime(true_year, true_month, day)
        return f"{dt.day:02d}/{dt.month:02d}/{dt.year}"
    except (ValueError, OverflowError):
        return date_str
