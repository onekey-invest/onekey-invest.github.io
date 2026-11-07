"""사이트 그림을 깃허브 서버(리눅스)의 LibreOffice가 그린다. PC가 꺼져 있어도 매일 돈다.

그림의 모양은 저장소의 그림 원본 엑셀(charts_src/site_charts.xlsx)에 있다. 본인이 PC의 엑셀에서 고쳐 저장하면
PC의 예약 작업이 그 파일을 저장소로 올리고, 다음 실행부터 그 모양으로 그린다.
이 프로그램은 그 파일을 열어 자료 칸만 새 자료로 바꾸고(엑셀 예약 작업 tools/excel_charts.ps1과 같은 자리),
차트가 읽는 범위를 맞춘 뒤 그림(PNG)으로 내보낸다. 파일은 저장하지 않는다(모양이 바뀌지 않게).
원본에 시트가 없는 새 그림은 건너뛴다(그 전 그림이 남는다). PC에서 엑셀이 한 번 시트를 만들면 그다음부터 그린다.

실행(서버): soffice --headless --accept="socket,host=localhost,port=2002;urp;" &
           /usr/bin/python3 tools/lo_charts.py <그림 자료.json> charts_src/site_charts.xlsx static/charts
"""
import json
import os
import re
import sys
import time
from datetime import date

import uno
from com.sun.star.beans import PropertyValue

SPARK = "작은그림"
SCALE = 2          # 화면보다 두 배 크게 그려 선명하게


def pv(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def oadate(s):
    return float((date.fromisoformat(s) - date(1899, 12, 30)).days)


def sheet_name(cid):
    return re.sub(r"[\\/\?\*\[\]:]", "_", cid)[:31]


def col_letter(c):          # 1 → A
    s = ""
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def connect():
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    for _ in range(60):
        try:
            return resolver.resolve("uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
        except Exception:
            time.sleep(1)
    raise RuntimeError("LibreOffice에 붙지 못했다")


def put(sheet, col, row, values):
    """col(1부터)·row(1부터)에서 아래로 값들을 적는다."""
    if not values:
        return
    rng = sheet.getCellRangeByPosition(col - 1, row - 1, col - 1, row - 1 + len(values) - 1)
    rng.setDataArray(tuple((v,) for v in values))


def clear(sheet, cols=702, rows=6000):
    sheet.getCellRangeByPosition(0, 0, cols - 1, rows - 1).clearContents(1 | 2 | 4 | 16)


def all_series(chart):
    cs = chart.getFirstDiagram().getCoordinateSystems()[0]
    out = []
    for ct in cs.getChartTypes():
        out += list(ct.getDataSeries())
    return cs, out


def rerange(model, ls, rep):
    """라벨 붙은 자료 열(ls)의 값 범위를 rep로 바꾼다. 역할(x값·y값 등)은 그대로."""
    old = ls.getValues()
    role = old.getPropertyValue("Role")
    seq = model.getDataProvider().createDataSequenceByRangeRepresentation(rep)
    seq.setPropertyValue("Role", role)
    ls.setValues(seq)


def prefix_of(model, series_list):
    """차트가 쓰는 범위 표기의 시트 부분(예: $'company-kia')."""
    for s in series_list:
        for ls in s.getDataSequences():
            r = ls.getValues().getSourceRangeRepresentation()
            if "." in r:
                return r.split(".$", 1)[0]
    return None


def rng(prefix, col, r1, r2):
    L = col_letter(col)
    return f"{prefix}.${L}${r1}:${L}${r2}"


def set_label_texts(smgr, model, series, k, texts):
    """점 계열(의견·목표주가 변경)의 점마다 글자를 붙인다. 글꼴·자리는 원본 차트 것을 따른다.
    새 차트 창구(chart2)의 점 객체는 속성 바꾸기를 열어 주지 않아, 옛 차트 창구(com.sun.star.chart)의 점 속성으로 바꾼다."""
    old_diagram = model.getDiagram()                 # 옛 창구
    for i, t in enumerate(texts):
        f = smgr.createInstance("com.sun.star.chart2.DataPointCustomLabelField")
        f.setFieldType(uno.Enum("com.sun.star.chart2.DataPointCustomLabelFieldType", "TEXT"))
        f.setString(t)
        props = old_diagram.getDataPointProperties(i, k)
        props.setPropertyValue("CustomLabelFields", (f,))
        lab = props.getPropertyValue("Label")
        lab.ShowCustomLabel = True
        lab.ShowNumber = False
        lab.ShowCategoryName = False
        props.setPropertyValue("Label", lab)


def draw_time(smgr, sheet, model, c):
    clear(sheet)
    col, layout = 1, []
    for s in c["series"]:
        pts = s["points"]
        n = len(pts)
        sheet.getCellByPosition(col - 1, 0).setString("날짜")
        sheet.getCellByPosition(col, 0).setString(str(s["name"]))
        put(sheet, col, 2, [oadate(p[0]) for p in pts])
        put(sheet, col + 1, 2, [float(p[1]) for p in pts])
        texts = [str(p[2]) if len(p) > 2 else "" for p in pts]
        if any(texts):
            sheet.getCellByPosition(col + 1, 0).setString("표시 글")
            put(sheet, col + 2, 2, texts)
        layout.append((col, n, s, texts))
        col += 3
    cs, ser = all_series(model)
    pre = prefix_of(model, ser)
    if not pre or len(ser) < len(layout):
        raise RuntimeError(f"계열 수가 원본과 다르다({len(ser)} < {len(layout)})")
    xmin, xmax = 1e18, -1e18
    for k, (cc, n, s, texts) in enumerate(layout):
        for ls in ser[k].getDataSequences():
            role = ls.getValues().getPropertyValue("Role")
            if role == "values-x":
                rerange(model, ls, rng(pre, cc, 2, n + 1))
            elif role == "values-y":
                rerange(model, ls, rng(pre, cc + 1, 2, n + 1))
        xs = [oadate(p[0]) for p in s["points"]]
        xmin, xmax = min(xmin, xs[0]), max(xmax, xs[-1])
        if s.get("type") == "points":
            try:
                set_label_texts(smgr, model, ser[k], k, texts)
            except Exception as e:      # 글자를 못 붙여도 그림은 낸다(원본에 있던 글자가 남는다)
                print(f"  {c['id']}: 변경 점 글자를 새로 붙이지 못함 ({type(e).__name__} {e})")
    for extra in ser[len(layout):]:        # 원본보다 계열이 적어졌으면 남는 계열을 뺀다
        for ct in cs.getChartTypes():
            if extra in list(ct.getDataSeries()):
                ct.removeDataSeries(extra)
    ax = cs.getAxisByDimension(0, 0)
    sd = ax.getScaleData()
    sd.Minimum, sd.Maximum = xmin, xmax
    ax.setScaleData(sd)


def draw_cats(smgr, sheet, model, cats, series_values, header_names):
    """막대·원: 1열은 구분, 2열부터 계열."""
    clear(sheet)
    n = len(cats)
    sheet.getCellByPosition(0, 0).setString(header_names[0])
    put(sheet, 1, 2, [str(x) for x in cats])
    for k, (name, vals) in enumerate(series_values):
        sheet.getCellByPosition(k + 1, 0).setString(str(name))
        put(sheet, k + 2, 2, [float(v) for v in vals])
    cs, ser = all_series(model)
    pre = prefix_of(model, ser)
    if not pre or len(ser) < len(series_values):
        raise RuntimeError("계열 수가 원본과 다르다")
    for k in range(len(series_values)):
        for ls in ser[k].getDataSequences():
            if ls.getValues().getPropertyValue("Role") == "values-y":
                rerange(model, ls, rng(pre, k + 2, 2, n + 1))
    ax = cs.getAxisByDimension(0, 0)
    sd = ax.getScaleData()
    if sd.Categories:
        rerange(model, sd.Categories, rng(pre, 1, 2, n + 1))
        ax.setScaleData(sd)


def draw_spark(smgr, sheet, model, c, col):
    sheet.getCellRangeByPosition(col - 1, 0, col - 1, 4999).clearContents(1 | 2 | 4 | 16)
    sheet.getCellByPosition(col - 1, 0).setString(c["id"])
    vals = [float(v) for v in c["values"]]
    put(sheet, col, 2, vals)
    cs, ser = all_series(model)
    pre = prefix_of(model, ser)
    for ls in ser[0].getDataSequences():
        if ls.getValues().getPropertyValue("Role") == "values-y":
            rerange(model, ls, rng(pre, col, 2, len(vals) + 1))
    ax = cs.getAxisByDimension(0, 0)
    sd = ax.getScaleData()
    if sd.Categories:
        rerange(model, sd.Categories, rng(pre, col, 2, len(vals) + 1))
        ax.setScaleData(sd)


def chart_shapes(sheet):
    dp = sheet.getDrawPage()
    out = {}
    for i in range(dp.getCount()):
        s = dp.getByIndex(i)
        if s.supportsService("com.sun.star.drawing.OLE2Shape"):
            out[s.getPropertyValue("Name")] = s
    return out


def export_png(smgr, ctx, shape, path):
    size = shape.getSize()                       # 1/100 mm
    w = round(size.Width / 2540 * 96)
    h = round(size.Height / 2540 * 96)
    gef = smgr.createInstanceWithContext("com.sun.star.drawing.GraphicExportFilter", ctx)
    gef.setSourceDocument(shape)
    fd = uno.Any("[]com.sun.star.beans.PropertyValue", (pv("PixelWidth", w * SCALE), pv("PixelHeight", h * SCALE)))
    gef.filter((pv("URL", uno.systemPathToFileUrl(os.path.abspath(path))), pv("MediaType", "image/png"), pv("FilterData", fd)))
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise RuntimeError("빈 그림")
    return w, h


def main(spec_path, wb_path, out):
    spec = json.load(open(spec_path, encoding="utf-8"))["charts"]
    os.makedirs(out, exist_ok=True)
    man_path = os.path.join(out, "manifest.json")
    manifest = json.load(open(man_path, encoding="utf-8")) if os.path.exists(man_path) else {}
    ctx = connect()
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(os.path.abspath(wb_path)), "_blank", 0, (pv("Hidden", True),))
    sheets = doc.getSheets()
    spark = sheets.getByName(SPARK) if sheets.hasByName(SPARK) else None
    spark_cols = {}
    if spark:
        j = 1
        while spark.getCellByPosition(j - 1, 0).getString():
            spark_cols[spark.getCellByPosition(j - 1, 0).getString()] = j
            j += 1
    done, skipped, failed = 0, [], []
    for c in spec:
        cid = c["id"]
        try:
            if c["kind"] == "spark":
                if not spark or cid not in spark_cols:
                    skipped.append(cid)
                    continue
                shape = chart_shapes(spark).get(cid)
                if shape is None:
                    skipped.append(cid)
                    continue
                draw_spark(smgr, spark, shape.getPropertyValue("Model"), c, spark_cols[cid])
            else:
                name = sheet_name(cid)
                if not sheets.hasByName(name):
                    skipped.append(cid)
                    continue
                sheet = sheets.getByName(name)
                shapes = chart_shapes(sheet)
                if not shapes:
                    skipped.append(cid)
                    continue
                shape = shapes.get("chart") or list(shapes.values())[0]
                model = shape.getPropertyValue("Model")
                if c["kind"] == "time":
                    draw_time(smgr, sheet, model, c)
                elif c["kind"] == "bar":
                    draw_cats(smgr, sheet, model, c["cats"], [(s["name"], s["values"]) for s in c["series"]], ["구분"])
                elif c["kind"] == "pie":
                    draw_cats(smgr, sheet, model, [p["name"] for p in c["parts"]], [("비중(%)", [p["pct"] for p in c["parts"]])], ["이름"])
            path = os.path.join(out, f"{cid}.png")
            w, h = export_png(smgr, ctx, shape, path)
            manifest[cid] = {"asof": str(c.get("asof", "")), "w": w, "h": h, "file": f"{cid}.png"}
            done += 1
        except Exception as e:
            import traceback
            tb = traceback.extract_tb(e.__traceback__)[-1]
            failed.append(f"{cid}: {type(e).__name__} {e} (줄 {tb.lineno}: {tb.line})")
    doc.close(True)            # 저장하지 않는다
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"그림 {done}개 그림 · 원본에 시트가 없어 건너뜀 {len(skipped)}개 {skipped} · 실패 {len(failed)}개")
    for x in failed:
        print("  실패", x)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
