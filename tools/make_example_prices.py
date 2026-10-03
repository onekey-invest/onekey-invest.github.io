"""예시 시세 파일을 만든다. 실제 시세가 아니다.

정해 둔 날짜의 종가를 지나도록 선을 긋고, 그 사이에 재현 가능한 잡음을 얹는다.
실제 종가를 연결하면 이 스크립트와 data/prices의 예시 파일은 지운다.

실행: python tools/make_example_prices.py
"""
from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "prices"

# 이름: (호가 단위, 잡음 크기, [(날짜, 종가), ...])
ANCHORS = {
    "ex001": (100, 0.035, [
        (date(2025, 10, 1), 58600), (date(2025, 10, 2), 59100), (date(2026, 1, 5), 61000),
        (date(2026, 4, 3), 66800), (date(2026, 7, 1), 71000), (date(2026, 8, 31), 73600),
        (date(2026, 9, 1), 73400), (date(2026, 9, 18), 71200), (date(2026, 10, 1), 70000),
    ]),
    "ex002": (50, 0.045, [
        (date(2025, 10, 1), 31800), (date(2025, 12, 15), 33500), (date(2026, 2, 16), 36200),
        (date(2026, 6, 10), 28400), (date(2026, 8, 31), 27400), (date(2026, 9, 1), 27550),
        (date(2026, 10, 1), 26900),
    ]),
    "ex003": (100, 0.03, [
        (date(2025, 10, 1), 88000), (date(2026, 3, 9), 96000), (date(2026, 6, 15), 101500),
        (date(2026, 9, 1), 102800), (date(2026, 10, 1), 104500),
    ]),
    "KOSPI": (0.01, 0.012, [
        (date(2025, 10, 1), 3391.20), (date(2025, 10, 2), 3400.00), (date(2025, 12, 15), 3480.00),
        (date(2026, 3, 9), 3560.00), (date(2026, 4, 3), 3585.00), (date(2026, 6, 10), 3700.00),
        (date(2026, 9, 1), 3790.00), (date(2026, 10, 1), 3814.80),
    ]),
    "KOSDAQ": (0.01, 0.015, [
        (date(2025, 10, 1), 850.00), (date(2025, 12, 15), 842.00), (date(2026, 6, 10), 870.00),
        (date(2026, 9, 1), 874.00), (date(2026, 10, 1), 880.00),
    ]),
}


def business_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def build(name: str, tick: float, noise: float, anchors):
    rng = random.Random(name)
    rows = []
    for (d0, p0), (d1, p1) in zip(anchors, anchors[1:]):
        days = list(business_days(d0, d1))
        walk, w = [0.0], 0.0
        for _ in days[1:]:
            w += rng.gauss(0, 1)
            walk.append(w)
        span = len(days) - 1
        for i, d in enumerate(days[:-1]):
            t = i / span if span else 0
            # 양 끝에서 0이 되도록 걸음을 눌러 준다
            bridge = (walk[i] - t * walk[-1]) / math.sqrt(max(span, 1))
            p = (p0 + (p1 - p0) * t) * (1 + noise * bridge)
            rows.append((d, round(round(p / tick) * tick, 2)))
    rows.append(anchors[-1])
    # 구간이 맞닿는 날은 정해 둔 값으로 고정
    fixed = dict(anchors)
    return [(d, fixed.get(d, p)) for d, p in rows]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (tick, noise, anchors) in ANCHORS.items():
        rows = build(name, tick, noise, anchors)
        with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "close"])
            for d, p in rows:
                w.writerow([d.isoformat(), f"{p:.2f}" if tick < 1 else f"{p:.0f}"])
        print(f"{name}: {len(rows)}일, {rows[0][0]} ~ {rows[-1][0]}")


if __name__ == "__main__":
    main()
