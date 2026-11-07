"""채점표 실제 값 자동 채우기(매일 실행, 키 없이).

채점표 원본 scorecard_src/scorecard.xlsx('채점' 시트)에서 실제(H)가 빈 줄마다
  1) 항목의 분기("2026년 3분기 영업이익" → 2026-07-01 ~ 2026-09-30)를 읽고
  2) data/disclosures/<기업>.json에서 실적기간이 그 분기와 같고, 리포트 발행일 뒤에 나온
     '연결재무제표기준영업(잠정)실적' 공시(정정 아님)를 찾아
  3) DART 공개 화면 본문에서 영업이익 '당해실적'과 단위를 읽어 억원으로 바꿔
H(실제)·I(발표일)·J(출처)를 적고 K(확인 예정)를 비운다.
계산(오차·판정)은 하지 않는다. 통합 문서의 수식이 하고, tools/lo_scorecard.py(LibreOffice)가 다시 계산해 data/scorecard.csv로 낸다.

새 줄 자동 추가: 리포트 머리말에 score가 있으면(예)
    score: {item: "2026년 4분기 영업이익", mine: 21000, consensus: 23500, due: "2027년 1월 말"}
채점표에 (기업, 항목) 줄이 없을 때 한 줄을 더한다(수식은 make_scorecard.py와 같다). 컨센서스는 리포트에 적은 발행 때 값.

실행: python tools/score_actuals.py [--dry]
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from update_disclosures import fetch  # noqa: E402

WB = ROOT / "scorecard_src" / "scorecard.xlsx"
QEND = {1: ("01-01", "03-31"), 2: ("04-01", "06-30"), 3: ("07-01", "09-30"), 4: ("10-01", "12-31")}
UNIT = {"원": 1e-8, "천원": 1e-5, "백만원": 1e-2, "십억원": 10, "억원": 1, "조원": 1e4}
SOURCE = "영업(잠정)실적 공정공시, 연결(DART 공개 화면에서 자동으로 읽음)"


def quarter_of(item):
    m = re.search(r"(\d{4})년\s*([1-4])분기", str(item))
    if not m:
        return None
    y, q = int(m.group(1)), int(m.group(2))
    return [f"{y}-{QEND[q][0]}", f"{y}-{QEND[q][1]}"]


def doc_text(rcept_no):
    m = fetch(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}").decode("utf-8", "ignore")
    v = re.search(r'viewDoc\("(\d+)",\s*"(\d+)",\s*"(\d+)",\s*"(\d+)",\s*"(\d+)",\s*"([^"]+)"', m)
    if not v:
        return None
    r, d, e, o, l, dtd = v.groups()
    doc = fetch(f"https://dart.fss.or.kr/report/viewer.do?rcpNo={r}&dcmNo={d}&eleId={e}&offset={o}&length={l}&dtd={dtd}").decode("euc-kr", "ignore")
    doc = re.sub(r"(?is)<(style|script).*?</\1>", " ", doc)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", doc)))


def op_of(text):
    """본문에서 (영업이익 당해실적, 억원). 못 읽으면 None."""
    u = re.search(r"단위\s*[:：]\s*(조원|십억원|억원|백만원|천원|원)", text)
    m = re.search(r"영업이익\s*당해실적\s*(-?[\d,]+(?:\.\d+)?)", text)
    if not u or not m:
        return None
    return round(float(m.group(1).replace(",", "")) * UNIT[u.group(1)])


def find(cid, period, published):
    p = ROOT / "data" / "disclosures" / f"{cid}.json"
    if not p.exists():
        return None
    items = json.loads(p.read_text(encoding="utf-8"))["items"]
    cand = [x for x in items if x.get("kind") == "실적" and x.get("period") == period and not x.get("corrected")
            and "연결" in x.get("name", "") and x["date"] > published]
    return min(cand, key=lambda x: (x["date"], x.get("time", ""))) if cand else None


def formulas(ws, i):
    ws[f"L{i}"] = f'=IF(H{i}="","",ABS(F{i}/H{i}-1))'
    ws[f"M{i}"] = f'=IF(H{i}="","",ABS(G{i}/H{i}-1))'
    ws[f"N{i}"] = f'=IF(H{i}="","",(M{i}-L{i})*100)'
    ws[f"O{i}"] = (f'=IF(H{i}="","채점 전",IF(ABS(M{i}-L{i})<기준!$B$1,"비슷",'
                   f'IF(L{i}<M{i},"컨센서스보다 가까움","컨센서스가 더 가까움")))')
    ws[f"P{i}"] = f'=IF(OR(H{i}="",F{i}=G{i}),"",IF(SIGN(F{i}-G{i})=SIGN(H{i}-G{i}),"맞음","틀림"))'
    for col in "LM":
        ws[f"{col}{i}"].number_format = "0.0%"
    ws[f"N{i}"].number_format = "0.0"
    for col in "FGH":
        ws[f"{col}{i}"].number_format = "#,##0"


def relink(wb, n):
    """줄 수가 바뀌면 '요약'의 범위와 '내보내기' 시트를 다시 적는다(값이 아니라 수식)."""
    import re as _re
    last = n + 1
    for row in wb["요약"].iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.value = _re.sub(r"채점!([A-P])2:[A-P]\d+", lambda m: f"채점!{m.group(1)}2:{m.group(1)}{last}", c.value)
    e = wb["내보내기"]
    head = [c.value for c in e[1]]
    labels = [wb["요약"][f"A{k}"].value for k in range(1, wb["요약"].max_row + 1) if wb["요약"][f"A{k}"].value]
    e.delete_rows(2, e.max_row)
    for i in range(2, n + 2):
        e.append([f'=IF(채점!{L}{i}="","",채점!{L}{i})' for L in "ABCDEFGHIJKLMNOP"])
    e.append([])
    e.append(["summary"] + labels)
    e.append(["value"] + [f"=요약!B{k}" for k in range(1, len(labels) + 1)])
    assert head[0] == "round"


def add_rounds(wb):
    import yaml
    ws = wb["채점"]
    have = {(ws[f"B{r}"].value, ws[f"D{r}"].value) for r in range(2, ws.max_row + 1)}
    names = {c["id"]: c["name"] for c in yaml.safe_load((ROOT / "data" / "companies.yaml").read_text(encoding="utf-8"))}
    added = []
    for p in sorted((ROOT / "content" / "reports").glob("*.md")):
        t = p.read_text(encoding="utf-8")
        if not t.startswith("---"):
            continue
        f = yaml.safe_load(t.split("---", 2)[1]) or {}
        sc, cid = f.get("score"), f.get("company")
        if not sc or cid not in names or (cid, sc["item"]) in have:
            continue
        rnd = 1 + sum(1 for r in range(2, ws.max_row + 1) if ws[f"B{r}"].value == cid)
        i = ws.max_row + 1
        for col, v in zip("ABCDEFGHIJK", [rnd, cid, names[cid], sc["item"], str(f["date"]), int(sc["mine"]), int(sc["consensus"]),
                                           None, None, None, sc.get("due", "")]):
            ws[f"{col}{i}"] = v
        formulas(ws, i)
        have.add((cid, sc["item"]))
        added.append(f"{cid} {sc['item']}")
    if added:
        relink(wb, ws.max_row - 1)
        print("채점표에 새 줄: " + ", ".join(added))
    return added


def main(argv):
    dry = "--dry" in argv
    wb = load_workbook(WB)
    added = add_rounds(wb)
    ws = wb["채점"]
    changed = []
    for r in range(2, ws.max_row + 1):
        cid, item, pub, actual = ws[f"B{r}"].value, ws[f"D{r}"].value, ws[f"E{r}"].value, ws[f"H{r}"].value
        if not cid or actual not in (None, ""):
            continue
        period = quarter_of(item)
        if not period:
            continue
        hit = find(cid, period, str(pub))
        if not hit:
            continue
        text = doc_text(hit["rcept_no"])
        val = op_of(text) if text else None
        if val is None:
            print(f"{cid}: 공시는 있는데 영업이익을 못 읽었다 ({hit['rcept_no']}) — 손으로 넣는다")
            continue
        changed.append((cid, item, val, hit["date"]))
        if not dry:
            ws[f"H{r}"], ws[f"I{r}"], ws[f"J{r}"], ws[f"K{r}"] = val, hit["date"], SOURCE, None
    for c in changed:
        print(f"실제 값: {c[0]} {c[1]} = {c[2]:,}억원 ({c[3]} 공시)")
    if (changed or added) and not dry:
        wb.save(WB)
    if not changed:
        print("채점표: 새로 채울 실제 값 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
