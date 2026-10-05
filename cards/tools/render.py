"""카드뉴스 deck.html을 장마다 PNG(1080x1350)로 뽑고 점검한다.

실행: python tools/render.py 편/2026-10-05_환율
      python tools/render.py 편/2026-10-05_환율 --jpg   (인스타에 올릴 JPG도 만든다)
결과: 그 폴더에 01.png, 02.png, ... 와 한눈에 보는 모음.png
      --jpg를 주면 올릴것/01.jpg, ...
점검: 장수, 크기, 넘침, 사진·글꼴이 떴는지. 문제가 있으면 적어 주고 종료 코드 1로 끝난다.

크롬 찾기: 환경 변수 CARD_CHROME → PATH의 chrome/chromium/edge → 윈도 기본 설치 위치 순서.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

W, H = 1080, 1350
MAX_SLIDES = 10  # 인스타 API로 올릴 때 한 게시물의 한도. 지금은 넘어도 막지 않고 알려만 준다
NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge")
WINDOWS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def browser() -> str:
    env = os.environ.get("CARD_CHROME")
    if env and Path(env).exists():
        return env
    for name in NAMES:
        found = shutil.which(name)
        if found:
            return found
    for b in WINDOWS:
        if Path(b).exists():
            return b
    sys.exit("크롬이나 엣지를 찾지 못했다. CARD_CHROME에 실행 파일 경로를 적어 준다")


def chrome(exe: str, profile: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([
        exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
        "--force-device-scale-factor=1", f"--window-size={W},{H}",
        "--virtual-time-budget=8000", f"--user-data-dir={profile}", *args,
    ], check=True, capture_output=True, timeout=180)


def render(folder: Path) -> list[Path]:
    deck = folder / "deck.html"
    count = len(re.findall(r'<section class="slide', deck.read_text(encoding="utf-8")))
    exe, out = browser(), []
    with tempfile.TemporaryDirectory() as profile:
        for i in range(1, count + 1):
            png = folder / f"{i:02d}.png"
            chrome(exe, profile, f"--screenshot={png}", f"{deck.as_uri()}?s={i}")
            size = Image.open(png).size
            if size != (W, H):
                raise SystemExit(f"{png.name}: 크기가 {size}다. {W}x{H}이어야 한다")
            out.append(png)
    # 장수가 줄어 남은 옛 그림은 지우지 않고 옮겨 둔다
    for old in sorted(folder.glob("[0-9][0-9].png")):
        if int(old.stem) > count:
            keep = folder / "지난것"
            keep.mkdir(exist_ok=True)
            old.replace(keep / old.name)
    return out


def check(folder: Path) -> tuple[list[str], list[str]]:
    """deck.js의 점검 결과를 읽는다. (걸린 것, 알아 둘 것)을 돌려준다. 걸린 것이 없으면 통과다."""
    deck = folder / "deck.html"
    with tempfile.TemporaryDirectory() as profile:
        dom = chrome(browser(), profile, "--dump-dom", f"{deck.as_uri()}?check=1").stdout.decode("utf-8", "replace")
    m = re.search(r'<pre id="__check">(.*?)</pre>', dom, re.S)
    if not m:
        return ["점검 스크립트가 없다. deck.html 끝에서 tools/deck.js를 부르는지 본다"], []
    data = json.loads(html.unescape(m.group(1)))
    problems, notes = [], []
    if data["count"] > MAX_SLIDES:
        notes.append(f"장수가 {data['count']}장이다. 인스타 API로 올리려면 {MAX_SLIDES}장까지다")
    if not data["font"]:
        problems.append("글꼴(Pretendard)이 뜨지 않았다. 다른 글꼴로 뽑혔다")
    for s in data["slides"]:
        for b in s["bad"]:
            problems.append(f"{s['n']:02d}번 장: {b}")
    return problems, notes


def sheet(pngs: list[Path], path: Path, cols: int = 4, scale: float = 0.36) -> None:
    """모든 장을 한 장에 줄여 붙인다. 휴대폰에서 보이는 크기와 비슷하다."""
    w, h, gap = int(W * scale), int(H * scale), 16
    rows = -(-len(pngs) // cols)
    canvas = Image.new("RGB", (cols * w + (cols + 1) * gap, rows * h + (rows + 1) * gap), "#9aa0aa")
    for k, p in enumerate(pngs):
        im = Image.open(p).convert("RGB").resize((w, h), Image.LANCZOS)
        canvas.paste(im, (gap + (k % cols) * (w + gap), gap + (k // cols) * (h + gap)))
    canvas.save(path)


def to_jpg(pngs: list[Path], folder: Path) -> None:
    """인스타 API는 JPG만 받는다."""
    out = folder / "올릴것"
    out.mkdir(exist_ok=True)
    for p in pngs:
        Image.open(p).convert("RGB").save(out / (p.stem + ".jpg"), "JPEG", quality=92, optimize=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folder = Path(args[0]).resolve()
    pngs = render(folder)
    sheet(pngs, folder / "모음.png")
    if "--jpg" in sys.argv:
        to_jpg(pngs, folder)
    print(f"{len(pngs)}장 → {folder}")
    problems, notes = check(folder)
    for n in notes:
        print("알아 둘 것:", n)
    if problems:
        print("점검에서 걸린 것:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("점검 통과")
