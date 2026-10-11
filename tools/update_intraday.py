"""가상운용 ETF 전략이 드는 ETF와 벤치마크의 장중 가격을 받아 data/intraday.json에 적는다.

출처: 네이버 증권의 시세 조회(polling.finance.naver.com). 사이트 주인이 허락받은 범위에서 쓴다(2026-10-12).
한 번 돌 때 요청은 둘이다(ETF 묶음 하나, 지수 하나). 장중 갱신 워크플로가 평일 장중 5분마다 돌린다.
받지 못하면 기존 파일을 그대로 두고 오류로 끝난다(워크플로에서는 이 단계가 실패해도 화면은 다시 만든다).
이 값은 화면의 "장중 평가"에만 쓴다. 거래 기록과 성과는 일별 종가(data/prices)로 계산한다.

실행:  python tools/update_intraday.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://polling.finance.naver.com/api/realtime/domestic"
OUT = ROOT / "data" / "intraday.json"
INDEX_CODES = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (onekey-invest site updater)"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))


def parse(payload):
    """네이버 응답 → {코드: (가격, 체결 시각, 장 상태)}"""
    out = {}
    for x in payload.get("datas", []):
        price = float(str(x["closePrice"]).replace(",", ""))
        out[str(x["itemCode"])] = (price, x.get("localTradedAt", ""), x.get("marketStatus", ""))
    return out


def targets():
    """auto가 적힌 운용 중 전략이 드는 자산 가운데 국내 종목(야후 기호가 .KS/.KQ로 끝나는 것)의 {이름: 6자리 코드}와 벤치마크 이름들."""
    sources = yaml.safe_load((ROOT / "data" / "sources.yaml").read_text(encoding="utf-8")) or {}
    strategies = yaml.safe_load((ROOT / "data" / "strategies.yaml").read_text(encoding="utf-8")) or []
    names, benches = {}, set()
    for s in strategies:
        if not s.get("auto") or s.get("status") != "운용 중":
            continue
        benches.add(s["benchmark"])
        for a in s["auto"]["weights"]:
            sym = str((sources.get(a) or {}).get("symbol", ""))
            if sym.endswith((".KS", ".KQ")):
                names[a] = sym[:6]
    return names, sorted(b for b in benches if b in INDEX_CODES)


def main():
    names, benches = targets()
    if not names:
        print("장중 가격을 받을 전략이 없다")
        return
    stocks = parse(get(f"{BASE}/stock/{','.join(sorted(set(names.values())))}"))
    prices, times, status = {}, [], set()
    for name, code in names.items():
        if code not in stocks:
            sys.exit(f"{name}({code}): 응답에 없다. 기존 파일을 그대로 둔다")
        prices[name] = stocks[code][0]
        times.append(stocks[code][1])
        status.add(stocks[code][2])
    bench = {}
    for b in benches:
        got = parse(get(f"{BASE}/index/{INDEX_CODES[b]}"))
        if INDEX_CODES[b] in got:
            bench[b] = got[INDEX_CODES[b]][0]
    out = {"asof": max(times), "status": "OPEN" if "OPEN" in status else "CLOSE", "source": "네이버 증권", "prices": prices, "bench": bench}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"장중 가격 {len(prices)}개, 기준 {out['asof']}, 장 {out['status']}")


if __name__ == "__main__":
    main()
