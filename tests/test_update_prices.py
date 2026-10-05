"""시세 정리 검증(인터넷 없이). 실행: python -m unittest discover tests"""
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import update_prices as U  # noqa: E402

KST = timezone(timedelta(hours=9))


class CleanTest(unittest.TestCase):
    def test_sorts_and_drops_bad_values(self):
        rows = [
            (date(2026, 1, 6), 110.0),
            (date(2026, 1, 5), 100.0),
            (date(2026, 1, 7), 0.0),            # 거래정지일의 0
            (date(2026, 1, 8), float("nan")),
            (date(2026, 1, 9), None),
        ]
        self.assertEqual(U.clean(rows, date(2026, 1, 31)), [(date(2026, 1, 5), 100.0), (date(2026, 1, 6), 110.0)])

    def test_drops_days_after_until(self):
        rows = [(date(2026, 1, 5), 100.0), (date(2026, 1, 6), 110.0)]
        self.assertEqual(U.clean(rows, date(2026, 1, 5)), [(date(2026, 1, 5), 100.0)])

    def test_same_day_keeps_last(self):
        rows = [(date(2026, 1, 5), 100.0), (date(2026, 1, 5), 101.0)]
        self.assertEqual(U.clean(rows, date(2026, 1, 5)), [(date(2026, 1, 5), 101.0)])


class UntilTest(unittest.TestCase):
    def test_before_close_uses_yesterday(self):
        self.assertEqual(U.default_until(datetime(2026, 10, 2, 11, 0, tzinfo=KST)), date(2026, 10, 1))

    def test_after_close_uses_today(self):
        self.assertEqual(U.default_until(datetime(2026, 10, 2, 18, 30, tzinfo=KST)), date(2026, 10, 2))


if __name__ == "__main__":
    unittest.main()
