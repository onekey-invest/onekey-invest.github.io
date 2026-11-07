"""의견 장부의 괴리율·변경 구분과, 마켓노트의 기업 이름 링크를 검증한다."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build  # noqa: E402
from lib import metrics as M  # noqa: E402


def S(pairs):
    return M.Series(tuple(d for d, _ in pairs), tuple(c for _, c in pairs))


class LedgerTest(unittest.TestCase):
    def test_gap_and_change(self):
        px = S([(date(2026, 10, 1), 100.0), (date(2026, 10, 2), 110.0), (date(2026, 10, 5), 90.0), (date(2026, 10, 6), 80.0)])
        kospi = S([(date(2026, 10, 1), 1000.0), (date(2026, 10, 6), 1100.0)])
        states = [{"date": date(2026, 10, 1), "rating": "중립", "target": 100, "report_id": "a"},
                  {"date": date(2026, 10, 5), "rating": "매도", "target": 70, "report_id": "b"}]
        rows = build.ledger_view(states, px, kospi, date(2026, 10, 6))
        self.assertEqual([r["change"] for r in rows], ["개시", "의견 변경"])
        # 첫 의견은 10/1~10/2 (다음 의견 날의 종가는 빼고): 평균 105 → +5%, 최고 110 → +10%
        self.assertAlmostEqual(rows[0]["gap_avg"], 0.05)
        self.assertAlmostEqual(rows[0]["gap_ext"], 0.10)
        # 매도 의견은 최저가 기준: 80 / 70 − 1
        self.assertAlmostEqual(rows[1]["gap_ext"], 80 / 70 - 1)
        self.assertEqual(rows[1]["ext_label"], "최저")
        self.assertTrue(rows[1]["live"])
        self.assertAlmostEqual(rows[0]["after"], -0.2)

    def test_target_down(self):
        px = S([(date(2026, 10, 1), 100.0), (date(2026, 10, 2), 100.0)])
        states = [{"date": date(2026, 10, 1), "rating": "중립", "target": 100, "report_id": "a"},
                  {"date": date(2026, 10, 2), "rating": "중립", "target": 90, "report_id": "a"}]
        rows = build.ledger_view(states, px, px, date(2026, 10, 2))
        self.assertEqual(rows[1]["change"], "목표주가 하향")


class LinkTest(unittest.TestCase):
    def test_link_first_outside_tags_and_links(self):
        html = '<p><a href="x">기아</a> 기아가 올랐다. 기아</p>'
        out, done = build.link_first(html, "기아", "/companies/kia/")
        self.assertTrue(done)
        self.assertEqual(str(out).count('href="/companies/kia/"'), 1)
        self.assertIn('<a href="x">기아</a> <a class="lnk" href="/companies/kia/">기아</a>가', str(out))

    def test_no_match(self):
        out, done = build.link_first("<p>없음</p>", "기아", "/k/")
        self.assertFalse(done)


if __name__ == "__main__":
    unittest.main()
