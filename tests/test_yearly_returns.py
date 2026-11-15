"""Tests for the calendar-year return maths in invit-analysis-2026/data/yearly_returns.py.

The inputs are small hand-made payloads in the shape Yahoo's chart API returns. They are
dense daily series, because the module drops everything before a gap of more than 30
days; a sparse fixture would trigger that rule by accident.
"""

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "invit-analysis-2026" / "data"))

import yearly_returns  # noqa: E402

IST = yearly_returns.IST


def ts(d, hour=12):
    """Unix timestamp for the given date at noon IST, inside the trading day."""
    return int(dt.datetime(d.year, d.month, d.day, hour, tzinfo=IST).timestamp())


def day(y, m, d):
    return dt.date(y, m, d)


def dense(start, end, close_fn, volume_fn=lambda d: 10):
    """One row per calendar day from start to end (inclusive): (date, close, volume)."""
    out, d = [], start
    while d <= end:
        out.append((d, close_fn(d), volume_fn(d)))
        d += dt.timedelta(days=1)
    return out


def payload(rows, dividends=()):
    """rows: (date, close, volume). dividends: (date, amount)."""
    result = {
        "timestamp": [ts(d) for d, _, _ in rows],
        "indicators": {"quote": [{
            "close": [c for _, c, _ in rows],
            "volume": [v for _, _, v in rows],
        }]},
    }
    if dividends:
        result["events"] = {"dividends": {str(ts(d)): {"amount": a} for d, a in dividends}}
    return result


def steps(*breaks):
    """Close as a function of date: each (last_date, value) applies up to and including last_date."""
    def close(d):
        for last, value in breaks:
            if d <= last:
                return value
        return breaks[-1][1]
    return close


class YearlyReturnsTest(unittest.TestCase):
    def test_price_and_distribution_yield_against_prior_year_end(self):
        close = steps(
            (day(2023, 12, 31), 100.0),
            (day(2024, 12, 30), 105.0),
            (day(2024, 12, 31), 120.0),   # 2024 year-end
            (day(2025, 12, 30), 120.0),
            (day(2025, 12, 31), 90.0),    # 2025 year-end
        )
        rows = dense(day(2023, 12, 1), day(2025, 12, 31), close)
        dividends = [(day(2024, 3, 1), 5.0), (day(2025, 2, 1), 9.0)]
        by_year = {r["year"]: r for r in yearly_returns.yearly(payload(rows, dividends))}

        self.assertFalse(by_year[2024]["partial"])
        self.assertAlmostEqual(by_year[2024]["price_pct"], 20.0)     # 120 / 100 - 1
        self.assertAlmostEqual(by_year[2024]["dist_pct"], 5.0)       # 5 / 100
        self.assertAlmostEqual(by_year[2024]["total_pct"], 25.0)     # simple sum, not IRR
        self.assertAlmostEqual(by_year[2025]["price_pct"], -25.0)    # 90 / 120 - 1
        self.assertAlmostEqual(by_year[2025]["dist_pct"], 7.5)       # 9 / 120

    def test_zero_volume_close_does_not_become_year_end(self):
        # The last calendar day carries a stale price on zero volume; it must be ignored.
        rows = dense(
            day(2023, 12, 1), day(2024, 12, 31),
            close_fn=lambda d: 500.0 if d == day(2024, 12, 31) else (100.0 if d.year == 2023 else 110.0),
            volume_fn=lambda d: 0 if d == day(2024, 12, 31) else 10,
        )
        by_year = {r["year"]: r for r in yearly_returns.yearly(payload(rows))}
        self.assertEqual(by_year[2024]["end"], 110.0)
        self.assertAlmostEqual(by_year[2024]["price_pct"], 10.0)     # 110 / 100 - 1

    def test_series_starts_after_the_last_long_gap(self):
        # Two early closes, then a gap of more than 30 days, then a dense series from March 2020.
        early = [(day(2019, 1, 2), 40.0, 10), (day(2019, 1, 3), 41.0, 10)]
        late = dense(day(2020, 3, 2), day(2020, 12, 31),
                     steps((day(2020, 12, 30), 60.0), (day(2020, 12, 31), 66.0)))
        rows = yearly_returns.yearly(payload(early + late))
        self.assertEqual([r["year"] for r in rows], [2020])
        self.assertTrue(rows[0]["partial"])
        self.assertEqual(rows[0]["base_date"], "2020-03-02")
        self.assertAlmostEqual(rows[0]["price_pct"], 10.0)           # 66 / 60 - 1

    def test_distributions_paid_before_the_first_close_are_excluded(self):
        rows = dense(day(2020, 3, 2), day(2020, 12, 31), lambda d: 60.0)
        dividends = [(day(2020, 2, 1), 99.0), (day(2020, 9, 1), 3.0)]
        by_year = yearly_returns.yearly(payload(rows, dividends))
        self.assertAlmostEqual(by_year[0]["distributions"], 3.0)

    def test_years_after_last_year_are_left_out(self):
        rows = dense(day(2024, 12, 1), day(2026, 9, 20), lambda d: 100.0)
        years = [r["year"] for r in yearly_returns.yearly(payload(rows))]
        self.assertEqual(years, [2024, 2025])


if __name__ == "__main__":
    unittest.main()
