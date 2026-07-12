import re

chart_logic = """
class MonitorCardChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.history = []; // { t, open_spread, close_spread }
    this.maxPoints = 60;
  }

  addPoint(openSpread, closeSpread) {
    this.history.push({ t: Date.now(), o: openSpread, c: closeSpread });
    if (this.history.length > this.maxPoints) {
      this.history.shift();
    }
    this.draw();
  }

  draw() {
    if (this.history.length === 0) return;
    const w = this.canvas.width = this.canvas.offsetWidth || 400;
    const h = this.canvas.height = this.canvas.offsetHeight || 100;
    const ctx = this.ctx;

    ctx.clearRect(0, 0, w, h);

    // Find bounds
    let minVal = Number.MAX_VALUE;
    let maxVal = -Number.MAX_VALUE;
    for (let p of this.history) {
      if (p.o < minVal) minVal = p.o;
      if (p.o > maxVal) maxVal = p.o;
      if (p.c < minVal) minVal = p.c;
      if (p.c > maxVal) maxVal = p.c;
    }
    if (minVal === maxVal) { minVal -= 1; maxVal += 1; }
    const padding = (maxVal - minVal) * 0.1;
    minVal -= padding; maxVal += padding;
    const range = maxVal - minVal;

    const getX = (index) => (index / (this.maxPoints - 1)) * w;
    const getY = (val) => h - ((val - minVal) / range) * h;

    const drawLine = (key, color) => {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      for (let i = 0; i < this.history.length; i++) {
        const x = getX(i + (this.maxPoints - this.history.length));
        const y = getY(this.history[i][key]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    };

    // Close spread (red)
    drawLine('c', '#ef4444');
    // Open spread (green)
    drawLine('o', '#10b981');
  }
}
"""

with open("src/arbitrator/presentation/static/js/render/monitors.js", "r", encoding="utf-8") as f:
    content = f.read()

if "class MonitorCardChart" not in content:
    content += "\n" + chart_logic

# Hook it up in updateCardLiveState
replace_target = """    const openCurr = cardEl.querySelector(".lc-track-open-curr");
    if (openCurr) openCurr.textContent = stratRow.spread_pct.toFixed(3);"""

new_target = """    const openCurr = cardEl.querySelector(".lc-track-open-curr");
    if (openCurr) openCurr.textContent = stratRow.spread_pct.toFixed(3);

    const closeSpreadTarget = config.close_spread_pct || 0; // Using config target or could be from strat

    if (!cardEl._monitorChart) {
      const canvas = cardEl.querySelector(".lc-chart-canvas");
      if (canvas) {
        cardEl._monitorChart = new MonitorCardChart(canvas);
      }
    }
    if (cardEl._monitorChart) {
      cardEl._monitorChart.addPoint(stratRow.spread_pct, closeSpreadTarget);
    }"""

if "cardEl._monitorChart = new MonitorCardChart" not in content:
    content = content.replace(replace_target, new_target)

with open("src/arbitrator/presentation/static/js/render/monitors.js", "w", encoding="utf-8") as f:
    f.write(content)
