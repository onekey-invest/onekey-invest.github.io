"""가상운용 ETF 전략의 매매 규칙(계산만. 파일은 tools/etf_strategy.py가 읽고 쓴다).

규칙: 목표 비중 + 금리 조건 + 되돌리는 폭.
- 매달 마지막 거래일에 판정한다. 한국은행 기준금리가 6개월 전 월말보다 높으면 한국 주식 몫을 현금으로 둔다.
- 금리 조건이 바뀌었거나 어느 자산이든 목표 비중에서 band 넘게 벗어나 있으면 다음 거래일 종가에 전부 목표 비중으로 되돌린다.
- 첫 매수는 운용 개시일 종가에 한다(금리 조건은 그 앞 월말 기준).
"""
from __future__ import annotations

import calendar
import math
from datetime import date

from lib import portfolio as PF


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def shift_month_end(d: date, months: int) -> date:
    """d가 속한 달에서 months개월 앞(음수)·뒤 달의 말일."""
    k = d.year * 12 + (d.month - 1) + months
    return month_end(k // 12, k % 12 + 1)


def rate_at(rates, d: date):
    """rates: [(발표일, 금리)] 오름차순. d 당일까지 발표된 마지막 금리. 없으면 None."""
    out = None
    for day, r in rates:
        if day <= d:
            out = r
        else:
            break
    return out


def rate_rising(rates, decision: date, months: int = 6) -> bool:
    """판정일의 기준금리가 months개월 전 월말의 기준금리보다 높은가."""
    now, before = rate_at(rates, decision), rate_at(rates, shift_month_end(decision, -months))
    if now is None or before is None:
        raise ValueError(f"{decision}: 기준금리 자료가 모자란다")
    return now > before + 1e-9


def target_weights(weights: dict, kr_asset: str, rising: bool) -> dict:
    """금리 조건이 켜지면 한국 주식 몫을 뺀다(그만큼 현금)."""
    return {a: (0.0 if (rising and a == kr_asset) else w) for a, w in weights.items()}


def decision_days(dates):
    """거래일 목록에서 (그 달의 마지막 거래일, 다음 달의 첫 거래일) 짝. 다음 달 첫 거래일이 아직 없으면 넣지 않는다."""
    out = []
    for a, b in zip(dates, dates[1:]):
        if (a.year, a.month) != (b.year, b.month):
            out.append((a, b))
    return out


def weights_now(qty: dict, cash: float, closes: dict):
    value = cash + sum(q * closes[a] for a, q in qty.items())
    return {a: q * closes[a] / value for a, q in qty.items()}, value


def needs_rebalance(qty, cash, closes, target, band) -> bool:
    w, _ = weights_now(qty, cash, closes)
    return any(abs(w.get(a, 0.0) - t) > band for a, t in target.items())


def orders(qty: dict, cash: float, closes: dict, target: dict, fee: float, day: date, note: str):
    """목표 비중으로 맞추는 거래(매도 먼저). 수량은 정수, 수수료를 남기고 산다."""
    _, value = weights_now(qty, cash, closes)
    want = {a: math.floor(value * w / (closes[a] * (1 + fee))) for a, w in target.items()}
    sells, buys = [], []
    for a in sorted(set(qty) | set(want)):
        d = want.get(a, 0) - qty.get(a, 0)
        if d < 0:
            sells.append(PF.Trade(day, a, PF.SELL, float(-d), closes[a], note))
        elif d > 0:
            buys.append([a, d])
    cash_after = cash + sum(t.amount * (1 - fee) for t in sells)
    # 현금이 모자라면 금액이 큰 매수부터 한 주씩 줄인다
    while buys and sum(n * closes[a] * (1 + fee) for a, n in buys) > cash_after + 1e-6:
        big = max(buys, key=lambda x: x[1] * closes[x[0]])
        big[1] -= 1
        buys = [b for b in buys if b[1] > 0]
    return sells + [PF.Trade(day, a, PF.BUY, float(n), closes[a], note) for a, n in buys]


def position(initial: float, trades, fee: float):
    """거래 기록으로 지금의 보유 수량과 현금을 만든다."""
    cash, qty = float(initial), {}
    for t in trades:
        if t.side == PF.BUY:
            cash -= t.amount * (1 + fee)
            qty[t.asset] = qty.get(t.asset, 0.0) + t.qty
        else:
            cash += t.amount * (1 - fee)
            qty[t.asset] = qty.get(t.asset, 0.0) - t.qty
            if qty[t.asset] < 1e-9:
                del qty[t.asset]
    return qty, cash


def new_trades(cfg: dict, prices: dict, calendar_days, rates, trades, state: dict):
    """아직 적지 않은 거래를 만든다. 반환: (새 거래 목록, 새 상태).

    cfg: started, initial, commission, auto{weights, kr_asset, band, rate_months}
    prices: {자산: {날짜: 종가}}. calendar_days: 벤치마크의 거래일(오름차순). rates: [(날짜, 금리)].
    state: {"last_decision": "YYYY-MM-DD" 또는 None, "rising": bool 또는 None}
    """
    auto, fee = cfg["auto"], cfg.get("commission", 0.0)
    weights, kr, band, months = auto["weights"], auto["kr_asset"], auto.get("band", 0.05), auto.get("rate_months", 6)
    days = [d for d in calendar_days if d >= cfg["started"]]
    out, trades, state = [], list(trades), dict(state)

    def closes_on(d):
        c = {a: prices[a].get(d) for a in weights}
        return c if all(v is not None for v in c.values()) else None

    if not days:
        return out, state
    if not trades:                                   # 첫 매수
        d0 = days[0]
        c = closes_on(d0)
        if c is None:
            return out, state
        prev_me = shift_month_end(d0, -1)
        rising = rate_rising(rates, prev_me, months)
        note = "첫 매수" + (" (금리 조건이 켜져 한국 주식 몫은 현금)" if rising else "")
        first = orders({}, cfg["initial"], c, target_weights(weights, kr, rising), fee, d0, note)
        out += first
        trades += first
        state = {"last_decision": prev_me.isoformat(), "rising": rising}
    last = date.fromisoformat(state["last_decision"]) if state.get("last_decision") else None
    all_days = list(calendar_days)
    for dec, ex in decision_days(all_days):
        if dec < cfg["started"] or (last and dec <= last):
            continue
        c_dec, c_ex = closes_on(dec), closes_on(ex)
        if c_dec is None or c_ex is None:
            break
        rising = rate_rising(rates, dec, months)
        qty, cash = position(cfg["initial"], trades, fee)
        target = target_weights(weights, kr, rising)
        flipped = state.get("rising") is not None and rising != state["rising"]
        if flipped or needs_rebalance(qty, cash, c_dec, target, band):
            why = ("금리 조건 " + ("켜짐: 한국 주식 몫을 현금으로" if rising else "꺼짐: 한국 주식을 다시 삼")) if flipped else f"목표 비중에서 {band * 100:g}%p 넘게 벗어나 되돌림"
            new = orders(qty, cash, c_ex, target, fee, ex, why)
            out += new
            trades += new
        state = {"last_decision": dec.isoformat(), "rising": rising}
        last = dec
    return out, state
