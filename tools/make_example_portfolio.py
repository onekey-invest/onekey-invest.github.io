"""예시 거래 기록과 백테스트 파일을 만든다. 실제 운용 기록이 아니다.

예시 시세 파일의 종가를 읽어 그 가격으로 체결한 것처럼 적는다.
실행: python tools/make_example_prices.py 다음에 python tools/make_example_portfolio.py
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 전략: [(날짜, 종목 id, 구분, 수량, 메모)]
TRADES = {
    "dom-a": [
        (date(2026, 4, 6), "ex001", "매수", 50, "목표주가 상향 다음 거래일 편입"),
        (date(2026, 4, 6), "ex003", "매수", 33, "편입"),
        (date(2026, 7, 1), "ex003", "매도", 8, "분기 점검, 비중 축소"),
    ],
    "dom-b": [
        (date(2025, 12, 16), "ex002", "매수", 190, "커버리지 개시 다음 거래일 편입"),
        (date(2026, 6, 11), "ex002", "매도", 190, "의견 하향 다음 거래일 전량 매도"),
    ],
}

# 백테스트: 전략 → (시작, 끝, {종목: 비중})
BACKTESTS = {
    "dom-a": (date(2025, 10, 1), date(2026, 4, 3), {"ex001": 0.5, "ex003": 0.5}),
}


def closes(name):
    with open(ROOT / "data" / "prices" / f"{name}.csv", encoding="utf-8") as f:
        return {date.fromisoformat(r["date"]): float(r["close"]) for r in csv.DictReader(f)}


def main():
    cache = {}

    def px(asset, d):
        cache.setdefault(asset, closes(asset))
        return cache[asset][d]

    (ROOT / "data" / "trades").mkdir(exist_ok=True)
    for sid, rows in TRADES.items():
        with open(ROOT / "data" / "trades" / f"{sid}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "asset", "side", "qty", "price", "note"])
            for d, asset, side, qty, note in rows:
                w.writerow([d.isoformat(), asset, side, qty, f"{px(asset, d):.0f}", note])
        print(f"trades/{sid}.csv: {len(rows)}건")

    (ROOT / "data" / "backtests").mkdir(exist_ok=True)
    for sid, (start, end, weights) in BACKTESTS.items():
        series = {a: closes(a) for a in weights}
        days = sorted(d for d in next(iter(series.values())) if start <= d <= end)
        with open(ROOT / "data" / "backtests" / f"{sid}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "value"])
            for d in days:
                v = sum(wt * series[a][d] / series[a][days[0]] for a, wt in weights.items()) * 100
                w.writerow([d.isoformat(), f"{v:.4f}"])
        print(f"backtests/{sid}.csv: {len(days)}일")


if __name__ == "__main__":
    main()
