"""편 폴더의 img/ 사진을 한 장에 모아 눈으로 확인하게 한다.

실행: python tools/photo_sheet.py 편/2026-10-05_환율
결과: img/확인.png (사진을 나란히 붙인 그림)과 사진마다 크기·방향·걸린 점

기계가 볼 수 있는 것(크기, 형식)만 여기서 거른다.
주제와 맞는지, 얼굴·상표가 있는지는 확인.png를 눈으로 보고 판단한다 (매뉴얼 1부 4번).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

MIN_W = 1080          # 카드 가로. 이보다 좁으면 늘려야 해서 흐려진다
THUMB_W = 360


def main(folder: Path) -> int:
    img = folder / "img"
    files = sorted(p for p in img.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.stem != "확인")
    if not files:
        print("img 폴더에 사진이 없다")
        return 1
    bad, thumbs = 0, []
    for p in files:
        im = Image.open(p)
        w, h = im.size
        way = "세로" if h > w else "가로"
        notes = []
        if w < MIN_W:
            notes.append(f"가로가 {w}px이다. {MIN_W}px 이상이어야 한다")
            bad += 1
        if way == "가로":
            notes.append("가로 사진이다. 표지에 쓰면 위쪽 3분의 2에만 깔린다")
        print(f"{p.name}: {w}x{h} {way}, {p.stat().st_size // 1024}KB" + ("".join(" / " + n for n in notes)))
        t = im.convert("RGB")
        t = t.resize((THUMB_W, int(h * THUMB_W / w)))
        thumbs.append(t.crop((0, 0, THUMB_W, min(t.height, 540))))
    gap = 12
    sheet = Image.new("RGB", (len(thumbs) * (THUMB_W + gap) + gap, 540 + 2 * gap), "#222222")
    for k, t in enumerate(thumbs):
        sheet.paste(t, (gap + k * (THUMB_W + gap), gap))
    out = img / "확인.png"
    sheet.save(out)
    print(f"눈으로 볼 그림 → {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve()))
