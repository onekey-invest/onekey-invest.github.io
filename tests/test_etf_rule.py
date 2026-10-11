"""가상운용 ETF 전략의 매매 규칙 검증. 실행: python -m unittest discover tests"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import etf_rule as R  # noqa: E402
from lib import portfolio as P  # noqa: E402
from tools import update_base_rate as U  # noqa: E402
from tools import update_intraday as I  # noqa: E402

RATES = [(date(2025, 5, 29), 2.50), (date(2026, 7, 16), 2.75), (date(2026, 8, 27), 3.00)]


def weekdays(a, b):
    d, out = a, []
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class RateTest(unittest.TestCase):
    def test_month_shift(self):
        self.assertEqual(R.shift_month_end(date(2026, 9, 30), -6), date(2026, 3, 31))
        self.assertEqual(R.shift_month_end(date(2027, 2, 26), -6), date(2026, 8, 31))

    def test_rising_and_off_again(self):
        self.assertFalse(R.rate_rising(RATES, date(2026, 6, 30)))
        self.assertTrue(R.rate_rising(RATES, date(2026, 7, 31)))     # 2.75 대 1월 말 2.50
        self.assertTrue(R.rate_rising(RATES, date(2027, 1, 29)))     # 3.00 대 7월 말 2.75
        self.assertFalse(R.rate_rising(RATES, date(2027, 2, 26)))    # 3.00 대 8월 말 3.00

    def test_parse_bok_table(self):
        html = '<tr> <td class="fb">2026</td> <td>08월 27일</td> <td>3.00</td> </tr><tr> <td class="fb">2026</td> <td>07월 16일</td> <td>2.75</td> </tr>'
        self.assertEqual(U.parse(html), [(date(2026, 7, 16), 2.75), (date(2026, 8, 27), 3.0)])


class IntradayTest(unittest.TestCase):
    def test_parse_naver(self):
        payload = {"datas": [{"itemCode": "069500", "closePrice": "105,650", "localTradedAt": "2026-10-12T10:05:00+09:00", "marketStatus": "OPEN"}]}
        self.assertEqual(I.parse(payload), {"069500": (105650.0, "2026-10-12T10:05:00+09:00", "OPEN")})


class TradeTest(unittest.TestCase):
    def setUp(self):
        self.days = weekdays(date(2026, 9, 1), date(2027, 3, 5))
        flat = {d: 100.0 for d in self.days}
        self.prices = {"KR": dict(flat), "US": dict(flat), "GOLD": dict(flat)}
        self.cfg = {"started": date(2026, 10, 12), "initial": 1_000_000, "commission": 0.001,
                    "auto": {"weights": {"KR": 1 / 3, "US": 1 / 3, "GOLD": 1 / 3}, "kr_asset": "KR", "band": 0.05, "rate_months": 6}}

    def run_all(self, prices=None):
        trades, state = [], {"last_decision": None, "rising": None}
        new, state = R.new_trades(self.cfg, prices or self.prices, self.days, RATES, trades, state)
        return new, state

    def test_first_buy_skips_korea_when_rate_rising(self):
        new, state = self.run_all()
        first = [t for t in new if t.date == date(2026, 10, 12)]
        self.assertEqual({t.asset for t in first}, {"US", "GOLD"})
        self.assertTrue(all(t.side == P.BUY and t.qty == 3330 for t in first))

    def test_korea_bought_when_condition_turns_off(self):
        new, state = self.run_all()
        back = [t for t in new if t.asset == "KR"]
        self.assertEqual([(t.date, t.side) for t in back], [(date(2027, 3, 1), P.BUY)])   # 2월 말 판정, 3월 첫 거래일
        self.assertFalse(state["rising"])

    def test_no_trade_inside_band_and_idempotent(self):
        new, state = self.run_all()
        self.assertEqual(len([t for t in new if date(2026, 10, 13) <= t.date <= date(2027, 2, 26)]), 0)
        again, state2 = R.new_trades(self.cfg, self.prices, self.days, RATES, new, state)
        self.assertEqual(again, [])
        self.assertEqual(state2, state)

    def test_band_breach_rebalances_and_cash_never_negative(self):
        prices = {a: dict(v) for a, v in self.prices.items()}
        for d in self.days:
            if d >= date(2026, 11, 16):
                prices["GOLD"][d] = 160.0                      # 금이 60% 올라 비중이 5%p 넘게 벗어난다
        new, _ = self.run_all(prices)
        dec = [t for t in new if t.date == date(2026, 12, 1)]
        self.assertTrue(any(t.asset == "GOLD" and t.side == P.SELL for t in dec))
        cal = [d for d in self.days if d >= self.cfg["started"]]
        series = {a: __import__("lib.metrics", fromlist=["Series"]).Series(tuple(sorted(v)), tuple(v[k] for k in sorted(v))) for a, v in prices.items()}
        P.run(self.cfg["initial"], new, series, cal, self.cfg["commission"], 0.0)      # 현금이 모자라면 여기서 오류


if __name__ == "__main__":
    unittest.main()
