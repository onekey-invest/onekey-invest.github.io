// 차트. TradingView의 Lightweight Charts로 그린다.
// 라이브러리를 불러오지 못하면 빌드할 때 만들어 둔 SVG가 그대로 남는다.
(function () {
  const LC = window.LightweightCharts;
  if (!LC) return;

  const fmt = {
    price: (v) => Math.round(v).toLocaleString("ko-KR"),
    pct: (v) => (v > 0 ? "+" : "") + v.toFixed(1) + "%",
  };

  const rgba = (hex, a) => {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  document.querySelectorAll(".chart").forEach((root) => {
    const src = root.querySelector('script[type="application/json"]');
    const box = root.querySelector(".chart-canvas");
    if (!src || !box) return;
    let cfg;
    try {
      cfg = JSON.parse(src.textContent);
    } catch (e) {
      return;
    }
    if (!cfg.series || !cfg.series.length) return;
    const format = fmt[cfg.format] || fmt.price;

    box.innerHTML = "";
    box.classList.add("live");
    const chart = LC.createChart(box, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "#667085",
        fontSize: 11,
        fontFamily: '"Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif',
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#eef0f3" } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
      timeScale: { borderVisible: false },
      crosshair: {
        mode: LC.CrosshairMode.Magnet,
        vertLine: { color: "#98a2b3", width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: "#1f2a44" },
        horzLine: { visible: false, labelVisible: false },
      },
      localization: { locale: "ko-KR", dateFormat: "yyyy.MM.dd", priceFormatter: format },
      // 페이지를 내릴 때 차트가 휠을 가로채지 않게 한다
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: false },
    });

    const made = cfg.series.map((s) => {
      const data = s.data.map(([time, value]) => ({ time, value }));
      const common = {
        priceLineVisible: false,
        lastValueVisible: s.type === "area" || s.type === "step" || cfg.series.length <= 2,
        priceFormat: { type: "custom", formatter: format, minMove: 0.01 },
        crosshairMarkerRadius: 3.5,
      };
      let series;
      if (s.type === "area") {
        series = chart.addSeries(LC.AreaSeries, {
          ...common,
          lineColor: s.color,
          lineWidth: 2,
          topColor: rgba(s.color, 0.16),
          bottomColor: rgba(s.color, 0),
        });
      } else {
        series = chart.addSeries(LC.LineSeries, {
          ...common,
          color: s.color,
          lineWidth: s.type === "step" ? 1 : 2,
          lineStyle: s.dash ? LC.LineStyle.Dashed : LC.LineStyle.Solid,
          lineType: s.type === "step" ? LC.LineType.WithSteps : LC.LineType.Simple,
          crosshairMarkerVisible: s.type !== "step",
        });
      }
      series.setData(data);
      return { cfg: s, series, last: data[data.length - 1] };
    });

    // 표시는 맨 위에 그려진 선(마지막 것)에 붙인다
    const main = made[made.length - 1];
    if (cfg.markers && cfg.markers.length && LC.createSeriesMarkers) {
      LC.createSeriesMarkers(
        main.series,
        cfg.markers.map((m) => ({ time: m.time, position: "aboveBar", color: "#0f766e", shape: "circle", text: m.text }))
      );
    }

    // 범례: 평소에는 마지막 값, 선 위에 올리면 그 날짜의 값
    const legend = root.querySelector(".chart-legend");
    const draw = (param) => {
      if (!legend) return;
      const hover = param && param.time;
      const date = hover ? String(param.time).replaceAll("-", ".") : main.last.time.replaceAll("-", ".");
      const items = [...made].reverse().map((m) => {
        const point = hover ? param.seriesData.get(m.series) : m.last;
        const value = point && point.value !== undefined ? format(point.value) : "–";
        return `<span><i style="background:${m.cfg.color}"></i>${m.cfg.name} <b>${value}</b></span>`;
      });
      legend.innerHTML = `<time>${date}</time>${items.join("")}`;
    };
    chart.subscribeCrosshairMove(draw);
    draw(null);

    // 기간 단추
    const times = main.cfg.data.map((d) => d[0]);
    const first = times[0];
    const lastDay = times[times.length - 1];
    // 가로축에 놓이는 날짜 수(모든 선의 날짜를 합친 것)
    const total = new Set(cfg.series.flatMap((s) => s.data.map((d) => d[0]))).size;
    let from = null; // 고른 기간의 시작일. null이면 전체
    const apply = () => {
      if (from) {
        chart.timeScale().setVisibleRange({ from, to: lastDay });
      } else {
        // 전체 구간을 보여 주되, 양 끝의 표시 글자가 잘리지 않게 조금 띄운다
        chart.timeScale().setVisibleLogicalRange({ from: -Math.ceil(total * 0.045), to: total - 1 + Math.ceil(total * 0.02) });
      }
    };
    // 차트 폭이 정해지거나 바뀔 때마다 구간을 다시 맞춘다
    chart.timeScale().subscribeSizeChange(apply);
    root.querySelectorAll(".chart-range button").forEach((btn) => {
      const months = Number(btn.dataset.months || 0);
      if (months) {
        const d = new Date(lastDay + "T00:00:00Z");
        d.setUTCMonth(d.getUTCMonth() - months);
        const start = d.toISOString().slice(0, 10);
        if (start <= first) {
          btn.hidden = true; // 자료가 그만큼 길지 않으면 단추를 숨긴다
          return;
        }
        btn.dataset.from = start;
      }
      btn.addEventListener("click", () => {
        root.querySelectorAll(".chart-range button").forEach((b) => b.classList.remove("on"));
        btn.classList.add("on");
        from = btn.dataset.from || null;
        apply();
      });
    });
    apply();
  });
})();
