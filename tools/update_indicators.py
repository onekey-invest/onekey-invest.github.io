"""산업 핵심 지표(data/indicators/<산업>.csv)의 빈 칸과 새 기간을 키 없이 채운다(매일 실행).

출처는 data/indicator_sources.yaml. 이미 있는 값은 고치지 않는다(산업 모델에서 넣은 값이 우선).
기간이 끝난 뒤에만 줄을 더한다(분기: 분기 첫날의 3달 뒤 달의 1일로 적는 기존 꼴 = 분기 마지막 달 1일).
실행: python tools/update_indicators.py [--dry]
"""
from __future__ import annotations

import csv
import io
import sys
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
IND = ROOT / "data" / "indicators"


def qkey(d):            # 분기 끝 날짜 → csv의 날짜(분기 마지막 달 1일)
    return f"{d.year}-{d.month:02d}-01"


_yq = {}


def yahoo_q(symbol):
    """{분기 키: (매출, 영업이익)}"""
    if symbol not in _yq:
        import yfinance as yf
        t = yf.Ticker(symbol).quarterly_income_stmt
        out = {}
        for c in t.columns:
            rev = t.at["Total Revenue", c] if "Total Revenue" in t.index else None
            op = t.at["Operating Income", c] if "Operating Income" in t.index else None
            out[qkey(c.date())] = (None if rev is None or rev != rev else float(rev), None if op is None or op != op else float(op))
        _yq[symbol] = out
    return _yq[symbol]


def yahoo_sum(symbols, k, idx):
    vals = [yahoo_q(s).get(k, (None, None))[idx] for s in symbols]
    return None if any(v is None for v in vals) else sum(vals)


_fred = {}


def fred(series):
    if series not in _fred:
        # FRED는 이름을 붙인 클라이언트를 늦게 받는다(2026-11-07 시험). 파이썬 기본 머리말로 받는다
        req = urllib.request.Request(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=2020-01-01")
        for k in range(3):
            try:
                text = urllib.request.urlopen(req, timeout=90).read().decode("utf-8")
                break
            except Exception:
                if k == 2:
                    raise
        out = {}
        for r in list(csv.reader(io.StringIO(text)))[1:]:
            if len(r) == 2 and r[1] not in ("", "."):
                out[r[0]] = float(r[1])
        _fred[series] = out
    return _fred[series]


CASINO_CACHE = IND / "_casino.json"
_casino = None


def casino_parse(text):
    """월 잠정실적 공시 본문 → (카지노 매출, 드롭액), 백만원. 당기실적(그 달) 값."""
    import re
    rev = re.search(r"카지노\s*매출액\s*(\d{1,3}(?:,\d{3})+|\d+)", text)
    i = max(text.find("드롭액"), text.find("드랍액"))
    drop = None
    if i >= 0:
        j = text.find("====", i)
        m = re.search(r"(\d{1,3}(?:,\d{3})+)", text[j:]) if j >= 0 else None
        drop = m.group(1) if m else None
    if not rev or not drop:
        return None
    return float(rev.group(1).replace(",", "")), float(drop.replace(",", ""))


def casino_months(corps):
    """세 회사의 월 잠정실적 공시를 DART RSS(키 없이, 최근 5영업일)에서 찾아 읽고 _casino.json에 쌓는다. {달: {corp: {...}}}"""
    global _casino
    if _casino is not None:
        return _casino
    import json
    sys.path.insert(0, str(ROOT / "tools"))
    from update_disclosures import by_rss, period_of
    from score_actuals import doc_text
    cache = json.loads(CASINO_CACHE.read_text(encoding="utf-8")) if CASINO_CACHE.exists() else {}
    for corp in corps:
        try:
            items = by_rss("casino", corp)
        except Exception as e:
            print(f"카지노 {corp}: RSS 못 받음 ({type(e).__name__})")
            continue
        for it in items:
            if "영업(잠정)실적" not in it["name"] or it.get("corrected"):
                continue
            per = period_of(it["rcept_no"])
            if not per or per[0][:7] != per[1][:7]:          # 한 달짜리만
                continue
            ym = per[0][:7]
            if corp in cache.get(ym, {}):
                continue
            text = doc_text(it["rcept_no"])
            v = casino_parse(text) if text else None
            if v:
                cache.setdefault(ym, {})[corp] = {"rcept_no": it["rcept_no"], "revenue": v[0], "drop": v[1]}
                print(f"카지노 {corp} {ym}: 매출 {v[0]:,.0f} · 드롭액 {v[1]:,.0f} 백만원")
    CASINO_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    _casino = cache
    return cache


def value(spec, k):
    kind = spec["kind"]
    if kind == "dart_casino_monthly":
        m = casino_months(spec["corps"]).get(k[:7], {})
        if not all(c in m for c in spec["corps"]):
            return None
        return round(sum(m[c][spec["field"]] for c in spec["corps"]) / spec.get("scale", 1), 2)
    if kind == "yahoo_q_revenue":
        v = yahoo_sum(spec["symbols"], k, 0)
        return None if v is None else round(v / spec.get("scale", 1), 2)
    if kind == "yahoo_q_margin":
        rev, op = yahoo_sum(spec["symbols"], k, 0), yahoo_sum(spec["symbols"], k, 1)
        return None if not rev or op is None else round(op / rev * 100, 2)
    if kind == "fred_monthly":
        v = fred(spec["series"]).get(k)
        return None if v is None else round(v, 2)
    raise ValueError(kind)


def periods_after(last, freq, today):
    """last(csv 날짜) 뒤로 끝난 기간의 키들."""
    y, m = int(last[:4]), int(last[5:7])
    step = 3 if freq == "Q" else 1
    out = []
    while True:
        m += step
        if m > 12:
            y, m = y + 1, m - 12
        nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
        if date(nm_y, nm_m, 1) > today:        # 그 달이 다 끝나야
            return out
        out.append(f"{y}-{m:02d}-01")


def main(argv):
    dry = "--dry" in argv
    spec = yaml.safe_load((ROOT / "data" / "indicator_sources.yaml").read_text(encoding="utf-8")) or {}
    today = date.today()
    for iid, s in spec.items():
        path = IND / f"{iid}.csv"
        rows = list(csv.reader(open(path, encoding="utf-8")))
        head, body = rows[0], rows[1:]
        keys = [r[0] for r in body]
        for k in periods_after(keys[-1], s["freq"], today):
            body.append([k] + [""] * (len(head) - 1))
            keys.append(k)
        filled = []
        for col, cs in (s.get("columns") or {}).items():
            if col not in head:
                print(f"{iid}: 열이 없다 {col}")
                continue
            j = head.index(col)
            for r in body:
                if r[j] in ("", None) and r[0] >= "2026-01-01":
                    try:
                        v = value(cs, r[0])
                    except Exception as e:
                        print(f"{iid} {col} {r[0]}: 못 받음 ({type(e).__name__})")
                        v = None
                    if v is not None:
                        r[j] = f"{v:.2f}"
                        filled.append(f"{r[0]} {col}={v:.2f}")
        # 끝에 붙인 줄이 다 비었으면 내지 않는다
        while body and all(x in ("", None) for x in body[-1][1:]):
            body.pop()
        if filled:
            print(f"{iid}: " + ", ".join(filled))
            if not dry:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f, lineterminator="\n")
                    w.writerow(head)
                    w.writerows(body)
        else:
            print(f"{iid}: 새로 채울 값 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
