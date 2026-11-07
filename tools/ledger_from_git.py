"""의견 장부(data/ledger.csv)를 깃 기록에서 처음 한 번 채운다.

사이트에는 기업마다 최신 판 하나만 남기므로, 내린 리포트와 고쳐 쓴 의견·목표주가는 깃 기록에만 있다.
이 스크립트는 content/reports/의 기업 리포트 파일마다 바뀐 기록을 따라가며
의견이나 목표주가가 달라진 때를 모두 찾아 장부에 적는다.

  at        그 의견이 사이트 저장소에 처음 들어간 시각(한국 시간)
  date      리포트 머리말의 발행일
  company   기업 id
  rating    투자의견
  target    목표주가
  report_id 리포트 id
  kind      리포트 구분(최초·업데이트·브리프)

브리프는 같은 날 정식 보고서와 의견이 같으므로 장부에서 뺀다(정식 보고서가 없는 날만 남긴다).
뒤로는 리포트를 올릴 때 장부에 한 줄을 덧붙인다. 지난 줄은 고치지 않는다.

실행: python tools/ledger_from_git.py   (저장소 기록이 전부 있어야 한다: git fetch --unshallow)
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


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def front(text):
    if not text.startswith("---"):
        return None
    try:
        return yaml.safe_load(text.split("---", 2)[1])
    except Exception:
        return None


def main():
    companies = {c["id"] for c in yaml.safe_load((ROOT / "data" / "companies.yaml").read_text(encoding="utf-8"))}
    paths = sorted({p for p in git("log", "--no-renames", "--name-only", "--format=", "--", "content/reports").split("\n") if p.endswith(".md")})
    events = []
    for p in paths:
        prev = None
        log = git("log", "--no-renames", "--reverse", "--format=%H %ct", "--", p).split("\n")
        for line in filter(None, log):
            h, ts = line.split()
            try:
                text = git("show", f"{h}:{p}")
            except subprocess.CalledProcessError:
                prev = None          # 이 커밋에서 지워졌다
                continue
            f = front(text)
            if not f or f.get("company") not in companies or not f.get("rating"):
                continue
            state = (f["rating"], int(f["target"]))
            if state != prev:
                at = datetime.fromtimestamp(int(ts), KST)
                events.append({"at": at.strftime("%Y-%m-%d %H:%M"), "date": str(f["date"]), "company": f["company"],
                               "rating": state[0], "target": state[1], "report_id": f["id"], "kind": f.get("kind", "")})
                prev = state
    # 브리프는 같은 시각의 정식 보고서와 겹치면 뺀다
    full = {(e["company"], e["date"], e["rating"], e["target"]) for e in events if e["kind"] != "브리프"}
    events = [e for e in events if e["kind"] != "브리프" or (e["company"], e["date"], e["rating"], e["target"]) not in full]
    events.sort(key=lambda e: (e["at"], e["company"]))
    out = ROOT / "data" / "ledger.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0]))
        w.writeheader()
        w.writerows(events)
    print(f"장부 {len(events)}줄 → {out}")


if __name__ == "__main__":
    sys.exit(main())
