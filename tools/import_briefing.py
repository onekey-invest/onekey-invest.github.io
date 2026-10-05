"""아침 브리핑 글 파일을 마켓노트 원고(content/notes/날짜.md)로 바꾼다.

실행: python tools/import_briefing.py 브리핑.txt [--date 2026-10-05] [--force] [--draft]
만든 원고는 저장소에 올리면 바로 공개된다. --draft를 붙이면 공개 전(draft: true)으로 만든다.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.briefing import to_note  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="브리핑 글을 마켓노트 원고로 바꾼다")
    ap.add_argument("src", help="브리핑 글 파일(.txt, .md)")
    ap.add_argument("--date", help="날짜(YYYY-MM-DD). 없으면 짧은 노트의 날짜를 쓴다")
    ap.add_argument("--force", action="store_true", help="같은 날짜 원고가 있어도 덮어쓴다")
    ap.add_argument("--draft", action="store_true", help="공개 전 상태로 만든다")
    a = ap.parse_args(argv)

    text = Path(a.src).read_text(encoding="utf-8-sig")
    try:
        day, note = to_note(text, date.fromisoformat(a.date) if a.date else None, draft=a.draft)
    except ValueError as e:
        sys.exit(f"변환하지 않았다. {e}")
    out = ROOT / "content" / "notes" / f"{day:%Y-%m-%d}.md"
    if out.exists() and not a.force:
        sys.exit(f"{out.name}이 이미 있다. 같은 날짜 글을 덮어쓰지 않으려고 멈췄다. 덮어쓰려면 --force")
    out.write_text(note, encoding="utf-8")
    print(f"{out} 작성" + (" (공개 전)" if a.draft else ""))


if __name__ == "__main__":
    main()
