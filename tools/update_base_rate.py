"""한국은행 기준금리 변경 내역을 받아 data/rates/bok_base_rate.csv에 저장한다.

출처: 한국은행 누리집 "한국은행 기준금리 추이" 표(https://www.bok.or.kr/portal/singl/baseRate/list.do).
받지 못하거나 표를 읽지 못하면 기존 파일을 그대로 두고 오류로 끝난다(매일 갱신에서는 이 단계가 실패해도 계속 간다).
새로 받은 내역이 기존 파일보다 짧으면(표가 잘렸을 때) 덮어쓰지 않는다.

실행:  python tools/update_base_rate.py
"""
from __future__ import annotations

import csv
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.bok.or.kr/portal/singl/baseRate/list.do?dataSeCd=01&menuNo=200643"
OUT = ROOT / "data" / "rates" / "bok_base_rate.csv"
ROW = re.compile(r"<td[^>]*>\s*(\d{4})\s*</td>\s*<td[^>]*>\s*(\d{1,2})월\s*(\d{1,2})일\s*</td>\s*<td[^>]*>\s*([\d.]+)\s*</td>")


def parse(html: str):
    rows = {date(int(y), int(m), int(d)): float(r) for y, m, d, r in ROW.findall(html)}
    return sorted(rows.items())


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (onekey-invest site updater)"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    rows = parse(html)
    if len(rows) < 20:
        sys.exit(f"기준금리 표를 읽지 못했다(행 {len(rows)}개). 기존 파일을 그대로 둔다")
    old = 0
    if OUT.exists():
        with open(OUT, encoding="utf-8") as f:
            old = sum(1 for _ in csv.DictReader(f))
    if len(rows) < old:
        sys.exit(f"받은 내역({len(rows)}행)이 기존({old}행)보다 짧다. 덮어쓰지 않는다")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "rate"])
        for d, r in rows:
            w.writerow([d.isoformat(), f"{r:.2f}"])
    print(f"기준금리 {len(rows)}행, {rows[0][0]} ~ {rows[-1][0]}, 지금 {rows[-1][1]:.2f}%")


if __name__ == "__main__":
    main()
