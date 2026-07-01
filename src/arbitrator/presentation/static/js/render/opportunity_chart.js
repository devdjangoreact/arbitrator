const OpportunityChart = (() => {
  const canvas = () => document.getElementById("liveChart");
  const chartPad = { top: 10, right: 14, bottom: 24, left: 58 };
  const gridColor = "#e8e6e1";
  const axisColor = "#9c9a92";
  const gridStepSec = 5;
  const gridRows = 12;

  /** @type {Array<{ key: string, tag: string, color: string, dash: boolean, el: string, data: number[], exchangeId: string, marketType: string, lastPrice: number | null }>} */
  let chartSeries = [];
  /** @type {Record<string, string>} */
  let legendMap = {};
  let chartWindowSec = 60;
  let maxPoints = 61;

  function fmtPrice(v) {
    return v >= 10 ? v.toFixed(2) : v.toFixed(5);
  }

  function chartResize() {
    const c = canvas();
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const w = c.clientWidth;
    const h = c.clientHeight;
    if (!w || !h) return;
    c.width = w * devicePixelRatio;
    c.height = h * devicePixelRatio;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(devicePixelRatio, devicePixelRatio);
  }

  function chartBounds() {
    const all = chartSeries.flatMap((s) => s.data);
    if (!all.length) return { lo: 0, hi: 1 };
    const min = Math.min(...all);
    const max = Math.max(...all);
    const range = max - min || 0.0001;
    const pad = Math.max(range * 0.15, 0.00008);
    return { lo: min - pad, hi: max + pad };
  }

  function priceToY(price, lo, hi, plot) {
    return plot.y + plot.h - ((price - lo) / (hi - lo)) * plot.h;
  }

  function seriesLabelText(s) {
    const last = s.lastPrice ?? s.data[s.data.length - 1];
    const ex = (s.exchangeId || "").toUpperCase();
    const m = s.marketType === "spot" ? "S" : "F";
    return `${fmtPrice(last)} ${ex} ${m}`;
  }

  function layoutLineLabels(plot, lo, hi) {
    const minGap = 13;
    const labels = chartSeries
      .filter((s) => s.data.length > 0)
      .map((s) => {
        const last = s.lastPrice ?? s.data[s.data.length - 1];
        const lx = plot.x + plot.w;
        const ly = priceToY(last, lo, hi, plot);
        return { s, last, lx, ly };
      });
    labels.sort((a, b) => a.ly - b.ly);
    for (let i = 1; i < labels.length; i++) {
      if (labels[i].ly - labels[i - 1].ly < minGap) {
        labels[i].ly = labels[i - 1].ly + minGap;
      }
    }
    for (let i = labels.length - 2; i >= 0; i--) {
      if (labels[i].ly > labels[i + 1].ly - minGap) {
        labels[i].ly = labels[i + 1].ly - minGap;
      }
    }
    const top = plot.y + 6;
    const bottom = plot.y + plot.h - 6;
    for (const item of labels) {
      if (item.ly < top) item.ly = top;
      if (item.ly > bottom) item.ly = bottom;
    }
    return labels;
  }

  function drawLineLabels(ctx, labels) {
    const font = '9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif';
    ctx.font = font;
    for (const { s, lx, ly } of labels) {
      const text = seriesLabelText(s);
      const padX = 4;
      const tw = ctx.measureText(text).width;
      const th = 11;
      const boxW = tw + padX * 2;
      const boxH = th + 4;
      const bx = lx - boxW - 8;
      const by = ly - boxH / 2;
      ctx.fillStyle = "rgba(255,255,255,0.94)";
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") {
        ctx.roundRect(bx, by, boxW, boxH, 3);
      } else {
        ctx.rect(bx, by, boxW, boxH);
      }
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = s.color;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(text, bx + padX, ly);
      ctx.beginPath();
      ctx.arc(lx, ly, 3, 0, Math.PI * 2);
      ctx.fillStyle = s.color;
      ctx.fill();
    }
  }

  function drawGrid(ctx, lo, hi, plot) {
    const { x, y, w, h } = plot;
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.fillStyle = axisColor;
    ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif';
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i < gridRows; i++) {
      const t = i / (gridRows - 1);
      const py = y + h - t * h;
      const price = lo + t * (hi - lo);
      ctx.beginPath();
      ctx.moveTo(x, py);
      ctx.lineTo(x + w, py);
      ctx.stroke();
      ctx.fillText(fmtPrice(price), x - 6, py);
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let sec = 0; sec <= chartWindowSec; sec += gridStepSec) {
      const px = x + (1 - sec / chartWindowSec) * w;
      ctx.beginPath();
      ctx.moveTo(px, y);
      ctx.lineTo(px, y + h);
      ctx.stroke();
      ctx.fillText(sec === 0 ? "зараз" : `−${sec}с`, px, y + h + 5);
    }
    ctx.strokeStyle = "#cfccc4";
    ctx.strokeRect(x, y, w, h);
  }

  function chartDraw() {
    const c = canvas();
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const w = c.clientWidth;
    const h = c.clientHeight;
    if (!w || !h) return;
    ctx.clearRect(0, 0, w, h);
    const plot = {
      x: chartPad.left,
      y: chartPad.top,
      w: w - chartPad.left - chartPad.right,
      h: h - chartPad.top - chartPad.bottom,
    };
    if (plot.w <= 0 || plot.h <= 0) return;
    const { lo, hi } = chartBounds();
    drawGrid(ctx, lo, hi, plot);
    for (const s of chartSeries) {
      if (s.data.length < 1) continue;
      const denom = Math.max(s.data.length - 1, 1);
      ctx.beginPath();
      ctx.setLineDash(s.dash ? [5, 4] : []);
      s.data.forEach((v, i) => {
        const px = plot.x + (i / denom) * plot.w;
        const py = priceToY(v, lo, hi, plot);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = s.color;
      ctx.lineWidth = s.dash ? 1.4 : 2;
      ctx.stroke();
      ctx.setLineDash([]);
    }
    const labels = layoutLineLabels(plot, lo, hi);
    drawLineLabels(ctx, labels);
  }

  /** @param {object[]} series */
  function renderLegend(series) {
    const legend = Dom.opportunity.chartLegend();
    if (!legend) return;
    legend.innerHTML =
      series
        .map((s) => {
          const styleAttr = s.dashed ? ` style="color:${s.color}"` : ` style="background:${s.color}"`;
          const swatchTag = s.dashed
            ? `<i class="swatch dash"${styleAttr}></i>`
            : `<i class="swatch"${styleAttr}></i>`;
          return `<span>${swatchTag}${s.label} <span class="price" id="ch-${s.key}">${fmtPrice(s.last_price)}</span></span>`;
        })
        .join("") + '<span class="faint" style="margin-left:auto;">реальний час</span>';
    series.forEach((s) => {
      legendMap[s.key] = `ch-${s.key}`;
    });
  }

  /** @param {object} chartPayload */
  function updateFromSnapshot(chartPayload) {
    if (!chartPayload || !chartPayload.series) return;
    chartWindowSec = Number(chartPayload.window_seconds) || chartWindowSec;
    const longest = chartPayload.series.reduce(
      (max, s) => Math.max(max, (s.points || []).length),
      1
    );
    maxPoints = Math.max(longest, 2);
    chartSeries = chartPayload.series.map((s) => ({
      key: s.key,
      tag: s.label,
      color: s.color,
      dash: !!s.dashed,
      el: `ch-${s.key}`,
      exchangeId: s.exchange_id || "",
      marketType: s.market_type || "futures",
      lastPrice: s.last_price ?? null,
      data: (s.points || []).map((p) => p.price),
    }));
    renderLegend(chartPayload.series);
    chartResize();
    chartDraw();
  }

  /** @param {object[]} seriesDelta */
  function applyDelta(seriesDelta) {
    if (!seriesDelta?.length) return;
    for (const item of seriesDelta) {
      let series = chartSeries.find((s) => s.key === item.key);
      if (!series) {
        series = {
          key: item.key,
          tag: item.key,
          color: "#999",
          dash: false,
          el: `ch-${item.key}`,
          exchangeId: "",
          marketType: "futures",
          lastPrice: null,
          data: [],
        };
        chartSeries.push(series);
      }
      if (item.point) {
        series.data.push(item.point.price);
        if (series.data.length > maxPoints) series.data.shift();
      }
      if (item.last_price != null) {
        series.lastPrice = item.last_price;
        const el = document.getElementById(legendMap[item.key] || `ch-${item.key}`);
        if (el) el.textContent = fmtPrice(item.last_price);
      }
    }
    chartDraw();
  }

  window.addEventListener("resize", () => {
    chartResize();
    chartDraw();
  });

  return { chartResize, chartDraw, updateFromSnapshot, applyDelta };
})();

window.OpportunityChart = OpportunityChart;
