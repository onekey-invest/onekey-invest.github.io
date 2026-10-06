"""빌드할 때 SVG 차트를 만든다. 브라우저에서 따로 실행되는 코드는 없다.

규칙은 DESIGN.md 4절을 따른다: 주가는 남색 실선, 벤치마크는 주황 실선,
목표주가는 빨강 점선 계단, 의견 변경은 빨강 마름모.
"""
from __future__ import annotations

import math
from bisect import bisect_right

W, H = 520, 262
X0, X1, Y0, Y1 = 46, 476, 20, 220
FONT = 'font-family="Pretendard Variable, Malgun Gothic, sans-serif"'


def _nice_ticks(lo: float, hi: float, target: int = 4):
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    start = math.floor(lo / step) * step
    # 맨 위 눈금이 최댓값을 덮을 때까지 올린다
    ticks = [round(start, 6)]
    while ticks[-1] < hi:
        ticks.append(round(ticks[-1] + step, 6))
    return ticks


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


def company_chart(price, bench=None, targets=(), markers=()) -> str:
    """price, bench: [(날짜, 종가)]. targets: [(날짜, 목표주가)]. markers: [(날짜, 설명)].

    벤치마크는 차트 첫날의 주가에 맞춰 환산해 겹쳐 그린다.
    """
    if len(price) < 2:
        return ""
    dates = [d for d, _ in price]
    base = price[0][1]
    n = len(dates)

    def xi(d):
        i = max(0, min(n - 1, bisect_right(dates, d) - 1))
        return X0 + (X1 - X0) * i / (n - 1)

    bench_pts = []
    if bench:
        b0 = next((c for d, c in bench if d >= dates[0]), None)
        if b0:
            bench_pts = [(d, c / b0 * base) for d, c in bench if dates[0] <= d <= dates[-1]]

    values = [c for _, c in price] + [c for _, c in bench_pts] + [t for _, t in targets]
    ticks = _nice_ticks(min(values), max(values))
    lo, hi = ticks[0], ticks[-1]

    def yv(v):
        return Y1 - (Y1 - Y0) * (v - lo) / (hi - lo)

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="주가, 목표주가, 벤치마크 비교 차트">']

    out.append('<g stroke="#e3e5e9" stroke-width="1">')
    for t in ticks[1:]:
        out.append(f'<line x1="{X0}" y1="{yv(t):.1f}" x2="{X1}" y2="{yv(t):.1f}"/>')
    out.append("</g>")
    out.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#333"/>')
    out.append(f'<line x1="{X0}" y1="{Y0}" x2="{X0}" y2="{Y1}" stroke="#bbb"/>')
    out.append(f'<line x1="{X1}" y1="{Y0}" x2="{X1}" y2="{Y1}" stroke="#bbb"/>')

    out.append(f'<g font-size="10.5" fill="#555" {FONT}>')
    out.append(f'<text x="{X0 - 4}" y="12" text-anchor="end">[원]</text>')
    out.append(f'<text x="{X1 + 4}" y="12">[%]</text>')
    for t in ticks:
        y = yv(t) + 4
        out.append(f'<text x="{X0 - 4}" y="{y:.1f}" text-anchor="end">{_fmt(t)}</text>')
        out.append(f'<text x="{X1 + 4}" y="{y:.1f}">{(t / base - 1) * 100:+.0f}</text>')
    # 가로축: 석 달 간격으로 그 달의 첫 거래일
    seen, labels = set(), []
    for d in dates:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            labels.append(d)
    step = max(1, math.ceil(len(labels) / 5))
    for d in labels[::step]:
        out.append(f'<text x="{xi(d):.1f}" y="{Y1 + 16}" text-anchor="middle">{d:%Y/%m}</text>')
    out.append("</g>")

    if targets:
        pts, prev = [], None
        for d, t in targets:
            x = xi(max(d, dates[0]))
            if prev is not None:
                pts.append(f"{x:.1f},{yv(prev):.1f}")
            pts.append(f"{x:.1f},{yv(t):.1f}")
            prev = t
        pts.append(f"{X1},{yv(prev):.1f}")
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#0f766e" stroke-width="1.4" stroke-dasharray="5 3"/>')

    if bench_pts:
        pts = " ".join(f"{xi(d):.1f},{yv(c):.1f}" for d, c in bench_pts)
        out.append(f'<polyline points="{pts}" fill="none" stroke="#98a2b3" stroke-width="1.4"/>')

    pts = " ".join(f"{xi(d):.1f},{yv(c):.1f}" for d, c in price)
    out.append(f'<polyline points="{pts}" fill="none" stroke="#1f2a44" stroke-width="2" stroke-linejoin="round"/>')

    closes = dict(price)
    label_parts = []
    for i, (d, text) in enumerate(markers):
        i_d = max(0, min(n - 1, bisect_right(dates, d) - 1))
        x, y = xi(d), yv(closes[dates[i_d]])
        out.append(f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" fill="#0f766e" transform="rotate(45 {x:.1f} {y:.1f})"/>')
        right_side = x > X0 + (X1 - X0) * 0.6
        tx = x - 8 if right_side else x + 8
        anchor = ' text-anchor="end"' if right_side else ""
        ty = y + 18 if i == 0 else y - 9
        label_parts.append(f'<text x="{tx:.1f}" y="{ty:.1f}"{anchor}>{text}</text>')
    if label_parts:
        # 선 위에 겹쳐도 읽히도록 글자 둘레를 흰색으로 두른다
        out.append(
            f'<g font-size="10.5" fill="#333" stroke="#fff" stroke-width="3" paint-order="stroke" {FONT}>'
            f'{"".join(label_parts)}</g>'
        )

    out.append("</svg>")
    return "".join(out)


def sparkline(values, color="#1f2a44", w=96, h=26) -> str:
    """표 안에 넣는 작은 추이선. 축과 눈금 없이 선과 마지막 점만 그린다."""
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    n = len(values)
    pts = [(2 + (w - 6) * i / (n - 1), 3 + (h - 6) * (1 - (v - lo) / span)) for i, v in enumerate(values)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="추이">'
        f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.2" fill="{color}"/></svg>'
    )


def pct_chart(lines, vline=None) -> str:
    """누적수익률 차트. 세로축은 %.

    lines: [{"points": [(날짜, 수익률 소수)], "color": "#...", "width": 2, "dash": "4 3" 또는 None}]
    vline: (날짜, 설명). 그 날짜에 세로선을 긋는다(운용 개시일 표시용).
    """
    lines = [ln for ln in lines if len(ln["points"]) >= 2]
    if not lines:
        return ""
    dates = sorted({d for ln in lines for d, _ in ln["points"]})
    n = len(dates)

    def xi(d):
        i = max(0, min(n - 1, bisect_right(dates, d) - 1))
        return X0 + (X1 - X0) * i / (n - 1)

    values = [v * 100 for ln in lines for _, v in ln["points"]] + [0.0]
    ticks = _nice_ticks(min(values), max(values))
    lo, hi = ticks[0], ticks[-1]

    def yv(v):
        return Y1 - (Y1 - Y0) * (v - lo) / (hi - lo)

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="누적수익률 차트">']
    out.append('<g stroke="#e3e5e9" stroke-width="1">')
    for t in ticks:
        if t != lo:
            out.append(f'<line x1="{X0}" y1="{yv(t):.1f}" x2="{X1}" y2="{yv(t):.1f}"/>')
    out.append("</g>")
    if lo < 0 < hi:
        out.append(f'<line x1="{X0}" y1="{yv(0):.1f}" x2="{X1}" y2="{yv(0):.1f}" stroke="#999"/>')
    out.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#333"/>')
    out.append(f'<line x1="{X0}" y1="{Y0}" x2="{X0}" y2="{Y1}" stroke="#bbb"/>')
    out.append(f'<line x1="{X1}" y1="{Y0}" x2="{X1}" y2="{Y1}" stroke="#bbb"/>')

    out.append(f'<g font-size="10.5" fill="#555" {FONT}>')
    out.append(f'<text x="{X0 - 4}" y="12" text-anchor="end">[%]</text>')
    for t in ticks:
        label = f"{t:+.0f}" if float(t).is_integer() else f"{t:+.1f}"
        out.append(f'<text x="{X0 - 4}" y="{yv(t) + 4:.1f}" text-anchor="end">{label if t else "0"}</text>')
    seen, labels = set(), []
    for d in dates:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            labels.append(d)
    step = max(1, math.ceil(len(labels) / 5))
    for d in labels[::step]:
        out.append(f'<text x="{xi(d):.1f}" y="{Y1 + 16}" text-anchor="middle">{d:%Y/%m}</text>')
    out.append("</g>")

    if vline:
        x = xi(vline[0])
        out.append(f'<line x1="{x:.1f}" y1="{Y0}" x2="{x:.1f}" y2="{Y1}" stroke="#888" stroke-dasharray="2 2"/>')
        right_side = x > X0 + (X1 - X0) * 0.6
        tx = x - 5 if right_side else x + 5
        anchor = ' text-anchor="end"' if right_side else ""
        out.append(
            f'<text x="{tx:.1f}" y="{Y0 + 11}" font-size="10.5" fill="#333" stroke="#fff" stroke-width="3" '
            f'paint-order="stroke" {FONT}{anchor}>{vline[1]}</text>'
        )

    for ln in lines:
        pts = " ".join(f"{xi(d):.1f},{yv(v * 100):.1f}" for d, v in ln["points"])
        dash = f' stroke-dasharray="{ln["dash"]}"' if ln.get("dash") else ""
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{ln["color"]}" '
            f'stroke-width="{ln.get("width", 2)}" stroke-linejoin="round"{dash}/>'
        )

    out.append("</svg>")
    return "".join(out)


PIE_COLORS = ["#0f766e", "#1f2a44", "#5fa8a0", "#475467", "#b5d9d4", "#0b5c56", "#98a2b3", "#2d8f85", "#344054", "#cfe8e4"]
PIE_REST = "#e4e7ec"
_DARK = {"#0f766e", "#1f2a44", "#475467", "#0b5c56", "#2d8f85", "#344054"}


def pie_colors(parts) -> list[str]:
    """조각마다 쓸 색. '그 밖'(rest)은 옅은 회색, 나머지는 순서대로."""
    out, k = [], 0
    for p in parts:
        if p.get("rest"):
            out.append(PIE_REST)
        else:
            out.append(PIE_COLORS[k % len(PIE_COLORS)])
            k += 1
    return out


def pie_chart(parts, center_note: str = "") -> str:
    """점유율 원그래프. parts = [{name, pct, rest?}], pct의 합은 100.

    12시에서 시작해 시계 방향으로 돈다. 큰 조각(8% 이상)과 '그 밖'은 조각 안에 이름과 %를 쓰고,
    작은 조각은 원 밖 옆줄에 이름과 %를 쓰고 선으로 잇는다(오른쪽 반은 오른쪽 줄, 왼쪽 반은 왼쪽 줄).
    """
    total = sum(p["pct"] for p in parts)
    if not parts or total <= 0:
        return ""
    colors = pie_colors(parts)
    r, gap, row = 118, 22, 21
    slices, a0 = [], 0.0
    for p, col in zip(parts, colors):
        a1 = a0 + p["pct"] / total * 360
        slices.append({**p, "a0": a0, "a1": a1, "mid": (a0 + a1) / 2, "color": col})
        a0 = a1
    inside = [s for s in slices if s.get("rest") or s["pct"] / total >= 0.08]
    outside = [s for s in slices if s not in inside]
    right = [s for s in outside if s["mid"] < 180]
    left = sorted([s for s in outside if s["mid"] >= 180], key=lambda s: -s["mid"])   # 왼쪽은 위에서 아래로
    lab_w = 150
    w = (lab_w if left else 14) + 2 * r + gap + (lab_w if right else 14)
    cx = (lab_w if left else 14) + r
    need = max(len(right), len(left)) * row + 24
    h = max(2 * r + 28, need)
    cy = h / 2

    def pt(angle, radius):
        t = math.radians(angle)
        return cx + radius * math.sin(t), cy - radius * math.cos(t)

    o = [f'<svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="점유율 원그래프" {FONT} style="width:100%;max-width:{w:.0f}px;height:auto;display:block">']
    for s in slices:
        if s["a1"] - s["a0"] >= 359.999:
            o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{s["color"]}"/>')
            continue
        (x0, y0), (x1, y1) = pt(s["a0"], r), pt(s["a1"], r)
        big = 1 if s["a1"] - s["a0"] > 180 else 0
        o.append(f'<path d="M{cx:.1f},{cy:.1f} L{x0:.1f},{y0:.1f} A{r},{r} 0 {big} 1 {x1:.1f},{y1:.1f} Z" fill="{s["color"]}" stroke="#fff" stroke-width="1.2"><title>{s["name"]} {s["pct"]}%</title></path>')
    for s in inside:
        x, y = pt(s["mid"], r * (0.5 if s["a1"] - s["a0"] > 120 else 0.62))
        ink = "#fff" if s["color"] in _DARK else "#344054"
        o.append(f'<text x="{x:.1f}" y="{y - 3:.1f}" text-anchor="middle" font-size="12.5" fill="{ink}">{s["name"]}</text>')
        o.append(f'<text x="{x:.1f}" y="{y + 14:.1f}" text-anchor="middle" font-size="15" font-weight="700" fill="{ink}">{s["pct"]}%</text>')
    for side, group in (("r", right), ("l", left)):
        if not group:
            continue
        top = cy - (len(group) - 1) * row / 2
        for k, s in enumerate(group):
            ly = top + k * row
            px, py = pt(s["mid"], r + 3)
            if side == "r":
                ex, tx, anchor = cx + r + gap - 6, cx + r + gap, "start"
            else:
                ex, tx, anchor = cx - r - gap + 6, cx - r - gap, "end"
            o.append(f'<polyline points="{px:.1f},{py:.1f} {ex:.1f},{ly:.1f} {tx - (3 if side == "r" else -3):.1f},{ly:.1f}" fill="none" stroke="#98a2b3" stroke-width="0.8"/>')
            o.append(f'<text x="{tx:.1f}" y="{ly + 4:.1f}" text-anchor="{anchor}" font-size="12.5" fill="#344054">{s["name"]} <tspan font-weight="700" fill="#111827">{s["pct"]}%</tspan></text>')
    if center_note:
        o.append(f'<text x="{cx:.1f}" y="{h - 4:.1f}" text-anchor="middle" font-size="11" fill="#98a2b3">{center_note}</text>')
    o.append("</svg>")
    return "".join(o)

