"""만든 사이트(dist/)를 올리기 전에 점검한다. 하나라도 걸리면 오류로 끝난다(깃허브 실행이 멈추고 저장소 주인에게 메일이 간다).

1. 사이트 안 링크·그림 주소가 모두 열리는가(그림·PDF가 빈 파일이 아닌가)
2. 권유처럼 읽히는 말이 없는가(유사투자자문 경계). 고지 문장에 쓰는 "투자 권유가 아닙니다" 같은 부정형은 뺀다
3. 화면마다 설명문(description)이 있는가
4. 공개하면 안 되는 내부 폴더 이름이 새지 않았는가

실행: python tools/check_site.py            (dist/를 본다)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

PUSH = [r"지금\s*(사세요|매수하세요|파세요|매도하세요)", r"(매수|매도)\s*하세요", r"목표가\s*도달\s*알림", r"리딩\s*방",
        r"(수익|원금)\s*보장\s*(해\s*드|합니다|드립)", r"급등\s*(주|종목)\s*추천", r"(카톡|텔레그램|오픈채팅)\s*(방|문의)", r"손절가\s*(제공|알려)"]
INTERNAL = ["06_커버리지_후보", "05_분석프로세스", "내부_판단기록", "기업기록.md", "C:\\Users", "C:/Users"]


def main():
    if not DIST.exists():
        print("dist/가 없다. python build.py부터")
        return 2
    problems = []
    pages = [p for p in DIST.rglob("*.html")]
    for f in pages:
        html = f.read_text(encoding="utf-8")
        rel = f.relative_to(DIST).as_posix()
        if 'http-equiv="refresh"' in html:
            continue                     # 옛 주소에서 보내는 쪽
        body = re.sub(r"<script.*?</script>", "", html, flags=re.S)   # 스크립트 안의 글자열은 링크가 아니다
        for m in re.finditer(r'(?:href|src)="([^"#?]+)', body):
            u = m.group(1)
            if u.startswith(("http", "mailto", "data:", "//")):
                continue
            p = DIST / u.lstrip("/") if u.startswith("/") else (f.parent / u)
            p = Path(unquote(str(p)))
            if p.is_dir():
                p = p / "index.html"
            if not p.exists():
                problems.append(f"깨진 링크: {rel} → {u}")
            elif p.suffix.lower() in (".svg", ".png", ".jpg", ".pdf") and p.stat().st_size == 0:
                problems.append(f"빈 파일: {rel} → {u}")
        text = re.sub(r"<[^>]+>", " ", body)
        for pat in PUSH:
            for m in re.finditer(pat, text):
                around = text[max(0, m.start() - 12):m.end() + 12]
                if re.search(r"(않|없|아닙|금지|하지 않)", around):
                    continue
                problems.append(f"권유처럼 읽힘: {rel}: …{around.strip()}…")
        if rel != "404.html" and '<meta name="description" content=""' in html:
            problems.append(f"설명문 없음: {rel}")
        for w in INTERNAL:
            if w in text:
                problems.append(f"내부 이름: {rel}: {w}")
    for p in problems[:200]:
        print(p)
    print(f"화면 {len(pages)}개 점검, 걸린 것 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
