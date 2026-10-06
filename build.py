"""정적 사이트를 만든다.

실행: python build.py
결과: dist/ 폴더. 이 폴더를 그대로 호스팅에 올린다.

읽는 것: data/*.yaml, data/prices/*.csv, content/reports/*.md, content/pages/*.md
계산: lib/metrics.py   차트: lib/chart.py   화면 틀: templates/   규칙: DESIGN.md
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import metrics as M  # noqa: E402
from lib import portfolio as PF  # noqa: E402
from lib.chart import company_chart, pct_chart, sparkline  # noqa: E402

DIST = ROOT / "dist"


# ---------- 읽기 ----------

def load_yaml(name):
    with open(ROOT / "data" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prices():
    out = {}
    for path in sorted((ROOT / "data" / "prices").glob("*.csv")):
        dates, closes = [], []
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                dates.append(date.fromisoformat(row["date"]))
                closes.append(float(row["close"]))
        out[path.stem] = M.Series(tuple(dates), tuple(closes))
    return out


def md(text):
    return Markup(markdown.markdown(text, extensions=["tables"]))


def load_reports():
    reports = []
    for path in sorted((ROOT / "content" / "reports").glob("*.md")):
        r, body = split_front(path)
        for key in ("id", "date", "kind", "title"):
            if not r.get(key):
                raise ValueError(f"{path.name}: {key} 항목이 없다")
        if not (r.get("company") or r.get("industry")):
            raise ValueError(f"{path.name}: company 또는 industry 중 하나가 필요하다")
        if r.get("company") and not (r.get("rating") and r.get("target")):
            raise ValueError(f"{path.name}: 기업 리포트에는 rating과 target이 필요하다")
        r["body"] = md(body)
        r["path"] = f"reports/{r['id']}/"
        reports.append(r)
    ids = [r["id"] for r in reports]
    if len(ids) != len(set(ids)):
        raise ValueError("리포트 id가 겹친다")
    return sorted(reports, key=lambda r: (r["date"], r["id"]))


def load_trades(sid):
    path = ROOT / "data" / "trades" / f"{sid}.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [
            PF.Trade(date.fromisoformat(r["date"]), r["asset"], r["side"], float(r["qty"]), float(r["price"]), r.get("note", ""))
            for r in csv.DictReader(f)
        ]


def split_front(path):
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path.name}: 머리말(---)이 없다")
    _, front, body = raw.split("---", 2)
    return yaml.safe_load(front), body


def load_notes():
    """마켓노트. 본문은 '## 제목' 단위로 잘라 접는 구획으로 만든다.

    draft: true(공개 전)인 노트는 뺀다. 내 컴퓨터 미리보기(SITE_DRAFTS=1)에서만 보인다.
    """
    notes = []
    for path in sorted((ROOT / "content" / "notes").glob("*.md")):
        n, body = split_front(path)
        if n.get("draft") and os.environ.get("SITE_DRAFTS") != "1":
            continue
        for key in ("date", "headline"):
            if not n.get(key):
                raise ValueError(f"{path.name}: {key} 항목이 없다")
        sections, title, buf = [], None, []
        for line in body.splitlines():
            if line.startswith("## "):
                if title:
                    sections.append((title, md("\n".join(buf))))
                title, buf = line[3:].strip(), []
            else:
                buf.append(line)
        if title:
            sections.append((title, md("\n".join(buf))))
        n["sections"] = sections
        n["comment_html"] = md(n.get("comment") or "")
        n["path"] = f"notes/{n['date']:%Y-%m-%d}/"
        for ind in n.get("indicators") or []:
            ch = str(ind.get("change", "")).strip()
            ind["cls"] = "up" if ch.startswith("+") else "down" if ch.startswith(("-", "−")) else ""
        notes.append(n)
    dates = [n["date"] for n in notes]
    if len(dates) != len(set(dates)):
        raise ValueError("같은 날짜의 마켓노트가 둘 이상 있다")
    return sorted(notes, key=lambda n: n["date"], reverse=True)


def load_indicators(iid):
    """산업 핵심 지표. data/indicators/산업id.csv, 첫 열은 date, 나머지 열이 지표다."""
    path = ROOT / "data" / "indicators" / f"{iid}.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    names = [k for k in rows[0] if k != "date"] if rows else []
    return [
        (name, [(date.fromisoformat(r["date"]), float(r[name])) for r in rows if r[name] not in ("", None)])
        for name in names
    ]


def load_backtest(sid):
    path = ROOT / "data" / "backtests" / f"{sid}.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [(date.fromisoformat(r["date"]), float(r["value"])) for r in csv.DictReader(f)]


# ---------- 계산 ----------

CATEGORIES = [
    ("domestic", "국내 주식", "portfolios/"),
    ("overseas", "해외 주식", "portfolios/overseas/"),
    ("multi", "멀티에셋", "portfolios/multi/"),
]
INK, GREY, ACCENT = "#1f2a44", "#98a2b3", "#0f766e"
UP, DOWN = "#e0353b", "#2563eb"
LINE_COLORS = [INK, ACCENT, "#7c5cc4", "#c2410c"]   # 운용 중인 전략의 선 색
OFF_COLOR = "#b0b7c3"                               # 중단한 전략


def payload(fmt, series, markers=()):
    """브라우저의 차트(static/charts.js)가 읽는 자료. 화면 틀에서 <script type="application/json">에 넣는다."""
    data = {
        "format": fmt,
        "series": [
            {**{k: v for k, v in s.items() if k != "points"},
             "data": [[d.isoformat(), round(v, 4)] for d, v in s["points"]]}
            for s in series if len(s["points"]) >= 2
        ],
        "markers": [{"time": d.isoformat(), "text": t} for d, t in markers],
    }
    return Markup(json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def pct_points(points):
    return [(d, v * 100) for d, v in points]


def build_strategy(s, prices, bench_map, asof, comp_by_id):
    if s["category"] not in {c[0] for c in CATEGORIES}:
        raise ValueError(f"{s['id']}: 없는 category {s['category']}")
    bench = prices[bench_map[s["benchmark"]]]
    end = min(s.get("stopped") or asof, asof)
    calendar = [d for d in bench.dates if s["started"] <= d <= end]
    if not calendar:
        raise ValueError(f"{s['id']}: 운용 개시일 이후 거래일이 없다")
    trades = load_trades(s["id"])
    res = PF.run(s["initial"], trades, prices, calendar, s.get("commission", 0.0), s.get("sell_tax", 0.0))
    navs = [v for _, v in res["nav"]]
    ret = PF.total_return(res["nav"], s["initial"])
    bret = M.period_return(bench, calendar[0], end)

    def named(asset):
        c = comp_by_id.get(asset)
        return (c["name"], c["path"]) if c else (asset, None)

    holdings = []
    for h in res["holdings"]:
        name, path = named(h["asset"])
        holdings.append({**h, "name": name, "path": path})
    rate, tax = s.get("commission", 0.0), s.get("sell_tax", 0.0)
    trade_rows = []
    for t in reversed(trades):
        name, path = named(t.asset)
        fee = t.amount * rate + (t.amount * tax if t.side == PF.SELL else 0.0)
        trade_rows.append({"date": t.date, "name": name, "path": path, "side": t.side, "qty": t.qty,
                           "price": t.price, "amount": t.amount, "fee": fee, "note": t.note})

    live = [(d, v / s["initial"] - 1) for d, v in res["nav"]]
    b0 = bench.close_at(calendar[0])
    bench_line = [(d, bench.close_at(d) / b0 - 1) for d in calendar]
    bt = [(d, v) for d, v in load_backtest(s["id"]) if d <= calendar[0]]
    lines = []
    if len(bt) >= 2:
        lines.append({"points": [(d, v / bt[-1][1] - 1) for d, v in bt], "color": INK, "width": 1.6, "dash": "4 3"})
    lines.append({"points": bench_line, "color": GREY, "width": 1.4})
    lines.append({"points": live, "color": INK, "width": 2})
    series = []
    if len(bt) >= 2:
        series.append({"name": "백테스트", "type": "line", "color": INK, "dash": True,
                       "points": pct_points([(d, v / bt[-1][1] - 1) for d, v in bt])})
    series.append({"name": s["benchmark"], "type": "line", "color": GREY, "points": pct_points(bench_line)})
    series.append({"name": "운용 기록", "type": "area", "color": INK, "points": pct_points(live)})
    chart_data = payload("pct", series, [(calendar[0], "개시")] if len(bt) >= 2 else [])
    chart = pct_chart(lines, vline=(calendar[0], "운용 개시") if len(bt) >= 2 else None)

    return {
        **s,
        "path": f"strategies/{s['id']}/",
        "active": s["status"] == "운용 중",
        "end": end,
        "nav": res["nav"],
        "value": navs[-1],
        "cash": res["cash"],
        "cash_weight": res["cash_weight"],
        "ret": ret,
        "bench_ret": bret,
        "excess": M.excess(ret, bret),
        "mdd": PF.max_drawdown(navs),
        "sharpe": PF.sharpe(navs),
        "fees": res["fees"],
        "n_trades": res["n_trades"],
        "holdings": holdings,
        "trades": trade_rows,
        "live": live,
        "has_backtest": len(bt) >= 2,
        "chart": Markup(chart),
        "chart_data": chart_data,
        "spark": Markup(sparkline(navs, UP if (ret or 0) >= 0 else DOWN)),
        "rationale": md(s.get("rationale") or ""),
        "backtest": md(s.get("backtest") or ""),
        "log": md(s.get("log") or ""),
    }


def build_company(c, reports, prices, bench_map, asof):
    series = prices.get(c["id"])
    if series is None:
        raise ValueError(f"{c['id']}: data/prices/{c['id']}.csv가 없다")
    bench = prices[bench_map[c["benchmark"]]]
    reps = [r for r in reports if r.get("company") == c["id"]]
    if not reps:
        raise ValueError(f"{c['id']}: 리포트가 없다")
    first, latest = reps[0], reps[-1]

    last = series.close_at(asof)
    base = series.close_at(first["date"])
    ret = M.simple_return(base, last)
    bret = M.period_return(bench, first["date"], asof)

    change = None
    for prev, cur in zip(reps, reps[1:]):
        if cur["target"] != prev["target"] or cur["rating"] != prev["rating"]:
            change = {"prev": prev, "cur": cur}

    rows = []
    for r in reversed(reps):
        then = series.close_at(r["date"])
        rows.append({**r, "close": then, "after": M.simple_return(then, last)})

    targets, markers = [], []
    for i, r in enumerate(reps):
        changed = i == 0 or r["target"] != reps[i - 1]["target"] or r["rating"] != reps[i - 1]["rating"]
        if not changed:
            continue
        targets.append((r["date"], r["target"]))
        if i == 0:
            markers.append((r["date"], "개시"))
        elif r["rating"] != reps[i - 1]["rating"]:
            markers.append((r["date"], f"{r['rating']}, TP {r['target']:,.0f}"))
        else:
            markers.append((r["date"], f"TP {r['target']:,.0f}"))
    window = series.between(first["date"], asof)
    bwin = bench.between(first["date"], asof)
    if not len(window):
        # 첫 리포트를 그날 장이 끝나기 전(또는 휴장일)에 올리면 시세가 아직 발행일에 닿지 않는다.
        # 직전 종가 한 점에서 시작하고, 그날 종가가 들어오면 발행일부터 다시 그려진다.
        window = series.between(series.at(asof)[0], asof)
        bwin = bench.between(bench.at(asof)[0], asof)
    chart = company_chart(
        list(zip(window.dates, window.closes)),
        list(zip(bwin.dates, bwin.closes)),
        targets,
        markers,
    )

    marker_days = [(window.at(d)[0], t) for d, t in markers if window.at(d)]
    # 목표주가 선: 날짜를 시세가 있는 구간 안으로 맞추고, 같은 날짜가 겹치면 나중 값만 둔다(차트는 날짜가 겹치면 그리지 못한다)
    tp_by_day = {min(max(d, window.dates[0]), asof): t for d, t in targets}
    tp_by_day[asof] = targets[-1][1]
    tp_points = sorted(tp_by_day.items())
    b0 = bwin.closes[0] if len(bwin) else None
    chart_data = payload("price", [
        {"name": f"{c['benchmark']}(환산)", "type": "line", "color": GREY,
         "points": [(d, v / b0 * window.closes[0]) for d, v in zip(bwin.dates, bwin.closes)] if b0 else []},
        {"name": "목표주가", "type": "step", "color": ACCENT, "dash": True, "points": tp_points},
        {"name": c["name"], "type": "area", "color": INK, "points": list(zip(window.dates, window.closes))},
    ], marker_days)
    # 개시 기준가에서 목표주가까지 가는 길에서 지금 어디쯤인지 (0~100)
    span = latest["target"] - base if base else 0
    progress = max(0.0, min(1.0, (last - base) / span)) if span > 0 else None

    est = None
    e = c.get("estimates")
    if e:
        def per_share(vals):
            return [f"{last / v:.1f}" if v and v > 0 else "–" for v in vals]
        est = {
            "years": e["years"],
            "is_e": [str(y).endswith("E") for y in e["years"]],
            "rows": [
                ("매출액", [f"{v:,.0f}" for v in e["sales"]]),
                ("영업이익", [f"{v:,.0f}" for v in e["op"]]),
                ("영업이익률", [f"{o / s * 100:.1f}" if s else "–" for o, s in zip(e["op"], e["sales"])]),
                ("EPS", [f"{v:,.0f}" for v in e["eps"]]),
                ("PER", per_share(e["eps"])),
                ("PBR", per_share(e["bps"])),
                ("ROE", [f"{v:.1f}" for v in e["roe"]]),
            ],
        }

    return {
        **c,
        "path": f"companies/{c['id']}/",
        "reports": rows,
        "n_first": sum(1 for r in reps if r["kind"] == "최초"),
        "n_update": sum(1 for r in reps if r["kind"] not in ("최초", "브리프")),
        "n_brief": sum(1 for r in reps if r["kind"] == "브리프"),
        # 기업 화면 머리의 바로가기: 가장 최근의 기업 브리프와, 브리프가 아닌 가장 최근 리포트
        "brief": next((r for r in rows if r["kind"] == "브리프"), None),
        "full": next((r for r in rows if r["kind"] != "브리프"), None),
        "started": first["date"],
        "updated": latest["date"],
        "rating": latest["rating"],
        "target": latest["target"],
        "last": last,
        "base": base,
        "ret": ret,
        "bench_ret": bret,
        "excess": M.excess(ret, bret),
        "upside": M.upside(latest["target"], last),
        "r1m": M.period_return(series, M.months_before(asof, 1), asof),
        "r3m": M.period_return(series, M.months_before(asof, 3), asof),
        "r6m": M.period_return(series, M.months_before(asof, 6), asof),
        "change": change,
        "chart": Markup(chart),
        "chart_data": chart_data,
        "progress": progress,
        "spark": Markup(sparkline(window.closes, UP if (ret or 0) >= 0 else DOWN)),
        "est": est,
        "valuation": md(c.get("valuation") or ""),
        "risks": md(c.get("risks") or ""),
    }


def summarize(companies):
    ratings = {}
    for c in companies:
        ratings[c["rating"]] = ratings.get(c["rating"], 0) + 1
    return {
        "n": len(companies),
        "ratings": ratings,
        "avg_ret": M.mean(c["ret"] for c in companies),
        "avg_excess": M.mean(c["excess"] for c in companies),
        "n_beat": sum(1 for c in companies if c["excess"] is not None and c["excess"] > 0),
    }


# ---------- 표시 형식 ----------

def f_num(v):
    return "–" if v is None else f"{v:,.0f}"


def f_pct(v):
    return "–" if v is None else f"{v * 100:+.1f}%"


def f_pp(v):
    return "–" if v is None else f"{v * 100:+.1f}%p"


def f_sign(v):
    if v is None:
        return ""
    r = round(v * 100, 1)
    return "up" if r > 0 else "down" if r < 0 else ""


def f_ymd(d):
    return "–" if d is None else f"{d:%Y.%m.%d}"


def f_share(v):
    """비중. 부호 없이 표시한다."""
    return "–" if v is None else f"{v * 100:.1f}%"


def f_dec(v):
    return "–" if v is None else f"{v:.2f}"


def f_raw(v):
    """정렬용 숫자. 값이 없으면 빈 문자열."""
    return "" if v is None else f"{v:.6f}"


# ---------- 쓰기 ----------

def main():
    site = load_yaml("site.yaml")
    prices = load_prices()
    reports = load_reports()
    bench_map = site["benchmarks"]

    company_ids = {c["id"] for c in load_yaml("companies.yaml")}
    asof = min(s.last_date for name, s in prices.items() if name in company_ids or name in bench_map.values())

    industries_raw = load_yaml("industries.yaml")
    ind_by_id = {i["id"]: i for i in industries_raw}

    companies = []
    for c in load_yaml("companies.yaml"):
        for iid in c.get("industries", []):
            if iid not in ind_by_id:
                raise ValueError(f"{c['id']}: 없는 산업 {iid}")
        built = build_company(c, reports, prices, bench_map, asof)
        built["industry_objs"] = [ind_by_id[i] for i in c.get("industries", [])]
        companies.append(built)
    comp_by_id = {c["id"]: c for c in companies}

    industries = []
    for i in industries_raw:
        members = [c for c in companies if i["id"] in c.get("industries", [])]
        series = load_indicators(i["id"])
        ind_lines = [
            {"points": [(d, v / pts[0][1] - 1) for d, v in pts], "color": LINE_COLORS[k % len(LINE_COLORS)], "width": 2}
            for k, (name, pts) in enumerate(series) if len(pts) >= 2 and pts[0][1]
        ]
        industries.append({
            **i,
            "indicators": [
                {"name": name, "color": LINE_COLORS[k % len(LINE_COLORS)], "last": pts[-1][1], "last_date": pts[-1][0]}
                for k, (name, pts) in enumerate(series) if len(pts) >= 2 and pts[0][1]
            ],
            "indicator_chart": Markup(pct_chart(ind_lines)),
            "indicator_data": payload("pct", [
                {"name": name, "type": "line", "color": LINE_COLORS[k % len(LINE_COLORS)],
                 "points": [(d, (v / pts[0][1] - 1) * 100) for d, v in pts]}
                for k, (name, pts) in enumerate(series) if len(pts) >= 2 and pts[0][1]
            ]),
            "value_chain": md(i.get("value_chain") or ""),
            "path": f"industries/{i['id']}/",
            "members": members,
            "reports": [r for r in reversed(reports) if r.get("industry") == i["id"]],
            "avg_ret": M.mean(c["ret"] for c in members),
            "avg_excess": M.mean(c["excess"] for c in members),
        })
    for i in industries:
        ind_by_id[i["id"]].update(path=i["path"])

    all_reports = []
    for r in reversed(reports):
        row = dict(r)
        if r.get("company"):
            c = comp_by_id[r["company"]]
            mine = next(x for x in c["reports"] if x["id"] == r["id"])
            row.update(subject=c["name"], subject_path=c["path"], close=mine["close"], after=mine["after"])
        else:
            i = ind_by_id[r["industry"]]
            row.update(subject=i["name"], subject_path=f"industries/{i['id']}/", close=None, after=None)
        all_reports.append(row)

    strategies = []
    for s in load_yaml("strategies.yaml") or []:
        strategies.append(build_strategy(s, prices, bench_map, asof, comp_by_id))
    # 운용 중인 전략을 위에, 중단한 전략을 아래에 둔다
    strategies.sort(key=lambda s: (not s["active"], s["started"]))
    n_on = 0
    for s in strategies:
        if s["active"]:
            s["color"] = LINE_COLORS[n_on % len(LINE_COLORS)]
            n_on += 1
        else:
            s["color"] = OFF_COLOR
    for c in companies:
        c["held_by"] = [
            {"name": s["name"], "path": s["path"], "weight": h["weight"]}
            for s in strategies if s["active"]
            for h in s["holdings"] if h["asset"] == c["id"]
        ]

    notes = load_notes()
    for n in notes:
        for cid in n.get("companies") or []:
            if cid not in comp_by_id:
                raise ValueError(f"마켓노트 {n['date']}: 없는 기업 {cid}")
        for iid in n.get("industries") or []:
            if iid not in ind_by_id:
                raise ValueError(f"마켓노트 {n['date']}: 없는 산업 {iid}")
        n["company_objs"] = [comp_by_id[c] for c in n.get("companies") or []]
        n["industry_objs"] = [ind_by_id[i] for i in n.get("industries") or []]
    for c in companies:
        c["notes"] = [n for n in notes if c["id"] in (n.get("companies") or [])]
    for i in industries:
        i["notes"] = [n for n in notes if i["id"] in (n.get("industries") or [])]
    featured = [r for r in all_reports if r.get("featured")]

    # 내 컴퓨터 미리보기(serve.py)는 SITE_BASE_URL을 빈 값으로 넘겨 주소 앞머리를 뗀다
    base = os.environ.get("SITE_BASE_URL", site.get("base_url") or "").rstrip("/")
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(num=f_num, pct=f_pct, pp=f_pp, sign=f_sign, ymd=f_ymd, raw=f_raw, share=f_share, dec=f_dec)
    env.globals.update(
        site=site,
        asof=asof,
        url=lambda p="": f"{base}/{p}",
        built=datetime.now(),
        categories=CATEGORIES,
    )

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "static", DIST / "static")

    count = 0

    def write(path, template, **ctx):
        nonlocal count
        target = DIST / path / "index.html" if not path.endswith(".html") else DIST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(**ctx), encoding="utf-8")
        count += 1

    summary = summarize(companies)
    # 홈의 성적 막대: 가장 큰 절댓값을 막대 길이 50%로 삼는다
    top = max([abs(v) for c in companies for v in (c["ret"], c["bench_ret"]) if v is not None] or [1]) or 1   # 수익률이 모두 0이면 1로
    for c in companies:
        r, b = c["ret"] or 0, c["bench_ret"] or 0
        c["bar"] = {
            "left": 50 if r >= 0 else 50 - abs(r) / top * 50,
            "width": abs(r) / top * 50,
            "bench": 50 + b / top * 50,
        }

    write("", "home.html", nav="home", title="홈",
          companies=companies, reports=all_reports[:6], summary=summary, n_reports=len(all_reports),
          strategies=strategies, featured=featured[:3], notes=notes[:5])
    write("research", "research.html", nav="research", sub="companies", title="커버리지 성적표",
          companies=companies, summary=summary)
    write("research/industries", "industries.html", nav="research", sub="industries", title="산업",
          industries=industries)
    write("research/reports", "reports.html", nav="research", sub="reports", title="리포트 목록",
          reports=all_reports)

    for c in companies:
        write(c["path"], "company.html", nav="research", sub="companies", title=c["name"], c=c)
    for i in industries:
        write(i["path"], "industry.html", nav="research", sub="industries", title=i["name"], i=i)

    for r in all_reports:
        key = "company" if r.get("company") else "industry"
        siblings = [x for x in all_reports if x.get(key) == r[key]]  # 최신순
        idx = siblings.index(r)
        write(r["path"], "report.html", nav="research", sub="reports", title=r["title"], r=r,
              newer=siblings[idx - 1] if idx > 0 else None,
              older=siblings[idx + 1] if idx + 1 < len(siblings) else None)

    for name, title in (("methodology", "방법론"), ("about", "About")):
        body = md((ROOT / "content" / "pages" / f"{name}.md").read_text(encoding="utf-8"))
        write(name, "page.html", nav=name, title=title, body=body,
              featured=featured[:3] if name == "about" else [])

    for key, label, path in CATEGORIES:
        members = [s for s in strategies if s["category"] == key]
        chart = pct_chart([
            {"points": s["live"], "color": s["color"], "width": 2 if s["active"] else 1.4}
            for s in reversed(members)   # 운용 중인 전략의 선이 위에 오도록 나중에 그린다
        ])
        chart_data = payload("pct", [
            {"name": s["name"] + ("" if s["active"] else " (중단)"), "type": "line", "color": s["color"],
             "points": pct_points(s["live"])}
            for s in reversed(members)
        ])
        write(path, "portfolios.html", nav="portfolios", sub=key, title=f"가상운용 · {label}",
              label=label, strategies=members, chart=Markup(chart), chart_data=chart_data)
    for s in strategies:
        write(s["path"], "strategy.html", nav="portfolios", sub=s["category"], title=s["name"], s=s)

    write("notes", "notes.html", nav="notes", title="마켓노트", notes=notes)
    for k, n in enumerate(notes):   # notes는 최신순
        write(n["path"], "note.html", nav="notes", title=f"{n['date']:%Y.%m.%d} 마켓노트", n=n,
              description=n["headline"],
              newer=notes[k - 1] if k > 0 else None,
              older=notes[k + 1] if k + 1 < len(notes) else None)
    write("404.html", "soon.html", nav="", title="페이지를 찾을 수 없습니다", items=[])

    print(f"기준일 {asof:%Y-%m-%d} · 화면 {count}개 · 기업 {len(companies)} · 산업 {len(industries)} · "
          f"리포트 {len(all_reports)} · 전략 {len(strategies)} · 노트 {len(notes)} → {DIST}")


if __name__ == "__main__":
    main()
