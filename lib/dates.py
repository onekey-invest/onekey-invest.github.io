"""마켓노트의 날짜 계산과 검사. 한국 시간이 기준이다.

자료 범위(오늘 온 메일), 미국 동부 시각 → 한국 시각 변환, 글 속 날짜·요일 대조, 일정 범위 검사를 맡는다.
외부 모듈 없이 돌아가야 한다. 예약 실행이 다른 것을 설치하기 전에 먼저 부른다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"
EVENT_END = time(7, 0)          # 일정은 대상 날짜 00:00부터 다음 날 07:00 전까지

_WD = f"[{WEEKDAYS}]"
MD_RE = re.compile(rf"(\d{{1,2}})(?:\.|월\s*)(\d{{1,2}})일?\s*\(({_WD})\)")
D_RE = re.compile(rf"(?<![\d.월])(?<!월 )(\d{{1,2}})일\s*\(({_WD})\)")
EVENT_RE = re.compile(rf"(\d{{1,2}})\.(\d{{1,2}})\(({_WD})\)\s*(\d{{1,2}}:\d{{2}}|[가-힣]+)?")


def parse_cutoff(text: str) -> time:
    h, m = text.strip().strip('"').split(":")
    return time(int(h), int(m))


def window(day: date, cutoff: time) -> tuple[datetime, datetime]:
    """오늘 자료의 범위. 대상 날짜 00:00부터 기준 시각까지(한국 시간)를 UTC로 돌려준다."""
    start = datetime.combine(day, time(0, 0), KST)
    end = datetime.combine(day, cutoff, KST)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def parse_utc(stamp: str) -> datetime:
    """메일의 date(예: 2026-10-04T21:42:16Z)를 읽는다. 시간대가 없으면 UTC로 본다."""
    dt = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def in_window(stamp: str, day: date, cutoff: time) -> bool:
    start, end = window(day, cutoff)
    return start <= parse_utc(stamp) <= end


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def us_dst(local: datetime) -> bool:
    """미국 동부가 서머타임인가. 3월 둘째 일요일 02:00부터 11월 첫째 일요일 02:00 전까지다."""
    start = datetime.combine(_nth_sunday(local.year, 3, 2), time(2, 0))
    end = datetime.combine(_nth_sunday(local.year, 11, 1), time(2, 0))
    return start <= local.replace(tzinfo=None) < end


def et_to_kst(local: datetime) -> datetime:
    """미국 동부 시각 → 한국 시각. 서머타임이면 13시간, 아니면 14시간을 더한다."""
    return local.replace(tzinfo=None) + timedelta(hours=13 if us_dst(local) else 14)


def label(d: date) -> str:
    return f"{d:%Y-%m-%d}({WEEKDAYS[d.weekday()]})"


def _nearest(day: date, month: int | None, dom: int) -> date | None:
    """연도(또는 달)가 없는 날짜를 대상 날짜에서 가장 가까운 날짜로 읽는다."""
    if month is None:
        firsts = [(day.replace(day=1) + timedelta(days=k)).replace(day=1) for k in (-1, 0, 31)]
        pairs = [(f.year, f.month) for f in firsts]
    else:
        pairs = [(day.year + k, month) for k in (-1, 0, 1)]
    found = []
    for y, m in pairs:
        try:
            found.append(date(y, m, dom))
        except ValueError:
            continue
    return min(found, key=lambda d: abs((d - day).days)) if found else None


def weekday_errors(text: str, day: date) -> list[str]:
    """글 속의 '10.05(월)', '10월 5일(월)', '6일(화)'가 달력의 요일과 맞는지 본다."""
    out = []
    hits = [(m.group(0), int(m.group(1)), int(m.group(2)), m.group(3)) for m in MD_RE.finditer(text)]
    hits += [(m.group(0), None, int(m.group(1)), m.group(2)) for m in D_RE.finditer(text)]
    for raw, month, dom, wd in hits:
        d = _nearest(day, month, dom)
        if d is None:
            out.append(f"'{raw}': 달력에 없는 날짜다")
        elif WEEKDAYS[d.weekday()] != wd:
            out.append(f"'{raw}': {d:%Y-%m-%d}은 {WEEKDAYS[d.weekday()]}요일이다")
    return list(dict.fromkeys(out))


def event_errors(lines: list[str], day: date) -> list[str]:
    """일정이 대상 날짜 00:00 ~ 다음 날 07:00(한국 시간) 안에 있는지 본다. 날짜가 없는 줄은 건너뛴다."""
    out = []
    for line in lines:
        m = EVENT_RE.search(line)
        if not m:
            continue
        d = _nearest(day, int(m.group(1)), int(m.group(2)))
        when = m.group(4) or ""
        if d == day:
            continue
        early = when == "새벽" or (":" in when and int(when.split(":")[0]) < EVENT_END.hour)
        if d != day + timedelta(days=1) or not early:
            out.append(f"'{line.strip()}': 대상 날짜({label(day)}) 일정이 아니다")
    return out
