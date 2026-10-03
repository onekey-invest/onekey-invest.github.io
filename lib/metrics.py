"""성과 계산.

모든 수익률은 일별 종가 기준의 가격 수익률이다. 배당은 포함하지 않는다.
계산식은 content/pages/methodology.md에 적힌 내용과 같아야 한다.
"""
from __future__ import annotations

import calendar
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Series:
    """날짜 오름차순의 일별 종가."""

    dates: tuple
    closes: tuple

    def __post_init__(self):
        if len(self.dates) != len(self.closes):
            raise ValueError("날짜와 종가의 개수가 다르다")
        if any(a >= b for a, b in zip(self.dates, self.dates[1:])):
            raise ValueError("날짜가 오름차순이 아니거나 중복이 있다")

    def __len__(self):
        return len(self.dates)

    def at(self, d: date):
        """d 당일 또는 그 이전 마지막 거래일의 (날짜, 종가). 없으면 None."""
        i = bisect_right(self.dates, d) - 1
        if i < 0:
            return None
        return self.dates[i], self.closes[i]

    def close_at(self, d: date):
        hit = self.at(d)
        return hit[1] if hit else None

    @property
    def last_date(self) -> date:
        return self.dates[-1]

    @property
    def last_close(self) -> float:
        return self.closes[-1]

    def between(self, start: date, end: date) -> "Series":
        pairs = [(d, c) for d, c in zip(self.dates, self.closes) if start <= d <= end]
        return Series(tuple(d for d, _ in pairs), tuple(c for _, c in pairs))


def months_before(d: date, n: int) -> date:
    """d에서 n개월 전의 같은 날. 그 달에 없는 날이면 말일로 맞춘다."""
    y, m = d.year, d.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def simple_return(start_price, end_price):
    """end / start - 1. 값이 없거나 시작가가 0 이하면 None."""
    if start_price is None or end_price is None or start_price <= 0:
        return None
    return end_price / start_price - 1


def period_return(series: Series, start: date, end: date):
    """start 종가 대비 end 종가의 수익률. 각 날짜는 그 이전 마지막 거래일로 맞춘다."""
    return simple_return(series.close_at(start), series.close_at(end))


def upside(target, price):
    """상승여력 = 목표주가 / 종가 - 1."""
    return simple_return(price, target)


def excess(r, rb):
    """초과수익(소수). 화면에는 %p로 표시한다."""
    if r is None or rb is None:
        return None
    return r - rb


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None
