"""가상운용 미국 공시 전략 넷(us-t12 · us-t12d · us-t16 · us-t16d)의 장부를 날마다 평가한다. 깃허브 매일 실행이 PC 없이 돌린다.

계산은 ver5의 code/live_daily.py와 같다(운용 쪽이 정한 규칙, 2026-10-12):
  개시일(2026-10-01) 종가에 그 달 장부대로 들었다고 본다. 달러 평가 지수 V_t = V_{t-1} × (1 + Σ 어제 비중 × 오늘 수익률) − 공매도 빌리는 값(연 1% × 판 몫 × 날수 / 365).
  달이 바뀌면 그 달 장부로 그 달 첫 거래일 종가에 갈아탄다(갈아탄 만큼 0.2%를 지수에서 뺀다). 종가가 없는 날은 앞 값.
  원화(환헤지 층): 날 수익 = (1 + 달러)(1 + 환율) − 1 + h × (웃돈 ÷ 252 − 환율 변화), h·웃돈은 그 달 HEDGE 파일.
  사이트의 자산 하나(장부 전체) = 개시일에 10,000원.
읽는 것: <장부 폴더>/BOOK_<달>.csv(판·종목·비중), BOOK_<달>.json(요약), HEDGE_<달>.json — 장부는 운용 쪽이 달마다 만든다.
         사이트의 data/prices/SP500.csv · USDKRW.csv · KOSPI.csv
종가: 야후(키 없음). 종목 기호의 '.'은 '-'로 바꾼다(BRK.B → BRK-B).
쓰는 것: data/prices/<자산 이름>.csv, data/prices/SP500KRW.csv, data/strategy_books/<id>.json,
        data/strategy_books/us/site_usd_index.csv(운용 쪽 대조용 달러 지수: date, us-t12, us-t12d, us-t16, us-t16d)
그 달 장부가 없으면 그 전 거래일에서 멈춘다(앞 달 장부로 이어 가지 않는다). 10-01부터 늘 처음부터 다시 계산한다(한 출처).
운용 쪽 대조: 달마다 장부를 만드는 PC 작업이 ver5 지수와 견준 결과를 <장부 폴더>/CHECK.json({"date", "max_diff", "note"})에 적는다.
           누적 차이가 0.1%(0.001)를 넘으면 사이트 점검(site_health.py)이 경고한다.

실행: python tools/us_book.py [--books <장부 폴더>] [--check <ver5 LIVE_INDEX.csv>]
      --check: 겹치는 날의 결과를 그 파일과 견준다(값을 쓰지 않는다)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
START = pd.Timestamp("2026-10-01")
COST, BORROW, INITIAL, UNIT = 0.002, 0.01, 10_000_000, 10_000
S = {"us-t12": ("T12", "미국 공시 선별 장부", 0.002), "us-t12d": ("T12D", "미국 공시 선별 + 추세 장부", 0.002),
     "us-t16": ("T16", "미국 공시 130·30 장부", 0.002), "us-t16d": ("T16D", "미국 공시 130·30 + 추세 장부", 0.002)}
KSEC = {"Information Technology": "정보기술", "Financials": "금융", "Health Care": "헬스케어", "Consumer Discretionary": "경기소비재",
        "Industrials": "산업재", "Other": "기타", "Consumer Staples": "필수소비재", "Materials": "소재", "Utilities": "유틸리티",
        "Energy": "에너지", "Real Estate": "부동산", "Communication Services": "커뮤니케이션"}


def read_px(path):
    return pd.read_csv(path, parse_dates=["date"]).set_index("date").close.sort_index()


def load_books(folder):
    books, meta, hedge = {}, {}, {}
    for f in sorted(glob.glob(os.path.join(folder, "BOOK_*.csv"))):
        name = os.path.basename(f)
        if not re.fullmatch(r"BOOK_\d{4}-\d{2}\.csv", name) or name < "BOOK_2026-10.csv":
            continue
        d = pd.read_csv(f)
        ym = str(d["드는 달"].iloc[0])
        books[ym] = d
        meta[ym] = json.load(open(f[:-4] + ".json", encoding="utf-8"))
    for f in glob.glob(os.path.join(folder, "HEDGE_*.json")):
        hedge[os.path.basename(f)[6:13]] = json.load(open(f, encoding="utf-8"))
    return books, meta, hedge


def fetch_closes(symbols, start, end):
    """야후 일별 종가(분할 반영). 열은 원래 기호."""
    import yfinance as yf
    ymap = {s: s.replace(".", "-") for s in symbols}
    out = {}
    syms = sorted(ymap)
    for k in range(0, len(syms), 300):
        chunk = syms[k:k + 300]
        df = yf.download([ymap[s] for s in chunk], start=start.strftime("%Y-%m-%d"), end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         auto_adjust=False, progress=False, threads=True, group_by="column")
        close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": ymap[chunk[0]]})
        for s in chunk:
            if ymap[s] in close.columns:
                out[s] = close[ymap[s]]
    P = pd.DataFrame(out)
    P.index = pd.to_datetime(P.index).tz_localize(None).normalize()
    return P.sort_index().ffill()


def evaluate(P, days, books, pan):
    """그 달 장부가 없으면 앞 달 장부로 이어 가지 않고, 그 전 거래일(마지막 정상일)에서 멈춘다(운용 쪽 조건, 2026-11-07)."""
    v, vals, cur, w, wv, short, last_day, used = 1.0, [], None, None, None, 0.0, None, []
    for d in days:
        ym = f"{d.year}-{d.month:02d}"
        if ym != cur and ym not in books:
            break
        if cur is not None:                                             # 어제 종가 → 오늘 종가
            r = (P.loc[d].reindex(w.index) / P.loc[last_day].reindex(w.index) - 1).fillna(0.0)
            hold = wv * (1 + r)
            gain = float((wv * r).sum())
            v_new = v * (1 + gain) - v * BORROW * short * (d - last_day).days / 365
            wv = hold / (1 + gain) if (1 + gain) != 0 else hold
            v = v_new
        if ym != cur and ym in books:                                   # 그 달 첫 거래일 종가에 그 달 장부로
            bk = books[ym]
            nw = bk[bk["판"] == pan].set_index("종목")["비중"].astype(float)
            nw = nw[nw.index.isin(P.columns) & P.loc[d].reindex(nw.index).notna().to_numpy()]
            if cur is not None:
                allk = nw.index.union(wv.index)
                turn = float((nw.reindex(allk).fillna(0) - wv.reindex(allk).fillna(0)).abs().sum()) / 2
                v *= 1 - COST * turn
            w, wv, short, cur = nw, nw.copy(), float(-nw[nw < 0].sum()), ym
        vals.append(v)
        used.append(d)
        last_day = d
    return pd.Series(vals, index=used), cur


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", default=str(ROOT / "data" / "strategy_books" / "us"))
    ap.add_argument("--check", help="ver5 results/live/LIVE_INDEX.csv와 견주기만 한다")
    a = ap.parse_args(argv)
    books, meta, hedge = load_books(a.books)
    if not books:
        print(f"장부가 없다: {a.books}")
        return 1
    sp = read_px(ROOT / "data" / "prices" / "SP500.csv")
    fx = read_px(ROOT / "data" / "prices" / "USDKRW.csv")
    kend = read_px(ROOT / "data" / "prices" / "KOSPI.csv").index.max()
    syms = sorted(set().union(*[set(b["종목"]) for b in books.values()]))
    P = fetch_closes(syms, START - pd.Timedelta(days=5), max(kend, sp.index.max()))
    print(f"종목 {len(syms)}개 중 종가를 받은 것 {P.shape[1]}개, {P.index.min().date()} ~ {P.index.max().date()}")
    days = [d for d in sp.index if START <= d <= min(P.index.max(), kend)]
    assert days and days[0] == START, days[:2]
    fxd = fx.reindex(fx.index.union(days)).ffill().reindex(days)
    res = {}
    for sid, (pan, asset, fee) in S.items():
        usd, cur = evaluate(P, days, books, pan)
        dd = list(usd.index)
        fxs = fxd.reindex(dd)
        ru, rfx = usd.pct_change().fillna(0.0), fxs.pct_change().fillna(0.0)
        hser = pd.Series([hedge.get(f"{d.year}-{d.month:02d}", {}).get("헤지 비율", 0.0) for d in dd], index=dd)
        bser = pd.Series([hedge.get(f"{d.year}-{d.month:02d}", {}).get("달러 선물 웃돈(연)", 0.0) for d in dd], index=dd)
        rk = (1 + ru) * (1 + rfx) - 1 + hser * (bser / 252 - rfx)
        rk.iloc[0] = 0.0
        krw, krw0 = (1 + rk).cumprod(), usd * fxs / fxs.iloc[0]
        res[sid] = (usd, krw, krw0, cur, hser)
    spk = sp.reindex(days) * fxd

    if a.check:
        L = pd.read_csv(a.check, parse_dates=["date"]).set_index("date")
        rows = []
        for sid in S:
            for kind, ser, col in (("달러", res[sid][0], sid), ("원화(헤지)", res[sid][1], f"{sid} 원화(헤지)")):
                common = ser.index.intersection(L.index)
                diff = (ser.reindex(common) - L[col].reindex(common)).abs()
                rows.append((sid, kind, len(common), float(diff.max()), str(diff.idxmax().date())))
        print("견주기(겹치는 날, 지수 차이의 최댓값):")
        for r in rows:
            print(f"  {r[0]:8s} {r[1]:8s} {r[2]}일  최대 차이 {r[3]:.6f} ({r[4]})")
        old = read_px(ROOT / "data" / "prices" / "SP500KRW.csv")
        c = spk.index.intersection(old.index)
        print(f"  SP500KRW  {len(c)}일  최대 차이 {float((spk.reindex(c) - old.reindex(c)).abs().max()):.4f}")
        return 0

    for sid, (pan, asset, fee) in S.items():
        usd, krw, krw0, cur, hser = res[sid]
        with open(ROOT / "data" / "prices" / f"{asset}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["date", "close"])
            for d, x in krw.items():
                w.writerow([str(d.date()), f"{UNIT * x:.2f}"])
        cm, bk = meta[cur], books[cur]
        mine = bk[bk["판"] == pan]
        top = mine.sort_values("비중", ascending=False).head(10)
        secw = cm["T12"]["업종 비중(%)"] if pan.startswith("T12") else cm["기준"]["업종 비중(%)"]
        last = krw.index[-1]
        j = {"asof": str(last.date()), "book_month": cur, "price_note": "평가 종가: 야후, 백테스트·장부 선정: Alpaca", "sha": cm["sha256"][:16], "n_long": int((mine["비중"] > 0).sum()),
             "n_short": int((mine["비중"] < 0).sum()), "universe": cm["살 수 있는 종목"], "stock_share": cm["주식 몫"].get(pan, 1.0),
             "top": [[r_["종목"], round(float(r_["비중"]) * 100, 2)] for _, r_ in top.iterrows()],
             "sectors": [[KSEC.get(k, k), v_] for k, v_ in list(secw.items())[:12]],
             "usd_ret": round(float(usd.iloc[-1] - 1), 6), "sp_usd_ret": round(float(sp.reindex(dd := list(krw.index)).iloc[-1] / sp.reindex(dd).iloc[0] - 1), 6),
             "fx0": round(float(fxd.reindex(dd).iloc[0]), 2), "fx1": round(float(fxd.reindex(dd).iloc[-1]), 2),
             "layers": {"상황": cm["상황 층"]["켜짐"], "추세": cm["추세 층"]["켜짐"]},
             "hedge": {"ratio": round(float(hser.iloc[-1]) * 100, 1), "n_on": hedge.get(cur, {}).get("켜진 수"),
                       "signals": [[k_, bool(v_["켜짐"])] for k_, v_ in hedge.get(cur, {}).get("신호", {}).items()],
                       "krw_unhedged_ret": round(float(krw0.iloc[-1] - 1), 6), "krw_ret": round(float(krw.iloc[-1] - 1), 6)},
             "short_examples": [x[0] for x in cm["T16"]["파는 쪽 예 15"][:8]] if pan.startswith("T16") else [],
             "long_examples": [x[0] for x in cm["T16"]["사는 쪽 예 15"][:8]] if pan.startswith("T16") else []}
        (ROOT / "data" / "strategy_books" / f"{sid}.json").write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{sid}: {last.date()}까지(장부 {cur}){' — 다음 달 장부가 없어 여기서 멈춤' if last < days[-1] else ''}, 원화 {float(krw.iloc[-1] - 1):+.4f}")
    # 운용 쪽 대조용: 사이트가 계산한 달러 지수(열 date, us-t12, us-t12d, us-t16, us-t16d). 운용 총괄 요청 2026-11-07
    ix = pd.DataFrame({sid: res[sid][0] for sid in S})
    ix.index.name = "date"
    (ROOT / "data" / "strategy_books" / "us").mkdir(parents=True, exist_ok=True)
    ix.to_csv(ROOT / "data" / "strategy_books" / "us" / "site_usd_index.csv", float_format="%.8f", date_format="%Y-%m-%d", lineterminator="\n")
    with open(ROOT / "data" / "prices" / "SP500KRW.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "close"])
        for d, x in spk.items():
            w.writerow([str(d.date()), f"{x:.2f}"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
