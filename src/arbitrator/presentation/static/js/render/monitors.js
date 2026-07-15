let monitorsWs = null;
let historicalOpps = [];
let activeMonitors = {};
let activeCardWs = {}; // Track ws clients per card // Track monitors from server
let monitorsInitialized = false;

function initMonitors() {
  if (monitorsInitialized) return;
  monitorsInitialized = true;

  const toggle = document.getElementById("hs-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const body = document.getElementById("hist-screener-body");
      const chevron = document.getElementById("hs-chevron");
      if (!body) return;
      body.classList.toggle("is-collapsed");
      if (chevron) chevron.textContent = body.classList.contains("is-collapsed") ? "▶" : "▼";
    });
  }

  const startBtn = document.getElementById("hs-btn-start");
  if (startBtn) {
    startBtn.addEventListener("click", () => sendMonitorCmd("start", null));
  }

  const stopBtn = document.getElementById("hs-btn-stop");
  if (stopBtn) {
    stopBtn.addEventListener("click", () => sendMonitorCmd("stop", null));
  }

  ["hs-filter-lookback", "hs-filter-spread", "hs-filter-vol"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", sendFilterUpdate);
  });
}

function sendFilterUpdate() {
  const lookback = document.getElementById("hs-filter-lookback")?.value;
  const spread = document.getElementById("hs-filter-spread")?.value;
  const vol = document.getElementById("hs-filter-vol")?.value;

  if (monitorsWs && monitorsWs.readyState === WebSocket.OPEN) {
    monitorsWs.send(
      JSON.stringify({
        cmd: "update_filters",
        lookback_seconds: lookback,
        min_spread_pct: spread,
        min_volume_usdt: vol,
      })
    );
  }
}

function startMonitorsWs() {
  if (monitorsWs && (monitorsWs.readyState === WebSocket.OPEN || monitorsWs.readyState === WebSocket.CONNECTING)) {
    return;
  }
  if (monitorsWs) {
    monitorsWs.onclose = null;
    monitorsWs.close();
    monitorsWs = null;
  }

  const loc = window.location;
  const wsUri = (loc.protocol === "https:" ? "wss:" : "ws:") + "//" + loc.host + "/ws/historical_screener";
  monitorsWs = new WebSocket(wsUri);

  monitorsWs.onopen = () => {
    sendFilterUpdate();
  };

  monitorsWs.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "historical_screener_update") {
        historicalOpps = msg.data.opportunities || [];
        const statusEl = document.getElementById("hs-status");
        if (statusEl) statusEl.innerText = msg.data.status || "Idle";
        renderHistTable();

        // Sync active monitors from backend
        if (msg.data.monitors) {
          syncMonitorsFromServer(msg.data.monitors);
          if (msg.data.live_state) {
             applyLiveStateToMonitors(msg.data.live_state, msg.data.monitors);
          }
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  monitorsWs.onclose = () => {
    monitorsWs = null;
    setTimeout(() => {
      if (AppState.activePage === "monitors") startMonitorsWs();
    }, 2000);
  };
}

function stopMonitorsWs() {
  if (monitorsWs) {
    monitorsWs.onclose = null;
    monitorsWs.close();
    monitorsWs = null;
  }
}

function sendMonitorCmd(cmd, symbol, extraData = {}) {
  if (monitorsWs && monitorsWs.readyState === WebSocket.OPEN) {
    monitorsWs.send(JSON.stringify({ cmd, symbol, ...extraData }));
  }
}

function sendUpdateConfig(symbol, configUpdates) {
  sendMonitorCmd("update_config", symbol, { config: configUpdates });
}

function fmtPct(v, digits) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

function fmtPrice(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(5) : "—";
}

function fmtVol(v) {
  const n = Number(v);
  return Number.isFinite(n) ? "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : "—";
}

function fmtNextFunding(unixSec) {
  const sec = Number(unixSec);
  if (!Number.isFinite(sec) || sec <= 0) return "—";
  const target = new Date(sec * 1000);
  if (Number.isNaN(target.getTime())) return "—";
  const diffMs = target.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const h = Math.floor(abs / 3600000);
  const m = Math.floor((abs % 3600000) / 60000);
  const s = Math.floor((abs % 60000) / 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const countdown = `${pad(h)}:${pad(m)}:${pad(s)}`;
  const clock = target.toLocaleTimeString("en-US", { hour12: false });
  return diffMs >= 0 ? `${clock} (${countdown})` : `${clock} (-${countdown})`;
}

function renderHistTable() {
  const tbody = document.getElementById("hist-tbody");
  if (!tbody) return;

  historicalOpps.sort((a, b) => (b.current_spread_pct || 0) - (a.current_spread_pct || 0));

  if (historicalOpps.length === 0) {
    tbody.innerHTML =
      '<tr class="empty-row"><td colspan="8">No opportunities match the filters. Click Start Monitoring.</td></tr>';
    return;
  }

  let html = "";
  for (let i = 0; i < historicalOpps.length; i++) {
    const opp = historicalOpps[i];
    const sf = fmtPct(opp.short_funding_rate, 3);
    const lf = fmtPct(opp.long_funding_rate, 3);
    const fSpread = fmtPct(Math.abs((opp.short_funding_rate || 0) - (opp.long_funding_rate || 0)), 3);

    html += `
      <tr>
        <td>
          <strong>${opp.symbol}</strong><br>
          <span class="muted">Δ: ${fmtPct(opp.current_spread_pct, 2)}% → exit ${fmtPct(opp.max_historical_spread_pct, 2)}%</span>
        </td>
        <td>
           <span class="neg">${String(opp.short_ex || "").toUpperCase()} ↓</span><br>
           <span class="pos">${String(opp.long_ex || "").toUpperCase()} ↑</span>
        </td>
        <td>
           <span class="pos">${sf}%</span><br>
           <span class="neg">${lf}%</span>
        </td>
        <td class="muted">
          ${fmtNextFunding(opp.short_next_funding)}<br>
          ${fmtNextFunding(opp.long_next_funding)}
        </td>
        <td>${fSpread}%</td>
        <td>
          ${fmtPrice(opp.short_price)}<br>
          ${fmtPrice(opp.long_price)}
        </td>
        <td>
          ${fmtVol(opp.short_volume_24h)}<br>
          ${fmtVol(opp.long_volume_24h)}
        </td>
        <td class="hs-th-action">
          <button class="btn btn-secondary btn-row-action" type="button" data-hs-action="copy" data-idx="${i}">Copy to Form</button><br>
          <button class="btn btn-primary btn-row-action" type="button" data-hs-action="fast" data-idx="${i}">Fast Trade</button>
        </td>
      </tr>
    `;
  }
  tbody.innerHTML = html;
}

function onHistTableClick(event) {
  const btn = event.target.closest("[data-hs-action]");
  if (!btn) return;
  const idx = Number(btn.getAttribute("data-idx"));
  if (!Number.isInteger(idx) || idx < 0 || idx >= historicalOpps.length) return;
  const opp = historicalOpps[idx];

  sendMonitorCmd("add_monitor", opp.symbol, {
    short_ex: opp.short_ex,
    long_ex: opp.long_ex,
    max_spread: opp.max_historical_spread_pct
  });

  if (btn.getAttribute("data-hs-action") === "fast") {
      setTimeout(() => {
          sendUpdateConfig(opp.symbol, { is_active: true });
      }, 300);
  }
}

function syncMonitorsFromServer(monitorsArray) {
  const grid = document.getElementById("monitors-grid");
  if (!grid) return;

  const currentSymbols = new Set(monitorsArray.map(m => m.symbol));

  Object.keys(activeMonitors).forEach(symbol => {
    if (!currentSymbols.has(symbol)) {
      const cardEl = document.getElementById(`monitor-card-${symbol.replace(/[^a-zA-Z0-9]/g, "_")}`);
      if (cardEl) cardEl.remove();
      delete activeMonitors[symbol];
    }
  });

  monitorsArray.forEach(config => {
    const cardId = `monitor-card-${config.symbol.replace(/[^a-zA-Z0-9]/g, "_")}`;
    let cardEl = document.getElementById(cardId);

    if (!cardEl) {
      const tpl = document.getElementById("live-card-template");
      if (!tpl) return;
      const clone = tpl.content.cloneNode(true);
      cardEl = clone.querySelector(".live-card");
      cardEl.id = cardId;

      const closeBtn = document.createElement("button");
      closeBtn.innerHTML = "×";
      closeBtn.style.cssText = "position: absolute; top: 12px; right: 16px; background: transparent; border: none; color: #9ca3af; font-size: 1.5em; cursor: pointer;";
      closeBtn.addEventListener("click", () => {
        sendMonitorCmd("remove", config.symbol);
      });
      cardEl.style.position = "relative";
      cardEl.appendChild(closeBtn);

      setupCardListeners(cardEl, config.symbol);
      grid.appendChild(cardEl);
      activeMonitors[config.symbol] = true;
    }

    updateCardUI(cardEl, config);
  });
}

function setupCardListeners(cardEl, symbol) {
  const bindInput = (selector, configKey, isFloat = true) => {
    const el = cardEl.querySelector(selector);
    if (el) {
      el.addEventListener("change", () => {
        const val = isFloat ? parseFloat(el.value) : parseInt(el.value);
        if (!isNaN(val)) sendUpdateConfig(symbol, { [configKey]: val });
      });
    }
  };

  bindInput(".lc-param-open-spread", "open_spread_pct");
  bindInput(".lc-param-open-t", "open_ticks", false);
  bindInput(".lc-param-close-spread", "close_spread_pct");
  bindInput(".lc-param-close-t", "close_ticks", false);
  bindInput(".lc-param-order-size", "order_size_usdt");
  bindInput(".lc-param-max-orders", "max_orders", false);

  const bindCheckbox = (selector, configKey) => {
    const el = cardEl.querySelector(selector);
    if (el) {
      el.addEventListener("change", () => {
        sendUpdateConfig(symbol, { [configKey]: el.checked });
      });
    }
  };
  bindCheckbox(".lc-param-force-stop", "force_stop");
  bindCheckbox(".lc-param-total-stop", "total_stop");

  const btnStart = cardEl.querySelector(".lc-btn-start");
  if (btnStart) btnStart.addEventListener("click", () => sendUpdateConfig(symbol, { is_active: true }));

  const btnStop = cardEl.querySelector(".lc-btn-stop");
  if (btnStop) btnStop.addEventListener("click", () => sendUpdateConfig(symbol, { is_active: false }));

  const sideAuto = cardEl.querySelector(".lc-param-side-auto");
  const sideLong = cardEl.querySelector(".lc-param-side-long");
  const sideShort = cardEl.querySelector(".lc-param-side-short");

  if (sideAuto) sideAuto.addEventListener("click", () => sendUpdateConfig(symbol, { side: "auto" }));
  if (sideLong) sideLong.addEventListener("click", () => sendUpdateConfig(symbol, { side: "long" }));
  if (sideShort) sideShort.addEventListener("click", () => sendUpdateConfig(symbol, { side: "short" }));
}

function updateCardUI(cardEl, config) {
  const symbolEl = cardEl.querySelector(".lc-symbol");
  if (symbolEl) symbolEl.textContent = config.symbol.split("/")[0];

  const ex1 = cardEl.querySelector(".lc-ex1-name-header");
  if (ex1) ex1.textContent = String(config.short_ex || "").toUpperCase();
  const ex1col = cardEl.querySelector(".lc-ex1-name-col");
  if (ex1col) ex1col.textContent = String(config.short_ex || "").toUpperCase();

  const ex2 = cardEl.querySelector(".lc-ex2-name-header");
  if (ex2) ex2.textContent = String(config.long_ex || "").toUpperCase();
  const ex2col = cardEl.querySelector(".lc-ex2-name-col");
  if (ex2col) ex2col.textContent = String(config.long_ex || "").toUpperCase();

  const safeUpdateInput = (selector, val) => {
    const el = cardEl.querySelector(selector);
    if (el && document.activeElement !== el) el.value = val;
  };

  safeUpdateInput(".lc-param-open-spread", config.open_spread_pct);
  safeUpdateInput(".lc-param-open-t", config.open_ticks);
  safeUpdateInput(".lc-param-close-spread", config.close_spread_pct);
  safeUpdateInput(".lc-param-close-t", config.close_ticks);
  safeUpdateInput(".lc-param-order-size", config.order_size_usdt);
  safeUpdateInput(".lc-param-max-orders", config.max_orders);

  const forceEl = cardEl.querySelector(".lc-param-force-stop");
  if (forceEl) forceEl.checked = config.force_stop;
  const totalEl = cardEl.querySelector(".lc-param-total-stop");
  if (totalEl) totalEl.checked = config.total_stop;

  const sideAuto = cardEl.querySelector(".lc-param-side-auto");
  const sideLong = cardEl.querySelector(".lc-param-side-long");
  const sideShort = cardEl.querySelector(".lc-param-side-short");

  const setActiveSide = (activeBtn) => {
    [sideAuto, sideLong, sideShort].forEach(btn => {
      if (btn) {
        btn.style.background = "transparent";
        btn.style.color = "#9ca3af";
        btn.innerHTML = btn.textContent.replace(" ✓", "");
      }
    });
    if (activeBtn) {
      activeBtn.style.background = "#10b981";
      activeBtn.style.color = "white";
      activeBtn.innerHTML += ' <span style="font-size: 0.8em;">✓</span>';
    }
  };

  if (config.side === "long") setActiveSide(sideLong);
  else if (config.side === "short") setActiveSide(sideShort);
  else setActiveSide(sideAuto);

  const btnStart = cardEl.querySelector(".lc-btn-start");
  const btnStop = cardEl.querySelector(".lc-btn-stop");
  if (btnStart && btnStop) {
      if (config.is_active) {
          btnStart.style.opacity = "0.5";
          btnStart.style.pointerEvents = "none";
          btnStop.style.opacity = "1";
          btnStop.style.pointerEvents = "auto";
          cardEl.style.border = "1px solid #10b981";
      } else {
          btnStart.style.opacity = "1";
          btnStart.style.pointerEvents = "auto";
          btnStop.style.opacity = "0.5";
          btnStop.style.pointerEvents = "none";
          cardEl.style.border = "1px solid #1e293b";
      }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("hist-tbody");
  if (tbody) tbody.addEventListener("click", onHistTableClick);
});

window.initMonitors = initMonitors;
window.startMonitorsWs = startMonitorsWs;
window.stopMonitorsWs = stopMonitorsWs;


function startCardWs(cardEl, config) {
  const symbol = config.symbol;
  if (activeCardWs[symbol]) return;

  const q = new URLSearchParams({
    symbol: config.symbol,
    short: config.short_ex,
    long: config.long_ex,
  });
  const url = `/ws/opportunity?${q.toString()}`;

  const client = new window.WsClient(url, {
    onMessage: (msg) => {
      if (msg.type === "opportunity.snapshot") {
        updateCardLiveState(cardEl, msg.payload, config);
      } else if (msg.type === "opportunity.delta") {
        // Delta can be handled for chart updates
      }
    }
  });
  activeCardWs[symbol] = client;
}

function stopCardWs(symbol) {
  if (activeCardWs[symbol]) {
    activeCardWs[symbol].close();
    delete activeCardWs[symbol];
  }
}

function updateCardLiveState(cardEl, payload, config) {
  if (!payload || !payload.exchange_cards) return;

  // 1. Funding & Countdown
  payload.exchange_cards.forEach(card => {
    const isShort = card.side === "short";
    const prefix = isShort ? ".lc-ex1" : ".lc-ex2";
    const exFund = cardEl.querySelector(`${prefix}-funding`);
    if (exFund) {
      exFund.textContent = card.funding_rate_pct != null ? `${card.funding_rate_pct.toFixed(3)}%` : "—";
      exFund.style.color = card.funding_rate_pct < 0 ? "#ef4444" : "#10b981";
    }
    const nextFund = cardEl.querySelector(`${prefix}-next-fund`);
    if (nextFund && card.funding_countdown_sec != null) {
      const h = Math.floor(card.funding_countdown_sec / 3600);
      const m = Math.floor((card.funding_countdown_sec % 3600) / 60);
      nextFund.textContent = `${h}h ${m}m`;
    }
    const leverage = cardEl.querySelector(`${prefix}-leverage-display`);
    if (leverage) leverage.textContent = `${card.leverage}x`;
  });

  // 2. Orderbook Top
  if (payload.books) {
    payload.books.forEach(book => {
      const isShort = book.side_role === "short";
      const prefix = isShort ? ".lc-ex1" : ".lc-ex2";

      const bestAsk = book.asks && book.asks.length > 0 ? book.asks[book.asks.length - 1] : null;
      const bestBid = book.bids && book.bids.length > 0 ? book.bids[0] : null;

      const askEl = cardEl.querySelector(`${prefix}-ask`);
      if (askEl && bestAsk) askEl.textContent = bestAsk.price.toFixed(5);
      const bidEl = cardEl.querySelector(`${prefix}-bid`);
      if (bidEl && bestBid) bidEl.textContent = bestBid.price.toFixed(5);
      const sizeEl = cardEl.querySelector(`${prefix}-size`);
      if (sizeEl && bestAsk) {
        sizeEl.textContent = bestAsk.amount.toFixed(2);
      }
    });
  }

  // 3. Current Spread & Strategy stats
  const activeStrategyId = payload.params?.active_strategy_id || "futures_futures";
  const stratRow = payload.strategy_rows ? payload.strategy_rows.find(r => r.strategy_id === activeStrategyId) : null;
  if (stratRow) {
    const openCurr = cardEl.querySelector(".lc-track-open-curr");
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
    }

    // For now, let's just populate the short side PnL / execution price with mock or real if available
    const execPrice1 = cardEl.querySelector(".lc-ex1-exec-price");
    if (execPrice1) execPrice1.textContent = stratRow.prices_label.split(" / ")[0] || "—";
    const execPrice2 = cardEl.querySelector(".lc-ex2-exec-price");
    if (execPrice2) execPrice2.textContent = stratRow.prices_label.split(" / ")[1] || "—";

    const pnl1 = cardEl.querySelector(".lc-ex1-pnl");
    if (pnl1) pnl1.textContent = stratRow.net_profit_usdt != null ? stratRow.net_profit_usdt.toFixed(2) : "—";
  }
}


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


function applyLiveStateToMonitors(liveState, monitorsArray) {
  monitorsArray.forEach(config => {
    const symbol = config.symbol;
    const state = liveState[symbol];
    if (!state) return;

    const cardId = `monitor-card-${symbol.replace(/[^a-zA-Z0-9]/g, "_")}`;
    const cardEl = document.getElementById(cardId);
    if (!cardEl) return;

    // Spread text
    const openCurr = cardEl.querySelector(".lc-track-open-curr");
    if (openCurr) openCurr.textContent = fmtPct(state.open_spread, 3);
    const closeCurr = cardEl.querySelector(".lc-track-close-curr");
    if (closeCurr) closeCurr.textContent = fmtPct(state.close_spread, 3);

    // T-logic visual feedback
    const renderTLogic = (selector, currentTicks, maxTicks) => {
      const parent = cardEl.querySelector(selector);
      if (!parent) return;
      // We will append a small progress badge next to the input
      let badge = parent.querySelector(".t-badge");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "t-badge";
        badge.style.cssText = "position: absolute; right: -30px; top: 50%; transform: translateY(-50%); font-size: 0.8em; font-weight: bold; background: #374151; padding: 2px 4px; border-radius: 4px;";
        parent.appendChild(badge);
      }
      if (currentTicks > 0) {
        badge.textContent = `${currentTicks}/${maxTicks}`;
        badge.style.color = currentTicks >= maxTicks ? "#10b981" : "#f59e0b";
      } else {
        badge.textContent = "";
      }
    };

    renderTLogic(".lc-param-open-t", state.open_ticks, config.open_ticks);
    renderTLogic(".lc-param-close-t", state.close_ticks, config.close_ticks);

    // Chart
    if (!cardEl._monitorChart) {
      const canvas = cardEl.querySelector(".lc-chart-canvas");
      if (canvas) {
        cardEl._monitorChart = new MonitorCardChart(canvas);
      }
    }
    if (cardEl._monitorChart) {
      cardEl._monitorChart.addPoint(state.open_spread, state.close_spread);
    }

    // Status text (Orders)
    const ex1Orders = cardEl.querySelector(".lc-ex1-orders");
    if (ex1Orders) ex1Orders.textContent = state.open_orders;
  });
}
