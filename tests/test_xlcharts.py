"""엑셀에 넘기는 그림 자료(build.py의 xl_*)를 확인한다. 그림은 엑셀이 그리므로 여기서는 자료의 꼴만 본다."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build as B  # noqa: E402


class StepTest(unittest.TestCase):
    def test_step_repeats_previous_value_on_change_day(self):
        pts = [(date(2026, 1, 1), 100.0), (date(2026, 2, 1), 100.0), (date(2026, 3, 1), 120.0)]
        self.assertEqual(B.step_points(pts), [(date(2026, 1, 1), 100.0), (date(2026, 2, 1), 100.0), (date(2026, 3, 1), 100.0), (date(2026, 3, 1), 120.0)])


class SpecTest(unittest.TestCase):
    def setUp(self):
        B.XL.clear()

    def test_time_chart_marks_on_main_line(self):
        price = [(date(2026, 1, d), 100.0 + d) for d in range(1, 6)]
        cid = B.xl_time("company-x", "price", [
            {"name": "목표주가", "type": "step", "color": "#0f766e", "dash": True, "points": [(date(2026, 1, 1), 120.0), (date(2026, 1, 5), 130.0)]},
            {"name": "가", "type": "line", "color": "#1f2a44", "main": True, "points": price},
        ], [(date(2026, 1, 3), "TP 130")])
        self.assertEqual(cid, "company-x")
        c = B.XL[-1]
        self.assertEqual(c["asof"], "2026-01-05")
        self.assertEqual([x["type"] for x in c["series"]], ["line", "line", "points"])
        self.assertEqual(c["series"][0]["points"], [["2026-01-01", 120.0], ["2026-01-05", 120.0], ["2026-01-05", 130.0]])
        self.assertEqual(c["series"][2]["points"], [["2026-01-03", 103.0, "TP 130"]])
        self.assertTrue(c["series"][1]["main"])

    def test_short_series_are_dropped(self):
        self.assertIsNone(B.xl_time("x", "pct", [{"name": "가", "type": "line", "color": "#000000", "points": [(date(2026, 1, 1), 1.0)]}]))
        self.assertEqual(B.XL, [])

    def test_pie_rest_slice_is_grey(self):
        B.xl_pie("p", [{"name": "가", "pct": 60.0}, {"name": "그 밖", "pct": 40.0, "rest": True}], "2025년")
        parts = B.XL[-1]["parts"]
        self.assertEqual(parts[0]["color"], B.PIE_COLORS[0])
        self.assertEqual(parts[1]["color"], B.PIE_REST)

    def test_spark_needs_two_points(self):
        self.assertIsNone(B.xl_spark("s", [1.0], "#e0353b", date(2026, 1, 1)))
        self.assertEqual(B.xl_spark("s", [1.0, 2.0], "#e0353b", date(2026, 1, 2)), "s")


if __name__ == "__main__":
    unittest.main()
