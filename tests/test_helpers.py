"""
Unit tests for src/transformers/helpers.py
"""

from __future__ import annotations

import pytest

from src.transformers.helpers import (
    compute_overtime_buckets,
    date_to_hebrew_day,
    fix_date_month,
    infer_true_month_year,
    minutes_to_time,
    shift_time,
    time_to_minutes,
)


# ─── time_to_minutes ──────────────────────────────────────────────────────────

class TestTimeToMinutes:
    def test_basic(self):
        assert time_to_minutes("08:00") == 480

    def test_with_dot_separator(self):
        assert time_to_minutes("09.30") == 570

    def test_zero(self):
        assert time_to_minutes("00:00") == 0

    def test_midnight_end(self):
        assert time_to_minutes("23:59") == 1439

    def test_empty_returns_zero(self):
        assert time_to_minutes("") == 0


# ─── minutes_to_time ──────────────────────────────────────────────────────────

class TestMinutesToTime:
    def test_basic(self):
        assert minutes_to_time(480) == "08:00"

    def test_odd_minutes(self):
        assert minutes_to_time(570) == "09:30"

    def test_negative_clamps_to_zero(self):
        assert minutes_to_time(-10) == "00:00"

    def test_roundtrip(self):
        for t in ("06:00", "13:45", "22:30"):
            assert minutes_to_time(time_to_minutes(t)) == t


# ─── shift_time ───────────────────────────────────────────────────────────────

class TestShiftTime:
    """The result must always stay within [clamp_low, clamp_high]."""

    def test_stays_within_clamp(self):
        import random
        rng = random.Random(0)
        for _ in range(200):
            result = shift_time("08:00", rng,
                                min_shift=-60, max_shift=60,
                                clamp_low=360, clamp_high=1320)
            m = time_to_minutes(result)
            assert 360 <= m <= 1320

    def test_passthrough_on_empty(self):
        import random
        rng = random.Random(0)
        assert shift_time("", rng) == ""

    def test_zero_time_passthrough(self):
        """time_to_minutes('00:00') == 0 → treated as missing → unchanged."""
        import random
        rng = random.Random(0)
        assert shift_time("00:00", rng) == "00:00"


# ─── compute_overtime_buckets ─────────────────────────────────────────────────

class TestComputeOvertimeBuckets:
    def test_regular_only(self):
        assert compute_overtime_buckets(7.0) == (7.0, 0.0, 0.0)

    def test_exactly_8h(self):
        assert compute_overtime_buckets(8.0) == (8.0, 0.0, 0.0)

    def test_partial_125(self):
        h100, h125, h150 = compute_overtime_buckets(9.0)
        assert h100 == 8.0
        assert h125 == 1.0
        assert h150 == 0.0

    def test_exactly_10h(self):
        h100, h125, h150 = compute_overtime_buckets(10.0)
        assert h100 == 8.0
        assert h125 == 2.0
        assert h150 == 0.0

    def test_above_10h(self):
        h100, h125, h150 = compute_overtime_buckets(11.5)
        assert h100 == 8.0
        assert h125 == 2.0
        assert h150 == 1.5

    def test_zero(self):
        assert compute_overtime_buckets(0.0) == (0.0, 0.0, 0.0)

    def test_buckets_sum_to_total(self):
        for t in (6.0, 8.0, 9.5, 10.0, 12.25):
            h100, h125, h150 = compute_overtime_buckets(t)
            assert round(h100 + h125 + h150, 6) == pytest.approx(t)


# ─── infer_true_month_year ────────────────────────────────────────────────────

class TestInferTrueMonthYear:
    def test_all_same(self):
        dates = ["01/01/2023", "02/01/2023", "03/01/2023"]
        assert infer_true_month_year(dates) == (1, 2023)

    def test_one_outlier(self):
        """18 rows say month=1; 2 rows have OCR error month=11 → modal is (1, 2023)."""
        dates = [f"{d:02d}/01/2023" for d in range(1, 19)]
        dates += ["01/11/2023", "02/11/2023"]
        assert infer_true_month_year(dates) == (1, 2023)

    def test_two_digit_year_normalised(self):
        dates = ["10/05/23", "11/05/23", "12/05/23"]
        assert infer_true_month_year(dates) == (5, 2023)

    def test_empty_returns_none(self):
        assert infer_true_month_year([]) is None

    def test_unparseable_returns_none(self):
        assert infer_true_month_year(["garbage", "more-garbage"]) is None

    def test_mixed_valid_invalid(self):
        dates = ["01/03/2023", "bad", "02/03/2023"]
        assert infer_true_month_year(dates) == (3, 2023)


# ─── fix_date_month ───────────────────────────────────────────────────────────

class TestFixDateMonth:
    def test_corrects_ocr_error(self):
        """OCR reads 18/11/23 but true month is January 2023."""
        assert fix_date_month("18/11/23", true_month=1, true_year=2023) == "18/01/2023"

    def test_leaves_valid_date_unchanged(self):
        result = fix_date_month("15/03/2023", true_month=3, true_year=2023)
        assert result == "15/03/2023"

    def test_invalid_day_returns_original(self):
        """31/02 doesn't exist – return original string unchanged."""
        original = "31/02/2023"
        assert fix_date_month(original, true_month=2, true_year=2023) == original

    def test_output_is_zero_padded(self):
        result = fix_date_month("5/1/23", true_month=1, true_year=2023)
        assert result == "05/01/2023"

    def test_bad_input_returns_original(self):
        assert fix_date_month("not-a-date", 1, 2023) == "not-a-date"


# ─── date_to_hebrew_day ───────────────────────────────────────────────────────

class TestDateToHebrewDay:
    # 2023-01-02 is a Monday  → "שני"
    def test_monday(self):
        assert date_to_hebrew_day("02/01/2023") == "שני"

    # 2023-01-06 is a Friday  → "שישי"
    def test_friday(self):
        assert date_to_hebrew_day("06/01/2023") == "שישי"

    def test_two_digit_year(self):
        assert date_to_hebrew_day("02/01/23") == "שני"

    def test_empty_returns_empty(self):
        assert date_to_hebrew_day("") == ""

    def test_invalid_returns_empty(self):
        assert date_to_hebrew_day("garbage") == ""
