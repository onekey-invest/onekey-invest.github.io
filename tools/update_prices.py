"""실제 일별 종가를 받아 data/prices/에 저장한다.

대상은 data/sources.yaml에 적는다. 국내 종목은 pykrx, 지수와 해외 종목은 yfinance로 받는다.
받은 값은 화면 계산용이다. 두 도구 모두 공식 제공 경로가 아니므로 값이 비거나 형식이 바뀔 수 있다.
한 대상이라도 실패하면 그 대상의 기존 파일은 그대로 두고, 마지막에 실패 목록을 알린 뒤 오류로 끝난다.

실행:  python tools/update_prices.py
       python tools/update_prices.py --only KOSPI 005930     일부만
       python tools/update_prices.py --config 다른.yaml --out 다른폴더
필요:  pip install pykrx yfinance
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))


def default_until(now: datetime | None = None) -> date:
    """장이 끝난 날까지만 받는다. 한국 시간 16시 전이면 어제까지."""
    now = now or datetime.now(KST)
    return now.date() if now.hour >= 16 else now.date() - timedelta(days=1)


def clean(rows, until: date):
    """(날짜, 종가) 목록을 정리한다: 빈 값·0 이하·기준일 이후를 버리고, 날짜순으로, 같은 날은 마지막 값만."""
    by_day = {}
    for d, c in rows:
        if c is None:
            continue
        c = float(c)
        if math.isnan(c) or c <= 0 or d > until:
            continue
        by_day[d] = c
    return sorted(by_day.items())


def fetch_krx(code: str, start: date, until: date):
    """국내 종목의 수정주가 종가."""
    from pykrx import stock

    df = stock.get_market_ohlcv(f"{start:%Y%m%d}", f"{until:%Y%m%d}", str(code), adjusted=True)
    return [(idx.date(), row["종가"]) for idx, row in df.iterrows()]


def fetch_yahoo(symbol: str, start: date, until: date):
    """지수와 해외 종목의 종가(액면분할은 반영, 배당은 미반영)."""
    import yfinance as yf

    df = yf.Ticker(symbol).history(start=start.isoformat(), end=(until + timedelta(days=1)).isoformat(), auto_adjust=False)
    return [(idx.date(), row["Close"]) for idx, row in df.iterrows()]


FETCHERS = {
    "krx": lambda s, start, until: fetch_krx(s["code"], start, until),
    "yahoo": lambda s, start, until: fetch_yahoo(s["symbol"], start, until),
}


def write_csv(path: Path, rows, decimals: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for d, c in rows:
            w.writerow([d.isoformat(), f"{c:.{decimals}f}"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="실제 일별 종가를 받아 저장한다")
    ap.add_argument("--config", default=str(ROOT / "data" / "sources.yaml"))
    ap.add_argument("--out", default=str(ROOT / "data" / "prices"))
    ap.add_argument("--only", nargs="*", help="이 이름들만 받는다")
    ap.add_argument("--until", help="이 날짜까지만 (YYYY-MM-DD). 기본은 장이 끝난 마지막 날")
    args = ap.parse_args(argv)

    until = date.fromisoformat(args.until) if args.until else default_until()
    with open(args.config, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or {}
    if args.only:
        missing = [n for n in args.only if n not in sources]
        if missing:
            print(f"sources에 없는 이름: {', '.join(missing)}")
            return 2
        sources = {n: sources[n] for n in args.only}
    if not sources:
        print("받을 대상이 없다. data/sources.yaml에 대상을 적는다.")
        return 0

    failed = []
    for name, s in sources.items():
        kind = s.get("source")
        start = s.get("start") or date(until.year - 3, 1, 1)
        try:
            if kind not in FETCHERS:
                raise ValueError(f"source는 krx 또는 yahoo여야 한다: {kind}")
            rows = clean(FETCHERS[kind](s, start, until), until)
            if not rows:
                raise ValueError("받은 값이 없다")
            decimals = 2 if any(c != int(c) for _, c in rows) else 0
            write_csv(Path(args.out) / f"{name}.csv", rows, decimals)
            print(f"{name}: {len(rows)}일, {rows[0][0]} ~ {rows[-1][0]}, 마지막 종가 {rows[-1][1]:,.{decimals}f}")
        except Exception as e:  # 한 대상의 실패가 나머지를 막지 않게 한다
            failed.append(name)
            print(f"{name}: 실패 ({type(e).__name__}: {e}). 기존 파일은 그대로 둔다.")

    if failed:
        print(f"실패 {len(failed)}건: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
