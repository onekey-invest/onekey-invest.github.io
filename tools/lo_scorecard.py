"""채점표 원본(scorecard_src/scorecard.xlsx)을 LibreOffice로 다시 계산해 '내보내기' 시트 값을 data/scorecard.csv로 낸다.

계산은 통합 문서의 수식이 한다(이 스크립트는 계산하지 않고, 계산된 값을 옮기기만 한다). 통합 문서는 저장하지 않는다.
LibreOffice가 떠 있어야 한다: soffice --headless --accept="socket,host=localhost,port=2003;urp;" &
실행(깃허브 서버): /usr/bin/python3 tools/lo_scorecard.py scorecard_src/scorecard.xlsx data/scorecard.csv
PC에서는 엑셀로: 채점표 폴더의 export.ps1 + to_csv.py(같은 결과)
"""
import csv
import os
import sys
import time

import uno
from com.sun.star.beans import PropertyValue


def pv(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def connect(port):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    for _ in range(60):
        try:
            return resolver.resolve(f"uno:socket,host=localhost,port={port};urp;StarOffice.ComponentContext")
        except Exception:
            time.sleep(1)
    raise RuntimeError("LibreOffice에 붙지 못했다")


def cell(v):
    if isinstance(v, float):
        return int(v) if v.is_integer() else repr(v)
    return v


def main(wb_path, out, port=2003):
    ctx = connect(port)
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(os.path.abspath(wb_path)), "_blank", 0, (pv("Hidden", True),))
    try:
        doc.calculateAll()
        ws = doc.getSheets().getByName("내보내기")
        cur = ws.createCursor()
        cur.gotoEndOfUsedArea(False)
        last_col, last_row = cur.getRangeAddress().EndColumn, cur.getRangeAddress().EndRow
        rows = [[cell(v) for v in r] for r in ws.getCellRangeByPosition(0, 0, last_col, last_row).getDataArray()]
    finally:
        doc.close(True)
    # 채점한 줄인데 오차가 비었으면 계산이 안 된 것이다: 내지 않는다
    for r in rows[1:]:
        if r and r[0] not in ("", "summary", "value") and r[7] != "" and (r[11] == "" or r[12] == ""):
            raise SystemExit(f"계산 값이 비어 있다: {r[:4]}")
    with open(out, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(f"{len(rows)}줄 → {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2003)
