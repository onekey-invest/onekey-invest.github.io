"""계산 검증. 실행: python -m unittest discover tests"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import metrics as M  # noqa: E402


def series(pairs):
    return M.Series(tuple(d for d, _ in pairs), tuple(c for _, c in pairs))


S = series([
    (date(2026, 1, 2), 100.0),
    (date(2026, 1, 5), 110.0),   # 1월 3~4일은 주말
    (date(2026, 1, 6), 99.0),
])


class SeriesTest(unittest.TestCase):
    def test_exact_day(self):
        self.assertEqual(S.close_at(date(2026, 1, 5)), 110.0)

    def test_holiday_uses_previous_trading_day(self):
        self.assertEqual(S.at(date(2026, 1, 4)), (date(2026, 1, 2), 100.0))

    def test_before_first_day_is_none(self):
        self.assertIsNone(S.close_at(date(2026, 1, 1)))

    def test_after_last_day_uses_last(self):
        self.assertEqual(S.close_at(date(2026, 2, 1)), 99.0)

    def test_rejects_unsorted(self):
        with self.assertRaises(ValueError):
            series([(date(2026, 1, 5), 1.0), (date(2026, 1, 2), 1.0)])

    def test_rejects_duplicates(self):
        with self.assertRaises(ValueError):
            series([(date(2026, 1, 2), 1.0), (date(2026, 1, 2), 2.0)])


class ReturnTest(unittest.TestCase):
    def test_simple_return(self):
        self.assertAlmostEqual(M.simple_return(59100, 70000), 0.18443, places=5)

    def test_missing_or_zero_start(self):
        self.assertIsNone(M.simple_return(None, 100))
        self.assertIsNone(M.simple_return(0, 100))
        self.assertIsNone(M.simple_return(100, None))

    def test_period_return(self):
        self.assertAlmostEqual(M.period_return(S, date(2026, 1, 2), date(2026, 1, 6)), -0.01)

    def test_period_return_without_start_data(self):
        self.assertIsNone(M.period_return(S, date(2025, 12, 1), date(2026, 1, 6)))

    def test_upside(self):
        self.assertAlmostEqual(M.upside(85000, 70000), 0.21429, places=5)

    def test_excess(self):
        self.assertAlmostEqual(M.excess(0.184, 0.122), 0.062)
        self.assertIsNone(M.excess(None, 0.1))

    def test_mean_skips_missing(self):
        self.assertAlmostEqual(M.mean([0.1, None, 0.3]), 0.2)
        self.assertIsNone(M.mean([None]))


class MonthsBeforeTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(M.months_before(date(2026, 10, 1), 3), date(2026, 7, 1))

    def test_crosses_year(self):
        self.assertEqual(M.months_before(date(2026, 2, 15), 6), date(2025, 8, 15))

    def test_clamps_to_month_end(self):
        self.assertEqual(M.months_before(date(2026, 3, 31), 1), date(2026, 2, 28))


if __name__ == "__main__":
    unittest.main()
