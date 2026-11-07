"""의견 장부(data/ledger.csv)에 새 의견을 자동으로 덧붙인다(매일 실행).

content/reports/의 기업 리포트 머리말(회사·의견·목표주가·리포트 id)을 읽어,
장부에 같은 (기업, 리포트 id, 의견, 목표주가) 줄이 없으면 끝에 한 줄을 붙인다.
- 새 리포트를 올렸을 때, 같은 리포트의 의견·목표주가를 고쳐 다시 올렸을 때 모두 걸린다.
- 지난 줄은 고치지도 지우지도 않는다(리포트를 내려도 장부 줄은 남는다).
- 브리프는 같은 날 같은 의견의 정식 보고서가 있으면 붙이지 않는다(ledger_from_git.py와 같은 규칙).
- at은 장부에 처음 들어간 시각(한국 시간): 그 리포트 파일이 저장소에 처음 들어온 커밋 시각, 없으면 지금.

실행: python tools/ledger_append.py
"""
from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
LEDGER = ROOT / "data" / "ledger.csv"
FIELDS = ["at", "date", "company", "rating", "target", "report_id", "kind"]


def front(text):
    if not text.startswith("---"):
        return None
    try:
        return yaml.safe_load(text.split("---", 2)[1])
    except Exception:
        return None


def last_commit_time(path: Path):
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(ROOT))], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        return datetime.fromtimestamp(int(out), KST) if out else None
    except Exception:
        return None


def main():
    companies = {c["id"] for c in yaml.safe_load((ROOT / "data" / "companies.yaml").read_text(encoding="utf-8"))}
    rows = list(csv.DictReader(open(LEDGER, encoding="utf-8"))) if LEDGER.exists() else []
    have = {(r["company"], r["report_id"], r["rating"], str(int(float(r["target"])))) for r in rows}
    reps = []
    for p in sorted((ROOT / "content" / "reports").glob("*.md")):
        f = front(p.read_text(encoding="utf-8"))
        if not f or f.get("company") not in companies or not f.get("rating") or not f.get("target"):
            continue
        reps.append((p, f))
    full = {(f["company"], str(f["date"]), f["rating"], int(f["target"])) for _, f in reps if f.get("kind") != "브리프"}
    new = []
    for p, f in reps:
        key = (f["company"], f["id"], f["rating"], str(int(f["target"])))
        if key in have:
            continue
        if f.get("kind") == "브리프" and (f["company"], str(f["date"]), f["rating"], int(f["target"])) in full:
            continue
        at = last_commit_time(p) or datetime.now(KST)
        new.append({"at": at.strftime("%Y-%m-%d %H:%M"), "date": str(f["date"]), "company": f["company"],
                    "rating": f["rating"], "target": int(f["target"]), "report_id": f["id"], "kind": f.get("kind", "")})
    if not new:
        print(f"장부: 새 의견 없음({len(rows)}줄)")
        return 0
    new.sort(key=lambda e: (e["at"], e["company"]))
    write_header = not LEDGER.exists()
    with open(LEDGER, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(new)
    for e in new:
        print(f"장부에 덧붙임: {e['company']} {e['rating']} {e['target']:,} ({e['report_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
