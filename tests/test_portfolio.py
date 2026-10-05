"""가상운용 계산 검증. 실행: python -m unittest discover tests"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import metrics as M  # noqa: E402
from lib import portfolio as P  # noqa: E402

D = [date(2026, 1, d) for d in (5, 6, 7, 8, 9)]
PRICES = {
    "A": M.Series(tuple(D), (100.0, 110.0, 105.0, 120.0, 90.0)),
    "B": M.Series(tuple(D), (50.0, 50.0, 55.0, 55.0, 60.0)),
}


class RunTest(unittest.TestCase):
    def test_cash_only(self):
        r = P.run(1000, [], PRICES, D)
        self.assertEqual([v for _, v in r["nav"]], [1000.0] * 5)
        self.assertEqual(r["holdings"], [])

    def test_buy_then_value_follows_close(self):
        r = P.run(1000, [P.Trade(D[0], "A", P.BUY, 5, 100)], PRICES, D)
        # 현금 500 + 5주 × 종가
        self.assertEqual([v for _, v in r["nav"]], [1000, 1050, 1025, 1100, 950])
        h = r["holdings"][0]
        self.assertEqual((h["qty"], h["avg"], h["close"], h["value"]), (5, 100, 90, 450))
        self.assertAlmostEqual(h["pnl"], -0.1)
        self.assertAlmostEqual(h["weight"], 450 / 950)
        self.assertAlmostEqual(r["cash_weight"], 500 / 950)

    def test_costs_reduce_cash(self):
        trades = [P.Trade(D[0], "A", P.BUY, 5, 100), P.Trade(D[3], "A", P.SELL, 5, 120)]
        r = P.run(1000, trades, PRICES, D, commission=0.01, sell_tax=0.02)
        # 매수 수수료 5, 매도 수수료 6 + 세금 12
        self.assertAlmostEqual(r["fees"], 23)
        self.assertAlmostEqual(r["nav"][-1][1], 1000 - 500 - 5 + 600 - 18)
        self.assertEqual(r["holdings"], [])

    def test_partial_sell_keeps_average_cost(self):
        trades = [
            P.Trade(D[0], "A", P.BUY, 4, 100),
            P.Trade(D[1], "A", P.BUY, 4, 110),
            P.Trade(D[2], "A", P.SELL, 2, 105),
        ]
        r = P.run(2000, trades, PRICES, D)
        h = r["holdings"][0]
        self.assertEqual(h["qty"], 6)
        self.assertAlmostEqual(h["avg"], 105)

    def test_rejects_overselling(self):
        with self.assertRaises(ValueError):
            P.run(1000, [P.Trade(D[0], "A", P.SELL, 1, 100)], PRICES, D)

    def test_rejects_overspending(self):
        with self.assertRaises(ValueError):
            P.run(100, [P.Trade(D[0], "A", P.BUY, 5, 100)], PRICES, D)

    def test_rejects_trade_on_non_trading_day(self):
        with self.assertRaises(ValueError):
            P.run(1000, [P.Trade(date(2026, 1, 10), "A", P.BUY, 1, 100)], PRICES, D)

    def test_rejects_unknown_asset(self):
        with self.assertRaises(ValueError):
            P.run(1000, [P.Trade(D[0], "Z", P.BUY, 1, 100)], PRICES, D)


class StatsTest(unittest.TestCase):
    def test_total_return(self):
        self.assertAlmostEqual(P.total_return([(D[0], 1000), (D[1], 1100)], 1000), 0.1)

    def test_max_drawdown(self):
        self.assertAlmostEqual(P.max_drawdown([100, 120, 90, 110, 80, 130]), 80 / 120 - 1)

    def test_max_drawdown_never_down(self):
        self.assertEqual(P.max_drawdown([100, 101, 102]), 0.0)

    def test_sharpe_needs_enough_days(self):
        self.assertIsNone(P.sharpe([100, 101, 102]))

    def test_sharpe_value(self):
        values = [100.0]
        for i in range(40):
            values.append(values[-1] * (1.01 if i % 2 == 0 else 0.995))
        rets = [b / a - 1 for a, b in zip(values, values[1:])]
        mean = sum(rets) / len(rets)
        sd = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5
        self.assertAlmostEqual(P.sharpe(values), mean / sd * 252 ** 0.5)

    def test_sharpe_flat_is_none(self):
        self.assertIsNone(P.sharpe([100.0] * 30))


if __name__ == "__main__":
    unittest.main()
