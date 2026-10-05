"""다음 편에 쓸 바탕색을 알려 준다. 가장 오래 안 쓴 색을 먼저 권한다.

실행: python tools/theme.py
결과: 색마다 마지막으로 쓴 편과, 권하는 색 하나

색 목록은 tools/card.css에 있다. t-amber와 t-night는 모든 장에 dark를 붙여 쓴다.
여럿이 같은 시간에 만들 때는 이 도구로 고르지 않는다. 맡기는 쪽이 색을 정해 준다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

THEMES = {
    "(없음)": "회백 + 청록",
    "t-white": "흰색 + 청록",
    "t-beige": "베이지 + 주황",
    "t-moss": "옅은 올리브 + 이끼색",
    "t-violet": "연보라 + 보라",
    "t-amber": "어두운 바탕 + 호박색 (모든 장 dark)",
    "t-night": "남색 바탕 + 민트 (모든 장 dark)",
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "편"
    last: dict[str, str] = {}
    for deck in sorted(root.glob("*/deck.html")):
        m = re.search(r'<body(?: class="([^"]*)")?', deck.read_text(encoding="utf-8"))
        name = (m.group(1) or "").strip() if m else ""
        last[name if name in THEMES else "(없음)" if not name else name] = deck.parent.name
    order = sorted(THEMES, key=lambda t: last.get(t, ""))
    for t in order:
        print(f'{t:10s} {THEMES[t]:32s} 마지막: {last.get(t, "아직 안 씀")}')
    for extra in sorted(set(last) - set(THEMES)):
        print(f'{extra:10s} (목록에 없는 색) 마지막: {last[extra]}')
    print(f"권하는 색: {order[0]}")


if __name__ == "__main__":
    sys.exit(main())
