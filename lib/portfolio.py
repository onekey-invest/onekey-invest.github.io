"""가상운용 계산.

거래 기록과 일별 종가로 날마다의 평가금액을 만들고, 거기서 수익률·MDD·샤프를 구한다.
실제 주문은 내지 않는다. 계산식은 content/pages/methodology.md와 같아야 한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

BUY, SELL = "매수", "매도"


@dataclass(frozen=True)
class Trade:
    date: date
    asset: str
    side: str
    qty: float
    price: float
    note: str = ""

    @property
    def amount(self) -> float:
        return self.qty * self.price


def run(initial, trades, prices, calendar, commission=0.0, sell_tax=0.0):
    """평가금액을 날마다 계산한다.

    initial: 초기자금. trades: Trade 목록. prices: {자산: Series}.
    calendar: 운용 개시일부터 마지막 날까지의 거래일(오름차순).
    commission: 매수·매도 금액에 곱하는 수수료율. sell_tax: 매도 금액에 곱하는 세율.

    평가금액 = 현금 + Σ(보유 수량 × 그날 종가). 거래는 기록된 가격으로 그날 체결된 것으로 본다.
    """
    if not calendar:
        raise ValueError("거래일이 없다")
    days = set(calendar)
    by_day = {}
    for t in trades:
        if t.date not in days:
            raise ValueError(f"{t.date} {t.asset}: 거래일이 아니거나 운용 기간 밖이다")
        if t.side not in (BUY, SELL):
            raise ValueError(f"{t.date} {t.asset}: 구분은 매수 또는 매도여야 한다")
        if t.qty <= 0 or t.price <= 0:
            raise ValueError(f"{t.date} {t.asset}: 수량과 가격은 0보다 커야 한다")
        if t.asset not in prices:
            raise ValueError(f"{t.asset}: 시세 파일이 없다")
        by_day.setdefault(t.date, []).append(t)

    cash = float(initial)
    qty, cost = {}, {}          # 보유 수량, 매입 원가 합계
    fees = 0.0
    nav = []
    for d in calendar:
        for t in by_day.get(d, []):
            fee = t.amount * commission + (t.amount * sell_tax if t.side == SELL else 0.0)
            fees += fee
            if t.side == BUY:
                cash -= t.amount + fee
                if cash < -0.5:
                    raise ValueError(f"{t.date} {t.asset}: 현금이 부족하다")
                qty[t.asset] = qty.get(t.asset, 0.0) + t.qty
                cost[t.asset] = cost.get(t.asset, 0.0) + t.amount
            else:
                held = qty.get(t.asset, 0.0)
                if t.qty > held + 1e-9:
                    raise ValueError(f"{t.date} {t.asset}: 보유 수량({held:g})보다 많이 팔았다")
                cost[t.asset] -= cost[t.asset] * (t.qty / held)
                qty[t.asset] = held - t.qty
                cash += t.amount - fee
                if qty[t.asset] < 1e-9:
                    del qty[t.asset], cost[t.asset]
        value = cash
        for a, q in qty.items():
            close = prices[a].close_at(d)
            if close is None:
                raise ValueError(f"{a}: {d} 이전 종가가 없다")
            value += q * close
        nav.append((d, value))

    last = calendar[-1]
    total = nav[-1][1]
    holdings = []
    for a, q in qty.items():
        close = prices[a].close_at(last)
        avg = cost[a] / q
        holdings.append({
            "asset": a, "qty": q, "avg": avg, "close": close, "value": q * close,
            "weight": q * close / total if total else None,
            "pnl": close / avg - 1 if avg else None,
        })
    holdings.sort(key=lambda h: -h["value"])
    return {
        "nav": nav,
        "cash": cash,
        "cash_weight": cash / total if total else None,
        "holdings": holdings,
        "fees": fees,
        "n_trades": len(trades),
    }


def total_return(nav, initial):
    return nav[-1][1] / initial - 1 if nav and initial else None


def max_drawdown(values):
    """고점 대비 가장 크게 내려간 비율. 음수 또는 0."""
    peak, worst = None, 0.0
    for v in values:
        if peak is None or v > peak:
            peak = v
        if peak:
            worst = min(worst, v / peak - 1)
    return worst if peak is not None else None


def sharpe(values, min_days=20, periods=252):
    """일별 수익률의 평균 ÷ 표준편차 × √252. 무위험수익률은 0으로 둔다.

    자료가 min_days보다 적거나 변동이 없으면 None.
    """
    rets = [b / a - 1 for a, b in zip(values, values[1:]) if a]
    if len(rets) < min_days:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    if var <= 0:
        return None
    return mean / math.sqrt(var) * math.sqrt(periods)
