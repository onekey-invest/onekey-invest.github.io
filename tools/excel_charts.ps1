# 사이트 화면의 그림을 엑셀이 그린다.
#   1) python build.py --charts <자료.json>   사이트가 그림마다 쓸 자료를 적어 낸다
#   2) 이 스크립트                              엑셀 통합 문서의 자료 칸을 바꾸고(차트는 건드리지 않는다), 차트를 SVG로 내보낸다
#   3) python build.py                         내보낸 그림을 화면에 넣는다
#
#   powershell -ExecutionPolicy Bypass -File tools\excel_charts.ps1 -Spec <자료.json> -Workbook <그림.xlsx> -Out static\charts
#
# 통합 문서는 그림마다 시트가 하나다(왼쪽에 자료, 오른쪽에 차트). 표 안의 작은 그림은 '작은그림' 시트에 모여 있다.
# 차트가 이미 있으면 계열이 읽는 범위만 새 자료에 맞춘다. 엑셀에서 손으로 고친 색·글꼴·크기·제목은 그대로 남는다.
# 차트가 없을 때(새 그림)만 기본 모양으로 만든다. 그림을 처음 모양으로 되돌리려면 그 시트를 지우고 다시 돌린다.
# 이 파일은 한글이 들어 있어 UTF-8(BOM)으로 저장해야 한다.
param(
    [Parameter(Mandatory = $true)][string]$Spec,
    [Parameter(Mandatory = $true)][string]$Workbook,
    [Parameter(Mandatory = $true)][string]$Out
)
$ErrorActionPreference = 'Stop'
$FONT = '맑은 고딕'
$LIST = '목록'
$SPARK = '작은그림'

function Rgb([string]$hex) {
    $h = $hex.TrimStart('#')
    $r = [Convert]::ToInt32($h.Substring(0, 2), 16); $g = [Convert]::ToInt32($h.Substring(2, 2), 16); $b = [Convert]::ToInt32($h.Substring(4, 2), 16)
    return $r + 256 * $g + 65536 * $b
}
function OADate([string]$s) { return [datetime]::ParseExact($s, 'yyyy-MM-dd', $null).ToOADate() }
function SheetName([string]$id) {
    $n = ($id -replace '[\\/\?\*\[\]:]', '_')
    if ($n.Length -gt 31) { $n = $n.Substring(0, 31) }
    return $n
}
function FindSheet($wb, [string]$name) {
    foreach ($s in $wb.Worksheets) { if ($s.Name -eq $name) { return $s } }
    return $null
}
function PutColumn($ws, [int]$col, [int]$row0, $values) {
    $n = $values.Count
    if ($n -eq 0) { return }
    $arr = New-Object 'object[,]' $n, 1
    for ($i = 0; $i -lt $n; $i++) { $arr[$i, 0] = $values[$i] }
    $ws.Range($ws.Cells.Item($row0, $col), $ws.Cells.Item($row0 + $n - 1, $col)).Value2 = $arr
}
function BaseLook($ch) {
    $ch.HasTitle = $false
    $ch.ChartArea.Font.Name = $FONT
    $ch.ChartArea.Font.Size = 9
    $ch.ChartArea.Font.Color = (Rgb '#475467')
    $ch.ChartArea.Format.Line.Visible = 0
    $ch.ChartArea.Format.Fill.Visible = 0
    $ch.PlotArea.Format.Fill.Visible = 0
}

# ---- 시계열(주가·변화율): 분산형(직선)으로 그린다. 계열마다 날짜가 달라도 되고, 계단 선은 점을 겹쳐 만든다.
function DrawTime($ws, $c, [bool]$isNew) {
    $ws.Range('A:ZZ').ClearContents() | Out-Null
    $col = 1; $ranges = @()
    foreach ($s in $c.series) {
        $n = $s.points.Count
        $ws.Cells.Item(1, $col).Value2 = '날짜'; $ws.Cells.Item(1, $col + 1).Value2 = [string]$s.name
        $x = @(); $y = @(); $t = @(); $hasLabel = $false
        foreach ($p in $s.points) { $x += (OADate $p[0]); $y += [double]$p[1]; if ($p.Count -gt 2) { $t += [string]$p[2]; $hasLabel = $true } else { $t += '' } }
        PutColumn $ws $col 2 $x; PutColumn $ws ($col + 1) 2 $y
        $ws.Range($ws.Cells.Item(2, $col), $ws.Cells.Item($n + 1, $col)).NumberFormat = 'yyyy-mm-dd'
        if ($hasLabel) { $ws.Cells.Item(1, $col + 2).Value2 = '표시 글'; PutColumn $ws ($col + 2) 2 $t }
        $ranges += , @($col, $n, $s, $t)
        $col += 3
    }
    if ($isNew) {
        $w = 720; $h = 300; if ($c.w) { $w = [double]$c.w }; if ($c.h) { $h = [double]$c.h }
        $co = $ws.ChartObjects().Add(($col + 1) * 52, 10, $w, $h)
        $co.Name = 'chart'
        $ch = $co.Chart
        $ch.ChartType = 75      # xlXYScatterLinesNoMarkers
    }
    else { $co = $ws.ChartObjects().Item(1); $ch = $co.Chart }
    $sc = $ch.SeriesCollection()
    while ($sc.Count -gt $ranges.Count) { $sc.Item($sc.Count).Delete() | Out-Null }
    $k = 0; $xmin = [double]::MaxValue; $xmax = [double]::MinValue
    foreach ($r in $ranges) {
        $k++; $cc = $r[0]; $n = $r[1]; $s = $r[2]
        $fresh = $false
        if ($k -gt $sc.Count) { $ser = $sc.NewSeries(); $fresh = $true } else { $ser = $sc.Item($k) }
        $ser.Name = [string]$s.name
        $ser.XValues = $ws.Range($ws.Cells.Item(2, $cc), $ws.Cells.Item($n + 1, $cc))
        $ser.Values = $ws.Range($ws.Cells.Item(2, $cc + 1), $ws.Cells.Item($n + 1, $cc + 1))
        $a = [double]$ws.Cells.Item(2, $cc).Value2; $b = [double]$ws.Cells.Item($n + 1, $cc).Value2
        if ($a -lt $xmin) { $xmin = $a }; if ($b -gt $xmax) { $xmax = $b }
        if ($fresh -or $isNew) {
            if ($s.type -eq 'points') {
                $ser.ChartType = -4169          # xlXYScatter(점만)
                $ser.MarkerStyle = 8; $ser.MarkerSize = 7
                $ser.MarkerBackgroundColor = (Rgb $s.color); $ser.MarkerForegroundColor = (Rgb '#FFFFFF')
            }
            else {
                $ser.MarkerStyle = -4142
                $ser.Format.Line.Visible = -1
                $ser.Format.Line.ForeColor.RGB = (Rgb $s.color)
                $ser.Format.Line.Weight = $(if ($s.main) { 2.25 } else { 1.25 })
                if ($s.dash) { $ser.Format.Line.DashStyle = 4 }
            }
        }
        if ($s.type -eq 'points') {
            # 표시 글은 자료가 바뀔 때마다 다시 붙인다(글꼴은 차트 것을 따른다)
            $t = $r[3]
            for ($i = 1; $i -le $n; $i++) {
                $pt = $ser.Points($i); $pt.HasDataLabel = $true
                $pt.DataLabel.Text = [string]$t[$i - 1]
                if ($fresh -or $isNew) { $pt.DataLabel.Position = $(if ($i -eq 1) { -4152 } else { 0 }) }      # 첫 점은 오른쪽, 나머지는 위
            }
        }
    }
    $ax = $ch.Axes(1)
    $ax.MinimumScale = $xmin; $ax.MaximumScale = $xmax       # 자료가 늘면 가로축 끝도 따라간다
    if ($isNew) {
        BaseLook $ch
        $ch.HasLegend = $true; $ch.Legend.Position = -4107
        $ax.TickLabels.NumberFormat = $(if (($xmax - $xmin) -gt 400) { 'yy.mm' } else { 'yy.mm.dd' })
        $ax.HasMajorGridlines = $false
        $ax.Format.Line.ForeColor.RGB = (Rgb '#D0D5DD')
        $ay = $ch.Axes(2)
        $ay.HasMajorGridlines = $true
        $ay.MajorGridlines.Format.Line.ForeColor.RGB = (Rgb '#EAECF0')
        $ay.Format.Line.Visible = 0
        $ay.TickLabels.NumberFormat = $(if ($c.format -eq 'pct') { '0"%"' } else { '#,##0' })
    }
    if ($c.format -eq 'pct') { $ax.CrossesAt = $xmin; $ch.Axes(2).CrossesAt = -1000000 } else { $ax.CrossesAt = $xmin }
    return $co
}

# ---- 원그래프
function DrawPie($ws, $c, [bool]$isNew) {
    $ws.Range('A:ZZ').ClearContents() | Out-Null
    $n = $c.parts.Count
    $ws.Cells.Item(1, 1).Value2 = '이름'; $ws.Cells.Item(1, 2).Value2 = '비중(%)'
    $names = @(); $vals = @()
    foreach ($p in $c.parts) { $names += [string]$p.name; $vals += [double]$p.pct }
    PutColumn $ws 1 2 $names; PutColumn $ws 2 2 $vals
    if ($isNew) {
        $w = 400; $h = 320; if ($c.w) { $w = [double]$c.w }; if ($c.h) { $h = [double]$c.h }
        $co = $ws.ChartObjects().Add(220, 10, $w, $h); $co.Name = 'chart'
        $ch = $co.Chart; $ch.ChartType = 5
        $ser = $ch.SeriesCollection().NewSeries()
    }
    else { $co = $ws.ChartObjects().Item(1); $ch = $co.Chart; $ser = $ch.SeriesCollection().Item(1) }
    if ($isNew) { $ser.Name = '점유율' }
    $ser.XValues = $ws.Range($ws.Cells.Item(2, 1), $ws.Cells.Item($n + 1, 1))
    $ser.Values = $ws.Range($ws.Cells.Item(2, 2), $ws.Cells.Item($n + 1, 2))
    if ($isNew) {
        BaseLook $ch
        $ch.HasLegend = $false
        $ser.HasDataLabels = $true
        $dl = $ser.DataLabels()
        $dl.ShowCategoryName = $true; $dl.ShowValue = $true; $dl.ShowPercentage = $false; $dl.Separator = ' '
        $dl.NumberFormat = '0.0"%"'; $dl.Position = 5        # 엑셀이 겹치지 않게 자리를 잡는다(지시선 포함)
        $ser.HasLeaderLines = $true
        $dl.Font.Size = 9
        for ($i = 1; $i -le $n; $i++) {
            $pt = $ser.Points($i)
            $pt.Format.Fill.ForeColor.RGB = (Rgb $c.parts[$i - 1].color)
            $pt.Format.Line.ForeColor.RGB = (Rgb '#FFFFFF'); $pt.Format.Line.Weight = 1
        }
        $ch.ChartGroups(1).FirstSliceAngle = 20
        try { $ch.PlotArea.Width = $ch.ChartArea.Width * 0.6; $ch.PlotArea.Height = $ch.ChartArea.Height * 0.75
              $ch.PlotArea.Left = ($ch.ChartArea.Width - $ch.PlotArea.Width) / 2; $ch.PlotArea.Top = ($ch.ChartArea.Height - $ch.PlotArea.Height) / 2 } catch { }
        $ch.SetElement(0)        # 제목 없음(계열에 이름을 주면 엑셀이 제목을 붙인다)
    }
    return $co
}

# ---- 표 안의 작은 그림: 한 시트에 모아 둔다. 열 하나가 그림 하나.
function DrawSpark($ws, $c, [int]$col) {
    $n = $c.values.Count
    $ws.Range($ws.Cells.Item(1, $col), $ws.Cells.Item(5000, $col)).ClearContents() | Out-Null
    $ws.Cells.Item(1, $col).Value2 = [string]$c.id
    $v = @(); foreach ($x in $c.values) { $v += [double]$x }
    PutColumn $ws $col 2 $v
    $co = $null
    foreach ($o in $ws.ChartObjects()) { if ($o.Name -eq $c.id) { $co = $o } }
    $isNew = ($null -eq $co)
    if ($isNew) {
        $co = $ws.ChartObjects().Add(40 + 130 * ($col - 1), 320, 120, 34); $co.Name = [string]$c.id
        $ch = $co.Chart; $ch.ChartType = 4
        $ser = $ch.SeriesCollection().NewSeries()
    }
    else { $ch = $co.Chart; $ser = $ch.SeriesCollection().Item(1) }
    $ser.Values = $ws.Range($ws.Cells.Item(2, $col), $ws.Cells.Item($n + 1, $col))
    if ($isNew) {
        BaseLook $ch
        $ch.HasLegend = $false
        $ch.SetElement(348); $ch.SetElement(352); $ch.SetElement(328)       # 가로축·세로축·눈금선 없음
        $ser.MarkerStyle = -4142
        $ser.Format.Line.ForeColor.RGB = (Rgb $c.color); $ser.Format.Line.Weight = 1.5
        try { $ch.PlotArea.Left = 0; $ch.PlotArea.Top = 0; $ch.PlotArea.Width = $ch.ChartArea.Width; $ch.PlotArea.Height = $ch.ChartArea.Height } catch { }      # 작은 차트에서는 엑셀이 크기 지정을 거절할 때가 있다
    }
    else { $ser.Format.Line.ForeColor.RGB = (Rgb $c.color) }       # 오르면 빨강, 내리면 파랑은 자료가 정한다
    return $co
}

$specObj = Get-Content -Raw -Encoding UTF8 $Spec | ConvertFrom-Json
if (-not (Test-Path $Out)) { New-Item -ItemType Directory -Path $Out | Out-Null }
$Out = (Resolve-Path $Out).Path
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
$manifest = [ordered]@{}
try {
    $created = -not (Test-Path $Workbook)
    if ($created) {
        $wb = $xl.Workbooks.Add()
        while ($wb.Worksheets.Count -gt 1) { $wb.Worksheets.Item($wb.Worksheets.Count).Delete() }
        $wb.Worksheets.Item(1).Name = $LIST
    }
    else { $wb = $xl.Workbooks.Open((Resolve-Path $Workbook).Path) }
    $list = FindSheet $wb $LIST
    if ($null -eq $list) { $list = $wb.Worksheets.Add(); $list.Name = $LIST }
    $list.Range('A1:E1').Value2 = [object[]]@('그림', '시트', '종류', '자료 기준일', '마지막 갱신')
    $sparkCol = @{}
    $sp = FindSheet $wb $SPARK
    if ($null -ne $sp) { $j = 1; while ($sp.Cells.Item(1, $j).Value2) { $sparkCol[[string]$sp.Cells.Item(1, $j).Value2] = $j; $j++ } }
    $row = 2
    foreach ($c in $specObj.charts) {
        if ($c.kind -eq 'spark') {
            if ($null -eq $sp) { $sp = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count)); $sp.Name = $SPARK }
            if (-not $sparkCol.ContainsKey([string]$c.id)) { $sparkCol[[string]$c.id] = $sparkCol.Count + 1 }
            $co = DrawSpark $sp $c $sparkCol[[string]$c.id]
            $sheetName = $SPARK
        }
        else {
            $sheetName = SheetName $c.id
            $ws = FindSheet $wb $sheetName
            $isNew = ($null -eq $ws)
            if ($isNew) { $ws = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count)); $ws.Name = $sheetName }
            elseif ($ws.ChartObjects().Count -eq 0) { $isNew = $true }
            if ($c.kind -eq 'pie') { $co = DrawPie $ws $c $isNew } else { $co = DrawTime $ws $c $isNew }
        }
        $file = Join-Path $Out ($c.id + '.svg')
        if (Test-Path $file) { Remove-Item $file -Force }
        [void]$co.Chart.Export($file)
        $manifest[[string]$c.id] = [ordered]@{ asof = [string]$c.asof; w = [math]::Round($co.Width * 96 / 72); h = [math]::Round($co.Height * 96 / 72) }
        $list.Cells.Item($row, 1).Value2 = [string]$c.id; $list.Cells.Item($row, 2).Value2 = $sheetName; $list.Cells.Item($row, 3).Value2 = [string]$c.kind
        $list.Cells.Item($row, 4).Value2 = [string]$c.asof; $list.Cells.Item($row, 5).Value2 = (Get-Date).ToString('yyyy-MM-dd HH:mm')
        $row++
    }
    $list.Columns('A:E').AutoFit() | Out-Null
    if ($created) { $wb.SaveAs($Workbook, 51) } else { $wb.Save() }
    $wb.Close($false)
}
catch {
    Write-Output ("실패: {0} (줄 {1}: {2})" -f $_.Exception.Message, $_.InvocationInfo.ScriptLineNumber, $_.InvocationInfo.Line.Trim())
    throw
}
finally {
    $xl.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
$json = $manifest | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $Out 'manifest.json'), $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ("그림 {0}개를 내보냈다 → {1}" -f $manifest.Count, $Out)
