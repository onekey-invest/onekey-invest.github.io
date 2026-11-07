"""커버 기업의 최근 1년 주요 공시를 OpenDART에서 받아 data/disclosures/<기업 id>.json에 적는다.

인증키는 환경변수 OPENDART_API_KEY에서 읽는다(파일·화면에 적지 않는다). 깃허브에서 돌릴 때는 저장소 Secrets에 같은 이름으로 넣는다.
받는 것: 공시 목록(접수일, 보고서 이름, 접수번호). 주가 반응은 build.py가 시세 파일로 잰다.

실행: python tools/update_disclosures.py
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
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "https://opendart.fss.or.kr/api"

# 화면에 올릴 주요 공시(보고서 이름에 들어 있는 말). 그 밖(임원 소유 보고, 대량보유 등)은 뺀다
KEEP = [
    ("실적", r"영업\(잠정\)실적|잠정\)실적|매출액또는손익구조"),
    ("정기", r"^(\[[^\]]+\])?(사업|반기|분기)보고서"),
    ("수주", r"단일판매|공급계약"),
    ("주주환원", r"자기주식|현금ㆍ현물배당|현금·현물배당|주식소각|배당"),
    ("자본·지배구조", r"유상증자|무상증자|전환사채|교환사채|합병|분할|타법인주식|유형자산|영업양수|영업양도|최대주주"),
    ("IR", r"기업설명회"),
]


def get(path, **params):
    params["crtfc_key"] = os.environ["OPENDART_API_KEY"]
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def corp_codes():
    raw = get("corpCode.xml")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read(z.namelist()[0])
    out = {}
    for el in ElementTree.fromstring(xml).iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if stock:
            out[stock] = el.findtext("corp_code").strip()
    return out


def kind_of(name):
    for k, pat in KEEP:
        if re.search(pat, name):
            return k
    return None


def main():
    if not os.environ.get("OPENDART_API_KEY"):
        print("OPENDART_API_KEY가 없다")
        return 2
    companies = yaml.safe_load((ROOT / "data" / "companies.yaml").read_text(encoding="utf-8"))
    codes = corp_codes()
    end = date.today()
    start = end - timedelta(days=365)
    outdir = ROOT / "data" / "disclosures"
    outdir.mkdir(parents=True, exist_ok=True)
    failed = []
    for c in companies:
        corp = codes.get(str(c["ticker"]))
        if not corp:
            failed.append(c["id"])
            continue
        rows, page = [], 1
        while True:
            d = json.loads(get("list.json", corp_code=corp, bgn_de=f"{start:%Y%m%d}", end_de=f"{end:%Y%m%d}",
                               page_no=page, page_count=100))
            if d.get("status") == "013":      # 자료 없음
                break
            if d.get("status") != "000":
                raise RuntimeError(f"{c['id']}: {d.get('status')} {d.get('message')}")
            rows += d["list"]
            if page >= int(d.get("total_page", 1)):
                break
            page += 1
            time.sleep(0.2)
        keep = []
        for r in rows:
            name = re.sub(r"\s+", " ", r["report_nm"]).strip()
            k = kind_of(name)
            if not k:
                continue
            keep.append({"date": f"{r['rcept_dt'][:4]}-{r['rcept_dt'][4:6]}-{r['rcept_dt'][6:]}", "name": name, "kind": k,
                         "rcept_no": r["rcept_no"], "corrected": name.startswith("[기재정정]") or "정정" in name[:6]})
        keep.sort(key=lambda x: (x["date"], x["rcept_no"]), reverse=True)
        (outdir / f"{c['id']}.json").write_text(json.dumps({"asof": end.isoformat(), "source": "OpenDART 공시목록", "items": keep},
                                                           ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{c['id']}: 공시 {len(rows)}건 중 주요 {len(keep)}건")
        time.sleep(0.3)
    if failed:
        print("고유번호를 못 찾음:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
