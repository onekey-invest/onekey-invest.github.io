"""그림 자료(build.py --charts)에는 있는데 그림 원본 엑셀에 시트(작은 그림은 '작은그림' 시트의 열)가 없는 그림의 수를 적는다.
PC 예약 작업이 이 수가 0보다 크면 엑셀로 새 시트를 만든다.

실행: python tools/missing_chart_sheets.py <그림 자료.json> <그림 원본.xlsx>
"""
import json
import re
import sys

import openpyxl


def main(spec_path, wb_path):
    spec = json.load(open(spec_path, encoding="utf-8"))["charts"]
    wb = openpyxl.load_workbook(wb_path, read_only=True)
    names = set(wb.sheetnames)
    head = set()
    if "작은그림" in names:
        head = {c.value for c in next(wb["작은그림"].iter_rows(min_row=1, max_row=1))}
    missing = [c["id"] for c in spec
               if (c["id"] not in head if c["kind"] == "spark" else re.sub(r"[\/\?\*\[\]:]", "_", c["id"])[:31] not in names)]
    print(len(missing))
    if missing:
        print("없음: " + ", ".join(missing), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
