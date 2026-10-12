"""가상운용 Bottom-Up 1 · US: 든 30종목 전체를 자산 하나로 평가해 날마다 적는다.

읽는 것
  data/strategy_books/bu-us.picks.csv  고르는 날마다의 30종목(pick_date, ticker, sector, score, universe, passed). 3개월마다 한 번 손으로 더한다.
  data/prices/USDKRW.csv, SP500.csv    원/달러와 S&P 500(tools/update_prices.py가 받는다)
  야후 파이낸스                         든 종목의 종가와 배당
쓰는 것
  data/prices/Bottom-Up 1 US 장부.csv   묶음 전체의 원화 평가값(첫 체결일 = 10,000)
  data/strategy_books/bu-us.json        화면의 '보유 기준' 칸에 쓰는 요약
  data/prices/SP500KRW_FX.csv           견줄 지수: S&P 500 × 원/달러(2026년 1월부터. SP500KRW.csv는 10월부터라 따로 만든다)

셈
  체결일 = 고르는 날 다음의 첫 거래일. 그날 종가로 30종목을 같은 비중으로 산다(이어서 드는 종목도 다시 같은 비중으로 맞춘다).
  다음 체결일까지 그대로 든다. 배당은 배당락일에 현금으로 더한다(이자 0).
  갈아탈 때 비용: 바뀐 비중 × (살 때 0.1% + 팔 때 0.1%). 첫 매수 비용은 거래 기록(data/trades/bu-us.csv)의 수수료로 따로 잡힌다.
  시세가 끊긴 종목은 마지막 종가로 든 것으로 본다.
  원화 값 = 달러 값 × 그날 원/달러(환헤지 없음).
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOK = "Bottom-Up 1 US 장부"
COST = 0.001                      # 한쪽 비용
SECTOR = {"Information Technology": "정보기술", "Health Care": "헬스케어", "Industrials": "산업재", "Consumer Discretionary": "임의소비재", "Consumer Staples": "필수소비재",
          "Energy": "에너지", "Materials": "소재", "Communication Services": "커뮤니케이션", "Utilities": "유틸리티", "Other": "기타"}


def read_series(name):
    with open(ROOT / "data" / "prices" / f"{name}.csv", encoding="utf-8") as f:
        return {date.fromisoformat(r["date"]): float(r["close"]) for r in csv.DictReader(f)}


def at(series, d):
    """d 또는 그 앞의 가장 가까운 날의 값."""
    keys = [k for k in series if k <= d]
    return series[max(keys)] if keys else None


def fetch(tickers, start):
    import yfinance as yf

    px, div = {}, {}
    for t in tickers:
        df = yf.Ticker(t.replace(".", "-")).history(start=(start - timedelta(days=7)).isoformat(), auto_adjust=False, actions=True)
        px[t] = {i.date(): float(r["Close"]) for i, r in df.iterrows() if r["Close"] == r["Close"]}
        div[t] = {i.date(): float(r["Dividends"]) for i, r in df.iterrows() if r.get("Dividends", 0) > 0}
    return px, div


def main():
    with open(ROOT / "data" / "strategy_books" / "bu-us.picks.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    picks = {}
    for r in rows:
        picks.setdefault(date.fromisoformat(r["pick_date"]), []).append(r)
    pick_dates = sorted(picks)
    tickers = sorted({r["ticker"] for r in rows})
    px, div = fetch(tickers, pick_dates[0])
    missing = [t for t in tickers if not px[t]]
    if len(missing) > 3:
        sys.exit(f"시세를 못 받은 종목이 많다: {missing}")
    fx, sp = read_series("USDKRW"), read_series("SP500")
    with open(ROOT / "data" / "prices" / "SP500KRW_FX.csv", "w", encoding="utf-8", newline="") as f:   # 견줄 지수(원화)
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for d in sorted(sp):
            if at(fx, d):
                w.writerow([d.isoformat(), f"{sp[d] * at(fx, d):.2f}"])
    days = sorted({d for t in tickers for d in px[t] if d > pick_dates[0]})
    days = [d for d in days if sum(d in px[t] for t in tickers) >= len(tickers) * 0.8 and at(fx, d) and d in sp]   # 대부분의 종목이 거래된 날만
    if not days:
        sys.exit("체결일 이후 거래일이 없다")
    trade_days = {next(d for d in days if d > p): p for p in pick_dates if any(d > p for d in days)}

    def last_px(t, d):
        return at(px[t], d)

    nav, cash, shares, held, out, usd_curve = 1.0, 0.0, {}, [], [], []
    for d in days:
        if shares:
            for t in held:                                   # 배당락일에 현금으로 더한다
                if d in div[t]:
                    cash += shares[t] * div[t][d]
            nav = cash + sum(shares[t] * last_px(t, d) for t in held)
        if d in trade_days:                                  # 그날 종가로 갈아탄다
            new = [r["ticker"] for r in picks[trade_days[d]] if last_px(r["ticker"], d)]
            if held:
                w_old = {t: shares[t] * last_px(t, d) / nav for t in held}
                turn = sum(max(1 / len(new) - w_old.get(t, 0.0), 0.0) for t in new)   # 새로 사야 하는 비중
                nav *= 1 - turn * 2 * COST
            held, cash = new, 0.0
            shares = {t: nav / len(held) / last_px(t, d) for t in held}
            cur_pick = trade_days[d]
        usd_curve.append((d, nav))
    d0 = min(trade_days)
    usd_curve = [(d, v) for d, v in usd_curve if d >= d0]
    base = usd_curve[0][1] * at(fx, d0)
    krw = [(d, v * at(fx, d) / base * 10000) for d, v in usd_curve]
    with open(ROOT / "data" / "prices" / f"{BOOK}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for d, v in krw:
            w.writerow([d.isoformat(), f"{v:.2f}"])
    asof = usd_curve[-1][0]
    weights = sorted(((t, shares[t] * last_px(t, asof) / nav * 100) for t in held), key=lambda x: -x[1])
    sec = {}
    for r in picks[cur_pick]:
        if r["ticker"] in shares:
            k = SECTOR.get(r["sector"], r["sector"])
            sec[k] = sec.get(k, 0.0) + shares[r["ticker"]] * last_px(r["ticker"], asof) / nav * 100
    first = picks[cur_pick][0]
    summary = {"asof": asof.isoformat(), "book_month": f"{cur_pick.year}년 {cur_pick.month}월 말에 고른", "n_long": len(held), "n_short": 0,
               "universe": int(first.get("universe") or 0), "passed": int(first.get("passed") or 0), "stock_share": round(1 - cash / nav, 4),
               "top": [[t, round(w_, 2)] for t, w_ in weights[:10]], "sectors": [[k, round(v)] for k, v in sorted(sec.items(), key=lambda x: -x[1])],
               "usd_ret": round(usd_curve[-1][1] / usd_curve[0][1] - 1, 6), "sp_usd_ret": round(at(sp, asof) / at(sp, d0) - 1, 6),
               "fx0": round(at(fx, d0), 2), "fx1": round(at(fx, asof), 2), "trade_dates": [d.isoformat() for d in sorted(trade_days)], "missing": missing}
    (ROOT / "data" / "strategy_books" / "bu-us.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{BOOK}: {d0} ~ {asof} · 달러 {summary['usd_ret'] * 100:+.2f}% (S&P 500 {summary['sp_usd_ret'] * 100:+.2f}%) · 원화 {krw[-1][1] / 100 - 100:+.2f}% · 종목 {len(held)} · 시세 없는 종목 {missing}")


if __name__ == "__main__":
    main()
