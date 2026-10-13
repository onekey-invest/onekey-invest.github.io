"""가상운용 국내 개선 롱숏(kr-x1) · 국내 개선 롱숏 + KODEX(kr-x2): 든 종목 전체를 자산 하나로 평가해 날마다 적는다.

읽는 것
  data/strategy_books/kr-x.picks.csv   고르는 날(월말)마다의 롱 40종목과 숏 종목(pick_date, side, code, name, market, sector, mktcap_eok, universe).
                                       달마다 한 번 손으로 더한다(재무 자료로 고르기 때문에 이 저장소 밖에서 만든다).
  data/prices/KOSPI.csv, KODEX 200.csv 거래일과 KODEX 200 종가(tools/update_prices.py가 받는다)
  data/rates/bok_base_rate.csv         숏으로 판 돈에 붙는 이자(한국은행 기준금리)
  야후 파이낸스                         든 종목의 종가(코스피 .KS, 코스닥 .KQ)
쓰는 것
  data/prices/국내 개선 롱숏 장부.csv, 국내 개선 롱숏 + KODEX 장부.csv   묶음 전체의 평가값(첫 체결일 = 10,000)
  data/strategy_books/kr-x1.json, kr-x2.json                              화면의 '보유 기준' 칸에 쓰는 요약

셈
  체결일 = 고르는 날 다음의 첫 거래일. 그날 종가로 목표 비중에 맞춘다(이어서 드는 종목도 다시 맞춘다). 다음 체결일까지 그대로 둔다.
  kr-x1: 롱 40종목 100%(같은 금액씩) + 숏. kr-x2: 롱 40종목 50% + KODEX 200 50% + 숏.
  숏: 통과 종목에 같은 금액씩, 합쳐서 30%까지, 한 종목 3%까지. 통과 종목이 5개 미만이면 숏 없음.
       숏 금액에는 날마다 (기준금리 − 차입 연 3%) ÷ 365가 붙는다(판 돈의 이자에서 주식 빌리는 값을 뺀 것).
  갈아탈 때 비용: 주식을 늘리면 0.115%, 줄이면 0.315%(숏을 여는 것은 줄이는 쪽, 갚는 것은 늘리는 쪽). KODEX 200은 양쪽 0.115%.
       첫 체결일의 롱 매수 비용은 거래 기록(data/trades/)의 수수료로 따로 잡히므로 여기서는 숏을 여는 비용만 뺀다(다음 거래일 값에 반영).
  배당은 넣지 않는다. 시세가 끊긴 종목은 마지막 종가로 든 것으로 본다.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = {"kr-x1": ("국내 개선 롱숏 장부", 1.0, 0.0), "kr-x2": ("국내 개선 롱숏 + KODEX 장부", 0.5, 0.5)}   # id: (장부 이름, 롱 비중, KODEX 비중)
SHORT_MAX, SHORT_CAP, SHORT_MIN_N, BORROW = 0.30, 0.03, 5, 0.03
BUY, SELL = 0.00115, 0.00315
SECTOR = {"Information Technology": "정보기술", "Health Care": "헬스케어", "Industrials": "산업재", "Consumer Discretionary": "임의소비재",
          "Consumer Staples": "필수소비재", "Energy": "에너지", "Materials": "소재", "Communication Services": "커뮤니케이션", "Utilities": "유틸리티",
          "Financials": "금융", "Real Estate": "부동산"}


def read_series(name):
    with open(ROOT / "data" / "prices" / f"{name}.csv", encoding="utf-8") as f:
        return {date.fromisoformat(r["date"]): float(r["close"]) for r in csv.DictReader(f)}


def at(series, d):
    keys = [k for k in series if k <= d]
    return series[max(keys)] if keys else None


def base_rate(d):
    with open(ROOT / "data" / "rates" / "bok_base_rate.csv", encoding="utf-8") as f:
        rows = sorted((date.fromisoformat(r["date"]), float(r["rate"])) for r in csv.DictReader(f))
    cur = rows[0][1]
    for k, v in rows:
        if k <= d:
            cur = v
    return cur / 100


def fetch(codes, start):
    import yfinance as yf

    px = {}
    for code, market in codes:
        t = f"{code}.{'KS' if market == 'KOSPI' else 'KQ'}"
        df = yf.Ticker(t).history(start=(start - timedelta(days=10)).isoformat(), auto_adjust=False)
        px[code] = {i.date(): float(r["Close"]) for i, r in df.iterrows() if r["Close"] == r["Close"] and r["Close"] > 0}
    return px


def targets(rows, w_long, w_kodex):
    longs = [r for r in rows if r["side"] == "long"]
    shorts = [r for r in rows if r["side"] == "short"]
    w = {r["code"]: w_long / len(longs) for r in longs}
    if w_kodex:
        w["KODEX200"] = w_kodex
    if len(shorts) >= SHORT_MIN_N:
        each = min(SHORT_MAX / len(shorts), SHORT_CAP)
        for r in shorts:
            w[r["code"]] = w.get(r["code"], 0.0) - each
    return w


def main():
    with open(ROOT / "data" / "strategy_books" / "kr-x.picks.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    picks = {}
    for r in rows:
        picks.setdefault(date.fromisoformat(r["pick_date"]), []).append(r)
    info = {r["code"]: r for r in rows}
    kospi, kodex = read_series("KOSPI"), read_series("KODEX 200")
    days = sorted(kospi)
    first_pick = min(picks)
    px = fetch(sorted({(r["code"], r["market"]) for r in rows}), first_pick)
    px["KODEX200"] = kodex
    missing = sorted(c for c, s in px.items() if not s)
    trade_day = {}                                    # 체결일 → 고른 날
    for p in sorted(picks):
        nxt = [d for d in days if d > p]
        if nxt:
            trade_day[nxt[0]] = p
    start = min(trade_day)
    cal = [d for d in days if d >= start]
    for sid, (book, w_long, w_kodex) in BOOKS.items():
        nav, w, out, pending_cost, cur_pick = 10000.0, {}, [], 0.0, None
        prev = None
        for d in cal:
            if prev is not None:                      # 어제 종가 → 오늘 종가
                ret, gross_short = 0.0, 0.0
                for c, wt in w.items():
                    p0, p1 = at(px.get(c, {}), prev), at(px.get(c, {}), d)
                    r = (p1 / p0 - 1) if p0 and p1 else 0.0
                    ret += wt * r
                    w[c] = wt * (1 + r)
                    if wt < 0:
                        gross_short += -wt
                carry = gross_short * (base_rate(d) - BORROW) * (d - prev).days / 365
                tot = 1 + ret + carry - pending_cost
                pending_cost = 0.0
                nav *= tot
                w = {c: v / tot for c, v in w.items()}
            if d in trade_day:                        # 오늘 종가로 목표 비중에 맞춘다
                cur_pick = trade_day[d]
                tgt = targets(picks[cur_pick], w_long, w_kodex)
                cost = 0.0
                for c in set(tgt) | set(w):
                    dlt = tgt.get(c, 0.0) - w.get(c, 0.0)
                    if c == "KODEX200":
                        cost += abs(dlt) * BUY
                    else:
                        cost += dlt * BUY if dlt > 0 else -dlt * SELL
                if d == start:                        # 첫 롱·KODEX 매수 비용은 거래 기록의 수수료로 잡힌다. 숏을 여는 비용만 뺀다
                    cost = sum(-v for v in tgt.values() if v < 0) * SELL
                pending_cost = cost                   # 다음 거래일 값에 반영
                w = dict(tgt)
            out.append((d, nav))
            prev = d
        with open(ROOT / "data" / "prices" / f"{book}.csv", "w", encoding="utf-8", newline="") as f:
            wr = csv.writer(f, lineterminator="\n")
            wr.writerow(["date", "close"])
            wr.writerows((d.isoformat(), f"{v:.2f}") for d, v in out)
        asof = out[-1][0]
        cur = picks[cur_pick]
        longs = [r for r in cur if r["side"] == "long"]
        shorts = [r for r in cur if r["side"] == "short"]
        on = len(shorts) >= SHORT_MIN_N
        pos = sorted(((info[c]["name"] if c in info else "KODEX 200", v * 100) for c, v in w.items() if v > 0), key=lambda x: -x[1])
        sec = {}
        for c, v in w.items():
            if v > 0 and c in info:
                k = SECTOR.get(info[c]["sector"], "기타")
                sec[k] = sec.get(k, 0.0) + v * 100
        if w.get("KODEX200"):
            sec["KODEX 200"] = w["KODEX200"] * 100
        summary = {
            "asof": asof.isoformat(), "book_month": f"{cur_pick.year}년 {cur_pick.month}월 말", "kr": True,
            "n_long": len(longs) + (1 if w_kodex else 0), "n_short": len(shorts) if on else 0, "universe": int(longs[0]["universe"]),
            "stock_share": round(sum(v for v in w.values() if v > 0), 4), "short_share": round(sum(-v for v in w.values() if v < 0), 4),
            "top": [[n, round(v, 2)] for n, v in pos[:10]],
            "sectors": [[k, round(v, 1)] for k, v in sorted(sec.items(), key=lambda x: -x[1])],
            "long_examples": [r["name"] for r in longs[:8]], "short_examples": [r["name"] for r in shorts] if on else [],
            "bench_ret": round(at(kospi, asof) / at(kospi, start) - 1, 4), "book_ret": round(out[-1][1] / 10000 - 1, 4),
            "trade_dates": [d.isoformat() for d in sorted(trade_day) if d <= asof], "missing": missing,
        }
        (ROOT / "data" / "strategy_books" / f"{sid}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{sid}: {start} ~ {asof} · {len(out)}일 · 평가값 {out[-1][1]:,.2f} ({out[-1][1] / 100 - 100:+.2f}%) · KOSPI {summary['bench_ret'] * 100:+.2f}% · "
              f"롱 {len(longs)} · 숏 {summary['n_short']}(합 {summary['short_share'] * 100:.1f}%) · 시세 없음 {len(missing)}")


if __name__ == "__main__":
    sys.exit(main())
