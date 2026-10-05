"""차트 눈금 검증. 실행: python -m unittest discover tests"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.chart import _nice_ticks, company_chart  # noqa: E402


class TicksTest(unittest.TestCase):
    def test_ticks_cover_the_whole_range(self):
        for lo, hi in [(59100, 85000), (26900, 42000), (96000, 120000), (3400, 3815), (1, 1.5)]:
            ticks = _nice_ticks(lo, hi)
            self.assertLessEqual(ticks[0], lo, (lo, hi))
            self.assertGreaterEqual(ticks[-1], hi, (lo, hi))
            self.assertLessEqual(len(ticks), 8, (lo, hi))

    def test_flat_range_does_not_fail(self):
        self.assertGreaterEqual(len(_nice_ticks(100, 100)), 2)


class ChartTest(unittest.TestCase):
    def test_draws_all_layers(self):
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(30)]
        price = [(d, 100 + i) for i, d in enumerate(days)]
        bench = [(d, 50 + i * 0.2) for i, d in enumerate(days)]
        svg = company_chart(price, bench, [(days[0], 140), (days[10], 150)], [(days[0], "개시"), (days[10], "TP 150")])
        self.assertTrue(svg.startswith("<svg"))
        self.assertEqual(svg.count("<polyline"), 3)   # 목표주가, 벤치마크, 주가
        self.assertEqual(svg.count("<rect"), 2)       # 의견 변경 표시 두 개

    def test_too_short_series_returns_empty(self):
        self.assertEqual(company_chart([(date(2026, 1, 1), 100)]), "")


if __name__ == "__main__":
    unittest.main()
