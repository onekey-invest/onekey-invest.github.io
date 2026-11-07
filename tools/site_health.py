"""사이트 점검(총괄): 구역마다 자료가 제때 갱신되는지, 최근에 누가 무엇을 올렸는지 한 장으로 적는다.

매일 실행이 사이트를 만든 뒤 돌린다. 걸린 것이 있으면 저장소에 "사이트 점검" 할 일(이슈) 하나를 열거나 고쳐 쓰고,
다 괜찮아지면 닫는다(.github/workflows/daily.yml). 총괄 세션은 일을 시작할 때 이것을 먼저 돌린다.

실행: python tools/site_health.py              결과를 화면에, .health/health.md에 적는다(공개하지 않음)
      python tools/site_health.py --days 7     최근 올라온 것을 며칠 치 볼지
종료 코드는 늘 0이다(배포를 막지 않는다). 걸린 수는 .health/health_count.txt.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
LAG = 3          # 거래일 기준으로 이만큼 넘게 늦으면 걸린다


def last_date(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        return date.fromisoformat(rows[-1][0][:10]) if len(rows) > 1 else None
    except Exception:
        return None


def bdays_between(a: date, b: date) -> int:
    """a 다음 날부터 b까지의 평일 수(주말 제외. 공휴일은 따로 빼지 않는다)."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def expected_close(now: datetime) -> date:
    """장이 끝난 마지막 평일(16시 전이면 그 전 평일)."""
    d = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def recent_commits(days):
    try:
        out = subprocess.run(["git", "log", f"--since={days} days ago", "--format=%h\t%ad\t%an\t%s", "--date=format:%m-%d %H:%M", "--name-only"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    except Exception:
        return []
    items, cur = [], None
    for line in out.splitlines():
        if "\t" in line:
            h, d, a, s = line.split("\t", 3)
            cur = {"h": h, "d": d, "a": a, "s": s, "files": []}
            items.append(cur)
        elif line.strip() and cur:
            cur["files"].append(line.strip())
    auto = ("시세 갱신", "그림 갱신", "마켓노트 20", "그림 원본 갱신")
    return [c for c in items if not c["s"].startswith(auto)]


def area_of(files):
    m = {"content/reports": "리포트", "data/companies.yaml": "기업", "data/industries.yaml": "산업", "content/notes": "마켓노트",
         "content/studies": "연구", "content/books": "책 검증", "data/books": "책 검증", "data/strategies.yaml": "가상운용",
         "data/trades": "가상운용", "data/strategy_books": "가상운용", "data/scorecard.csv": "채점표", "data/ledger.csv": "의견 장부",
         "templates": "화면 틀", "static/style.css": "화면 틀", "build.py": "화면 틀", ".github": "자동 실행", "tools": "도구",
         "charts_src": "그림 원본", "content/pages": "소개·안내"}
    got = []
    for f in files:
        for k, v in m.items():
            if f.startswith(k) and v not in got:
                got.append(v)
    return got or ["그 밖"]


def main(argv):
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 7
    now = datetime.now(KST)
    want = expected_close(now)
    site = yaml.safe_load((ROOT / "data" / "site.yaml").read_text(encoding="utf-8"))
    companies = yaml.safe_load((ROOT / "data" / "companies.yaml").read_text(encoding="utf-8"))
    strategies = yaml.safe_load((ROOT / "data" / "strategies.yaml").read_text(encoding="utf-8")) or []
    issues, ok = [], []

    # 1. 시세
    for c in companies:
        d = last_date(ROOT / "data" / "prices" / f"{c['id']}.csv")
        if d is None or bdays_between(d, want) > LAG:
            issues.append(f"시세: {c['name']}의 종가가 {d}에서 멈춤 (data/sources.yaml에 있는지, 받기가 실패하는지)")
    kospi = last_date(ROOT / "data" / "prices" / "KOSPI.csv")
    ok.append(f"시세 기준(KOSPI) {kospi}")

    # 2. 가상운용: 운용 중인 전략이 드는 자산의 시세(장부 평가값)가 이어지는가
    for s in strategies:
        if s.get("status") != "운용 중":
            continue
        tp = ROOT / "data" / "trades" / f"{s['id']}.csv"
        assets = set()
        if tp.exists():
            with open(tp, encoding="utf-8") as f:
                assets = {r["asset"] for r in csv.DictReader(f)}
        ends = [(a, last_date(ROOT / "data" / "prices" / f"{a}.csv")) for a in assets if (ROOT / "data" / "prices" / f"{a}.csv").exists()]
        stale = [(a, d) for a, d in ends if d is None or bdays_between(d, want) > LAG]
        if stale:
            a, d = stale[0]
            issues.append(f"가상운용: {s['name']}({s['id']})의 평가가 {d}에서 멈춤 — 자산 '{a}'. 이 전략을 만든 쪽의 갱신 작업을 돌려야 한다")
    # 2-1. 미국 공시 전략: 사이트 평가(야후)와 운용 쪽 ver5 지수(Alpaca)의 누적 차이(운용 쪽이 달마다 적는 CHECK.json)
    chk = ROOT / "data" / "strategy_books" / "us" / "CHECK.json"
    if chk.exists():
        c = json.loads(chk.read_text(encoding="utf-8"))
        if float(c.get("max_diff", 0)) > 0.001:
            issues.append(f"가상운용: 미국 공시 전략의 사이트 평가와 운용 쪽 지수의 누적 차이 {float(c['max_diff']) * 100:.2f}% (0.1% 넘음, {c.get('date')}) — 종가 출처 차이를 본다")
    # 3. 마켓노트: 평일 09:30 뒤면 오늘 노트가 있어야
    notes = sorted(p.stem for p in (ROOT / "content" / "notes").glob("*.md"))
    last_note = date.fromisoformat(notes[-1]) if notes else None
    today = now.date()
    if today.weekday() < 5 and (now.hour, now.minute) >= (9, 30) and last_note != today:
        issues.append(f"마켓노트: 오늘({today}) 노트가 없음 (마지막 {last_note})")
    else:
        ok.append(f"마켓노트 마지막 {last_note}")
    # 4. 공시
    for c in companies:
        p = ROOT / "data" / "disclosures" / f"{c['id']}.json"
        if not p.exists():
            issues.append(f"공시: {c['name']} 목록이 없음")
            continue
        a = json.loads(p.read_text(encoding="utf-8")).get("asof")
        if a and bdays_between(date.fromisoformat(a), today) > LAG:
            issues.append(f"공시: {c['name']} 목록이 {a}에서 멈춤")
    # 5. 그림(서버가 그린 것)
    man = ROOT / "static" / "charts" / "manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        for c in companies:
            a = (m.get(f"company-{c['id']}") or {}).get("asof")
            if not a:
                issues.append(f"그림: {c['name']} 주가 그림이 없음")
            elif kospi and bdays_between(date.fromisoformat(a), kospi) > LAG:
                issues.append(f"그림: {c['name']} 주가 그림이 {a}에서 멈춤")
    dr = ROOT / "static" / "charts" / "_draw.json"
    if dr.exists():
        r = json.loads(dr.read_text(encoding="utf-8"))
        for cid in r.get("skipped", []):
            issues.append(f"그림: '{cid}'의 시트가 그림 원본 엑셀에 없음 — PC에서 09_사이트그림/daily_charts.ps1을 한 번 돌린다")
        for x in r.get("failed", []):
            issues.append(f"그림: 서버가 못 그림 — {x}")
    # 6. 채점 대기
    todo = ROOT / "dist" / "score_todo.txt"
    if todo.exists():
        for line in todo.read_text(encoding="utf-8").splitlines():
            if line.strip():
                issues.append(f"채점 대기: {line.split(' https')[0]}")

    # 7. 산업 핵심 지표: 열마다 마지막 값이 나와 있어야 할 기간보다 늦으면(분기: 분기 끝 + 75일, 월: 달 끝 + 45일)
    import csv as _csv
    src_path = ROOT / "data" / "indicator_sources.yaml"
    auto_cols = (yaml.safe_load(src_path.read_text(encoding="utf-8")) or {}) if src_path.exists() else {}
    for p in sorted((ROOT / "data" / "indicators").glob("*.csv")):
        rows = list(_csv.reader(open(p, encoding="utf-8")))
        if len(rows) < 3:
            continue
        head, body = rows[0], rows[1:]
        d0, d1 = date.fromisoformat(body[-2][0]), date.fromisoformat(body[-1][0])
        months = 3 if (d1.year - d0.year) * 12 + d1.month - d0.month >= 3 else 1
        lag = 75 if months == 3 else 45
        for j, col in enumerate(head[1:], start=1):
            last = max((r[0] for r in body if len(r) > j and r[j] not in ("", None)), default=None)
            if not last:
                continue
            ld = date.fromisoformat(last)
            nm = date(ld.year + (ld.month // 12), ld.month % 12 + 1, 1)          # 그 기간이 끝난 다음 날
            ny, nmm = (nm.year, nm.month + months - 1)
            ny, nmm = ny + (nmm - 1) // 12, (nmm - 1) % 12 + 1
            next_end = date(ny + (nmm // 12), nmm % 12 + 1, 1)                     # 다음 기간이 끝난 다음 날
            if (now.date() - next_end).days > lag:
                how = "자동(출처가 아직 안 냄)" if col in ((auto_cols.get(p.stem) or {}).get("columns") or {}) else "손으로 채우는 열 — 산업 모델 담당"
                issues.append(f"산업 지표: {p.stem} '{col}'이 {last}에서 멈춤 ({how})")

    commits = recent_commits(days)
    lines = [f"# 사이트 점검 {now:%Y-%m-%d %H:%M} (한국 시간)", "",
             f"## 걸린 것 {len(issues)}건", ""] + ([f"- {x}" for x in issues] or ["- 없음"]) + \
            ["", "## 정상", ""] + [f"- {x}" for x in ok] + \
            ["", f"## 최근 {days}일에 올라온 것(자동 갱신 제외) {len(commits)}건", ""] + \
            [f"- {c['d']} `{c['h']}` [{', '.join(area_of(c['files']))}] {c['s']}" for c in commits[:40]]
    text = "\n".join(lines) + "\n"
    print(text)
    out = ROOT / ".health"          # 공개 폴더(dist) 밖에 둔다(내부 경로가 들어 있다)
    out.mkdir(exist_ok=True)
    (out / "health.md").write_text(text, encoding="utf-8")
    (out / "health_count.txt").write_text(str(len(issues)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
