"""카드뉴스 deck.html을 장마다 PNG(1080x1350)로 뽑고 점검한다.

실행: python tools/render.py 편/2026-10-05_환율
      python tools/render.py 편/2026-10-05_환율 --jpg   (인스타에 올릴 JPG도 만든다)
      python tools/render.py 편/2026-10-05_환율 --jpg --font   (글꼴 파일이 없으면 먼저 받아 둔다)
결과: 그 폴더에 01.png, 02.png, ... 와 한눈에 보는 모음.png
      --jpg를 주면 올릴것/01.jpg, ...
점검: 장수, 크기, 넘침, 사진·글꼴이 떴는지. 문제가 있으면 적어 주고 종료 코드 1로 끝난다.

크롬 찾기: 환경 변수 CARD_CHROME → PATH의 chrome/chromium/edge → 윈도 기본 설치 위치
          → 플레이라이트가 깔아 둔 크로미엄(/opt/pw-browsers, ~/.cache/ms-playwright) 순서.
글꼴: tools/fonts/PretendardVariable.woff2가 있으면 그 파일로, 없으면 인터넷 주소의 글꼴로 뽑는다.
      클라우드에서는 크롬이 인터넷 글꼴을 못 가져온다(2026-10-05 시험). 그래서 클라우드에서는 --font를 준다.
      --font는 파일이 없을 때만 글꼴 공식 배포 주소에서 한 번 받는다(약 2MB). 환경 변수 CARD_FETCH_FONT=1도 같다.
창 높이: 크롬에 따라 보이는 칸이 창보다 낮게 잡힌다(클라우드에서 87px 낮았다).
        그래서 창을 넉넉히 높게 띄우고 위에서 1350px만 잘라 낸다.
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

import glob

from PIL import Image

W, H = 1080, 1350
SLACK = 300  # 창을 이만큼 더 높게 띄운 뒤 잘라 낸다
MAX_SLIDES = 10  # 인스타 API로 올릴 때 한 게시물의 한도. 지금은 넘어도 막지 않고 알려만 준다
NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge")
FONT_FILE = Path(__file__).resolve().parent / "fonts" / "PretendardVariable.woff2"
FONT_URL = ("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9"
            "/packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2")
WINDOWS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def fetch_font() -> None:
    """글꼴 파일이 없으면 받아 둔다. 크롬이 인터넷에 못 나가는 곳에서도 같은 글꼴로 뽑으려는 것이다."""
    if FONT_FILE.exists():
        return
    import urllib.request
    try:
        with urllib.request.urlopen(FONT_URL, timeout=60) as r:
            data = r.read()
    except Exception as e:  # 못 받아도 멈추지 않는다. 점검이 글꼴을 따로 본다
        print(f"알아 둘 것: 글꼴 파일을 받지 못했다 ({e})")
        return
    if data[:4] != b"wOF2" or len(data) < 1_000_000:
        print("알아 둘 것: 받은 글꼴 파일이 글꼴이 아니다. 쓰지 않는다")
        return
    FONT_FILE.parent.mkdir(exist_ok=True)
    FONT_FILE.write_bytes(data)
    print(f"글꼴 파일을 받아 두었다 → {FONT_FILE} ({len(data) // 1024}KB)")


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
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux/chrome")):
        found = sorted(glob.glob(pat))
        if found:
            return found[-1]
    sys.exit("크롬이나 엣지를 찾지 못했다. CARD_CHROME에 실행 파일 경로를 적어 준다")


def chrome(exe: str, profile: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([
        exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
        "--force-device-scale-factor=1", f"--window-size={W},{H + SLACK}",
        "--allow-file-access-from-files", "--virtual-time-budget=8000", f"--user-data-dir={profile}", *args,
    ], check=True, capture_output=True, timeout=180)


def render(folder: Path) -> list[Path]:
    deck = folder / "deck.html"
    count = len(re.findall(r'<section class="slide', deck.read_text(encoding="utf-8")))
    exe, out = browser(), []
    with tempfile.TemporaryDirectory() as profile:
        for i in range(1, count + 1):
            png = folder / f"{i:02d}.png"
            chrome(exe, profile, f"--screenshot={png}", f"{deck.as_uri()}?s={i}")
            shot = Image.open(png)
            if shot.size[0] != W or shot.size[1] < H:
                raise SystemExit(f"{png.name}: 찍힌 크기가 {shot.size}다. 가로 {W}, 세로 {H} 이상이어야 한다")
            shot.crop((0, 0, W, H)).save(png)
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
        problems.append("글꼴(Pretendard)이 뜨지 않았다. 다른 글꼴로 뽑혔다. --font를 주고 다시 뽑는다")
    else:
        notes.append("글꼴은 받아 둔 파일로 뽑았다" if data.get("fontFrom") == "file" else "글꼴은 인터넷 주소에서 불러왔다")
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
    if "--font" in sys.argv or os.environ.get("CARD_FETCH_FONT"):
        fetch_font()
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
