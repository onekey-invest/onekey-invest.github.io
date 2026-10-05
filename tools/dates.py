"""대상 날짜의 자료 범위·요일·시차를 계산해 보여 준다. 날짜를 암산하지 않으려고 쓴다.

실행: python tools/dates.py [2026-10-05] [--mail 2026-10-04T21:42:16Z ...] [--et "2026-10-07 14:00" ...]
날짜를 주지 않으면 지금의 한국 날짜다. --mail은 메일의 date(UTC)가 자료 범위 안인지, --et는 미국 동부 시각이
한국 시간으로 언제인지 알려 준다.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import dates as D  # noqa: E402


def read_config(key: str, pattern: str) -> str | None:
    """ops/routine.yaml의 값. 아직 아무것도 설치하지 않은 상태에서도 읽히도록 직접 찾는다."""
    text = (ROOT / "ops" / "routine.yaml").read_text(encoding="utf-8")
    m = re.search(rf'^{key}:\s*"?({pattern})', text, re.M)
    return m.group(1) if m else None


def default_day() -> date:
    """날짜를 주지 않았을 때의 대상 날짜. test 모드면 test_date, 아니면 지금의 한국 날짜다."""
    if read_config("mode", r"\w+") == "test" and read_config("test_date", r"\d{4}-\d\d-\d\d"):
        return date.fromisoformat(read_config("test_date", r"\d{4}-\d\d-\d\d"))
    return datetime.now(D.KST).date()


def main(argv=None):
    ap = argparse.ArgumentParser(description="마켓노트 날짜 계산")
    ap.add_argument("day", nargs="?", help="대상 날짜(YYYY-MM-DD). 없으면 지금의 한국 날짜")
    ap.add_argument("--cutoff", help="기준 시각(HH:MM). 없으면 ops/routine.yaml의 값")
    ap.add_argument("--mail", nargs="*", default=[], help="메일의 date(UTC)")
    ap.add_argument("--et", nargs="*", default=[], help='미국 동부 시각 "YYYY-MM-DD HH:MM"')
    a = ap.parse_args(argv)

    day = date.fromisoformat(a.day) if a.day else default_day()
    cutoff = D.parse_cutoff(a.cutoff or read_config("cutoff", r"\d{1,2}:\d{2}") or "08:30")
    start, end = D.window(day, cutoff)
    nxt = day + timedelta(days=1)
    gap = 13 if D.us_dst(datetime.combine(day, cutoff)) else 14

    print(f"대상 날짜: {D.label(day)}" + (" - 주말" if day.weekday() >= 5 else ""))
    print(f"전날: {D.label(day - timedelta(days=1))} / 다음 날: {D.label(nxt)}")
    print(f"자료 범위(한국 시간): {day:%m.%d} 00:00 ~ {cutoff:%H:%M}")
    print(f"자료 범위(UTC, 메일의 date와 비교): {start:%Y-%m-%dT%H:%M:%SZ} ~ {end:%Y-%m-%dT%H:%M:%SZ}")
    print(f"일정 범위(한국 시간): {day:%m.%d} 00:00 ~ {nxt:%m.%d} 07:00 전")
    print(f"미국 동부 시각 + {gap}시간 = 한국 시간")
    for stamp in a.mail:
        kst = D.parse_utc(stamp).astimezone(D.KST)
        verdict = "범위 안" if D.in_window(stamp, day, cutoff) else "범위 밖(쓰지 않는다)"
        print(f"메일 {stamp} → 한국 시간 {D.label(kst.date())} {kst:%H:%M} → {verdict}")
    for stamp in a.et:
        kst = D.et_to_kst(datetime.fromisoformat(stamp))
        print(f"미국 동부 {stamp} → 한국 시간 {D.label(kst.date())} {kst:%H:%M}")


if __name__ == "__main__":
    main()
