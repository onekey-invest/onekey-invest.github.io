"""아침 브리핑 글([0]~[7] 구획)을 마켓노트 원고로 바꾼다.

머리말은 [7. 짧은 노트]에서, 본문은 [1]~[4]에서, 최종 요약은 [5]에서 가져온다.
내 코멘트는 채우지 않고, 만든 원고는 draft: true(공개 전)로 둔다.
"""
from __future__ import annotations

import re
from datetime import date

import yaml

# 구획 번호와 제목의 앞머리. 본문 속 번호 목록("1. ...")과 헷갈리지 않게 둘 다 맞아야 구획으로 본다
HEADS = {0: "오늘의 한 줄", 1: "통합 브리핑", 2: "오늘의 시장", 3: "기업", 4: "오늘 예정", 5: "최종 요약",
         6: "PDF", 7: "짧은 노트", 8: "검증 기록"}
HEAD_RE = re.compile(r"^[\s#*\[]*(\d)\.\s*(.+?)[\]\*\s]*$")
SOURCE_RE = re.compile(r"\s*\[출처:[^\]]*\]")
SUB_RE = re.compile(r"^[\s#*]*([A-F])\.\s+(.+?)[\s*]*$")
ISSUE_RE = re.compile(r"^\s*\d+\)\s+\S")
BULLET_RE =re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+")
DATE_RE = re.compile(r"(20\d\d)[-.\s]+(\d{1,2})[-.\s]+(\d{1,2})")

SHORT_KEYS = ("날짜", "오늘의 한 줄", "지표", "핵심 3가지", "내 종목·산업", "오늘 일정", "어제 확인한 것",
              "확인할 것", "내 코멘트", "태그")
LIST_KEYS = ("지표", "핵심 3가지", "내 종목·산업", "오늘 일정")
EMPTY = ("", "-", "–", "없음", "해당 없음", "(작성 필요)")


def split_sections(text: str) -> dict[int, str]:
    """글을 구획 번호별로 자른다."""
    out, num, buf = {}, None, []
    for line in text.splitlines():
        m = HEAD_RE.match(line)
        # [0]~[5]는 번호와 제목이 다 맞아야 한다. 뒤의 짧은 노트·검증 기록은 번호가 밀릴 수 있어 제목만 본다
        hit = next((k for k, v in HEADS.items()
                    if m and m.group(2).startswith(v) and (k >= 7 or k == int(m.group(1)))), None)
        if hit is not None and len(line) < 60:
            if num is not None:
                out[num] = "\n".join(buf).strip()
            num, buf = hit, []
        elif num is not None:
            buf.append(line)
    if num is not None:
        out[num] = "\n".join(buf).strip()
    return out


def _item(line: str) -> str:
    return BULLET_RE.sub("", line).strip()


def parse_short(text: str) -> dict:
    """[7. 짧은 노트]의 '이름: 값' 줄과 그 아래 목록을 읽는다."""
    out, key = {}, None
    for raw in text.splitlines():
        line = raw.strip().strip("`")
        if not line:
            continue
        if line.startswith("(제안)"):
            out["제안"] = line[4:].strip()
            key = None
            continue
        hit = next((k for k in SHORT_KEYS if re.match(rf"^[\s*]*{re.escape(k)}[\s*]*:", line)), None)
        if hit:
            key = hit
            value = line.split(":", 1)[1].strip().strip("*").strip()
            out[key] = ([_item(value)] if value not in EMPTY else []) if key in LIST_KEYS else value
        elif key in LIST_KEYS:
            if _item(line) not in EMPTY:
                out[key].append(_item(line))
        elif key:
            out[key] = (out[key] + " " + line).strip()
    return out


def _indicator(line: str) -> dict:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"지표 줄은 '이름 | 값 | 변동' 꼴이어야 한다: {line}")
    return {"name": parts[0], "value": parts[1], "change": parts[2]}


def _body(text: str, subheads: bool = False) -> str:
    """본문 구획. 마켓노트는 '## '로 구획을 자르므로 그보다 큰 제목은 낮춘다."""
    lines = []
    for line in text.splitlines():
        line = SOURCE_RE.sub("", line)                    # 출처 표시는 공개 본문에 내보내지 않는다
        if not line.strip() and lines and not lines[-1].strip():
            continue
        m = SUB_RE.match(line) if subheads else None
        if m and len(line) < 60:
            lines.append(f"### {m.group(1)}. {m.group(2)}")
        elif line.lstrip().startswith("#"):
            lines.append("#### " + line.lstrip().lstrip("#").strip())
        elif ISSUE_RE.match(line):
            lines += ["", f"**{line.strip()}**", ""]      # '1) 이슈 제목'은 굵게, 앞뒤를 띄운다
        elif BULLET_RE.match(line) and lines and lines[-1].strip() and not BULLET_RE.match(lines[-1]):
            lines += ["", line]                           # 목록 앞에 빈 줄이 없으면 한 문단으로 붙는다
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _summary(text: str) -> list[str]:
    """최종 요약. '제목' 줄 다음에 문단이 오는 꼴이면 '제목: 문단'으로 합친다."""
    items, out = [_item(x) for x in text.splitlines() if _item(x)], []
    for x in items:
        if out and out[-1].startswith("오늘 ") and ":" not in out[-1] and len(out[-1]) < 25:
            out[-1] = f"{out[-1]}: {x}"
        else:
            out.append(x)
    return out


def to_note(text: str, day: date | None = None) -> tuple[date, str]:
    """브리핑 글 → (날짜, 마켓노트 원고)."""
    sec = split_sections(text)
    if 7 not in sec:
        raise ValueError("[7. 짧은 노트] 구획이 없다. 양식의 7번까지 출력된 브리핑인지 확인한다")
    short = parse_short(sec[7])

    if day is None:
        m = DATE_RE.search(short.get("날짜", ""))
        if not m:
            raise ValueError("짧은 노트에 '날짜: YYYY-MM-DD'가 없다. --date로 날짜를 준다")
        day = date(*map(int, m.groups()))

    headline = short.get("오늘의 한 줄") or sec.get(0, "").strip()
    if not headline:
        raise ValueError("오늘의 한 줄이 없다")

    review = short.get("어제 확인한 것", "")
    tags = [t.strip() for t in re.split(r"[,，]", short.get("태그", "")) if t.strip() not in EMPTY]
    front = {
        "date": day,
        "draft": True,
        "headline": headline.splitlines()[0].strip(),
        "indicators": [_indicator(x) for x in short.get("지표", [])],
        "comment": "",
        "comment_suggestion": short.get("제안", ""),
        "points": short.get("핵심 3가지", []),
        "watch": short.get("내 종목·산업", []),
        "review": "" if review in EMPTY else review,
        "summary": _summary(sec.get(5, "")),
        "companies": [],
        "industries": [],
        "tags": tags,
        "week": short.get("오늘 일정", []),
    }
    parts = []
    for num, title, sub in ((1, "통합 브리핑", True), (2, "오늘의 시장 지도", False),
                            (3, "기업·산업 Watch", False), (4, "오늘 예정 이벤트", False)):
        if sec.get(num):
            parts.append(f"## {title}\n\n{_body(sec[num], sub)}")
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000)
    return day, f"---\n{head}---\n\n" + "\n\n".join(parts) + "\n"
