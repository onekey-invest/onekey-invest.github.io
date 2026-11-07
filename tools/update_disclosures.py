"""커버 기업의 주요 공시를 data/disclosures/<기업 id>.json에 적는다.

두 가지 방식이 있다.
- 키 없이(기본, 깃허브 매일 실행): DART의 회사별 RSS(https://dart.fss.or.kr/api/companyRSS.xml?crpCd=…)를 읽는다.
  RSS는 최근 5영업일치만 주므로, 받은 것을 기존 목록에 덧붙인다(지난 줄은 지우지 않는다). 공시 시각도 함께 적는다.
- 키로(처음 채울 때·빠진 기간을 메울 때, 이 PC에서): 환경변수 OPENDART_API_KEY가 있으면 OpenDART 공시목록 API로 1년치를 받아 덧붙인다.
  키는 파일·화면에 적지 않는다. 깃허브에는 키를 주지 않는다.

DART 고유번호(corp_code)는 data/disclosures/_corp.json에 있다(공개된 번호. 키로 돌릴 때 새로 맞춘다).

실행: python tools/update_disclosures.py            (키가 있으면 키로, 없으면 RSS로)
      python tools/update_disclosures.py --rss      (키가 있어도 RSS로)
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "disclosures"
API = "https://opendart.fss.or.kr/api"
RSS = "https://dart.fss.or.kr/api/companyRSS.xml?crpCd={}"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "OneKey-site-builder (personal research site)"}

# 화면에 올릴 주요 공시(보고서 이름에 들어 있는 말). 그 밖(임원 소유 보고, 대량보유 등)은 뺀다
KEEP = [
    ("실적", r"영업\(잠정\)실적|잠정\)실적|매출액또는손익구조"),
    ("정기", r"(사업|반기|분기)보고서"),
    ("수주", r"단일판매|공급계약"),
    ("주주환원", r"자기주식|현금ㆍ현물배당|현금·현물배당|주식소각|배당"),
    ("자본·지배구조", r"유상증자|무상증자|전환사채|교환사채|합병|분할|타법인주식|유형자산|영업양수|영업양도|최대주주"),
    ("IR", r"기업설명회"),
]


def kind_of(name):
    for k, pat in KEEP:
        if re.search(pat, name):
            return k
    return None


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def api(path, **params):
    params["crtfc_key"] = os.environ["OPENDART_API_KEY"]
    return fetch(f"{API}/{path}?{urllib.parse.urlencode(params)}")


def load(cid):
    p = OUT / f"{cid}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"items": []}


def save(cid, d, source):
    seen, items = set(), []
    for x in sorted(d["items"], key=lambda x: (x["date"], x.get("time", ""), x["rcept_no"]), reverse=True):
        if x["rcept_no"] in seen:
            continue
        seen.add(x["rcept_no"])
        items.append(x)
    d.update(items=items, asof=date.today().isoformat(), source=source)
    (OUT / f"{cid}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(items)


def row(day, name, rcept_no, hhmm=""):
    name = re.sub(r"\s+", " ", name).strip()
    k = kind_of(name)
    if not k:
        return None
    x = {"date": day, "name": name, "kind": k, "rcept_no": rcept_no, "corrected": "정정" in name[:8]}
    if hhmm:
        x["time"] = hhmm
    return x


def by_rss(cid, corp):
    root = ElementTree.fromstring(fetch(RSS.format(corp)))
    out = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        name = title.split(" - ", 1)[1] if " - " in title else title       # "(유가)기아 - 보고서 이름"
        no = re.search(r"rcpNo=(\d+)", it.findtext("link") or "")
        if not no:
            continue
        when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        x = row(when.strftime("%Y-%m-%d"), name, no.group(1), when.strftime("%H:%M"))
        if x:
            out.append(x)
    return out


def by_api(corp, start, end):
    rows, page = [], 1
    while True:
        d = json.loads(api("list.json", corp_code=corp, bgn_de=f"{start:%Y%m%d}", end_de=f"{end:%Y%m%d}", page_no=page, page_count=100))
        if d.get("status") == "013":      # 자료 없음
            break
        if d.get("status") != "000":
            raise RuntimeError(f"{d.get('status')} {d.get('message')}")
        rows += d["list"]
        if page >= int(d.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.2)
    out = []
    for r in rows:
        x = row(f"{r['rcept_dt'][:4]}-{r['rcept_dt'][4:6]}-{r['rcept_dt'][6:]}", r["report_nm"], r["rcept_no"])
        if x:
            out.append(x)
    return out


def corp_map(companies, use_key):
    p = OUT / "_corp.json"
    have = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    if use_key and any(str(c["ticker"]) not in have for c in companies):
        with zipfile.ZipFile(io.BytesIO(api("corpCode.xml"))) as z:
            xml = z.read(z.namelist()[0])
        alls = {(e.findtext("stock_code") or "").strip(): e.findtext("corp_code").strip() for e in ElementTree.fromstring(xml).iter("list")}
        have.update({str(c["ticker"]): alls[str(c["ticker"])] for c in companies if str(c["ticker"]) in alls})
        p.write_text(json.dumps(have, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return have


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    use_key = bool(os.environ.get("OPENDART_API_KEY")) and "--rss" not in argv
    companies = yaml.safe_load((ROOT / "data" / "companies.yaml").read_text(encoding="utf-8"))
    corps = corp_map(companies, use_key)
    failed = []
    for c in companies:
        corp = corps.get(str(c["ticker"]))
        if not corp:
            failed.append(f"{c['id']}(고유번호 없음)")
            continue
        try:
            d = load(c["id"])
            new = by_api(corp, date.today() - timedelta(days=365), date.today()) if use_key else by_rss(c["id"], corp)
            # 같은 접수번호가 이미 있으면 시각 등 새로 안 것만 더한다
            old = {x["rcept_no"]: x for x in d["items"]}
            for x in new:
                old[x["rcept_no"]] = {**x, **{k: v for k, v in old.get(x["rcept_no"], {}).items() if k == "time" and "time" not in x}}
            d["items"] = list(old.values())
            n = save(c["id"], d, "OpenDART 공시목록" if use_key else "DART 회사별 RSS")
            print(f"{c['id']}: 새로 받은 {len(new)}건, 목록 {n}건")
        except Exception as e:      # 한 회사가 실패해도 나머지는 받는다
            failed.append(f"{c['id']}({type(e).__name__})")
        time.sleep(0.3)
    if failed:
        print("실패:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
