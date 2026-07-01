const SCREENER_EXCHANGES = ["mexc", "bitget", "gate", "bingx"];

const STRATEGY_KEYS = [
  "futures_futures",
  "futures_spot_2ex",
  "futures_spot_1ex",
  "funding_ff",
  "funding_fs",
  "funding_diff_dates",
];

/** @param {object} row */
function buildScreenerRow(row) {
  const tr = document.createElement("tr");
  tr.dataset.asset = row.asset;

  const assetTd = document.createElement("td");
  assetTd.textContent = row.asset;
  tr.appendChild(assetTd);

  for (const ex of SCREENER_EXCHANGES) {
    const prices = row.prices && row.prices[ex] ? row.prices[ex] : {};
    const futTd = document.createElement("td");
    futTd.className = "num fut-col";
    futTd.textContent = fmtNum(prices.futures);
    tr.appendChild(futTd);
    const spotTd = document.createElement("td");
    spotTd.className = "num spot-col";
    spotTd.textContent = fmtNum(prices.spot);
    tr.appendChild(spotTd);
  }

  const spreadCls = row.spread_pct >= 0 ? "pos" : "neg";
  const deltaCls = row.spread_delta > 0 ? "pos" : row.spread_delta < 0 ? "neg" : "";
  const cells = [
    ["num", fmtNum(row.max_price)],
    ["num", fmtNum(row.min_price)],
    [`num ${spreadCls}`, fmtNum(row.spread_pct, 2)],
    [`num ${deltaCls}`, row.spread_delta > 0 ? `+${fmtNum(row.spread_delta, 2)}` : fmtNum(row.spread_delta, 2)],
    ["num", fmtNum(row.volume_k_usdt, 0)],
  ];
  for (const [cls, text] of cells) {
    const td = document.createElement("td");
    td.className = cls;
    td.textContent = text;
    tr.appendChild(td);
  }

  const profits = row.strategy_profits || {};
  for (const key of STRATEGY_KEYS) {
    const val = profits[key];
    const td = document.createElement("td");
    const isNa = val === null || val === undefined;
    td.className = isNa ? "num na" : `num ${val >= 0 ? "pos" : "neg"}`;
    td.textContent = fmtStrategyProfit(val, 2);
    tr.appendChild(td);
  }

  const actionTd = document.createElement("td");
  const btn = document.createElement("button");
  btn.className = "btn btn-primary btn-row-action";
  btn.type = "button";
  btn.textContent = "Open Opportunity";
  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    const latest =
      AppState.screenerSnapshot?.rows?.find((candidate) => candidate.asset === row.asset) ?? row;
    if (typeof navigateToOpportunity === "function") {
      navigateToOpportunity({
        symbol: latest.asset,
        short_exchange_id: latest.short_exchange_id,
        long_exchange_id: latest.long_exchange_id,
      });
    }
    if (typeof ensureOpportunityWs === "function") {
      ensureOpportunityWs(true);
    }
  });
  actionTd.appendChild(btn);
  tr.appendChild(actionTd);
  return tr;
}

let _screenerFiltersSynced = false;

/** @returns {{ min_volume_k_usdt: number, min_spread_pct: number }} */
function readScreenerClientFilters() {
  return {
    min_volume_k_usdt: parseFloat(Dom.screener.filterMinVolume()?.value || "0") || 0,
    min_spread_pct: parseFloat(Dom.screener.filterMinSpread()?.value || "0") || 0,
  };
}

/** @param {object} row @param {{ min_volume_k_usdt: number, min_spread_pct: number }} filters */
function screenerRowPassesClientFilter(row, filters) {
  return row.volume_k_usdt >= filters.min_volume_k_usdt && row.spread_pct >= filters.min_spread_pct;
}

/** @param {object[] | null | undefined} rows */
function filterScreenerRows(rows) {
  const filters = readScreenerClientFilters();
  return (rows || []).filter((row) => screenerRowPassesClientFilter(row, filters));
}

/** @param {object[]} rows */
function renderScreenerTableBody(rows) {
  const tbody = Dom.screener.tbody();
  if (!tbody) return;

  AppState.screenerRowElements.clear();
  tbody.replaceChildren();

  if (!rows.length) {
    const hasStreamedRows = (AppState.screenerSnapshot?.rows || []).length > 0;
    const empty = document.createElement("tr");
    empty.className = "empty-row";
    const td = document.createElement("td");
    td.colSpan = 21;
    td.textContent = hasStreamedRows ? "No rows match filters" : "—";
    empty.appendChild(td);
    tbody.appendChild(empty);
    return;
  }

  for (const row of rows) {
    const tr = buildScreenerRow(row);
    AppState.screenerRowElements.set(row.asset, tr);
    tbody.appendChild(tr);
  }
}

function applyScreenerClientFilter() {
  const snap = AppState.screenerSnapshot;
  if (!snap) return;
  renderScreenerTableBody(filterScreenerRows(snap.rows));
}

/** @param {object | null | undefined} filters */
function syncScreenerFilterInputsOnce(filters) {
  if (_screenerFiltersSynced || !filters) return;
  const streamMinInput = Dom.screener.filterStreamMin();
  if (streamMinInput) streamMinInput.value = Number(filters.stream_min_volume_usdt).toFixed(2);
  _screenerFiltersSynced = true;
}

const SCREENER_CONNECTING_STATUSES = new Set([
  "connecting",
  "Connecting…",
  "Discovering volumes…",
]);

function updateScreenerLoading() {
  const snap = AppState.screenerSnapshot;
  const wsConnected = !!AppState.screenerWsConnected;
  const status = snap?.status || "";
  const loading = !snap || !wsConnected || SCREENER_CONNECTING_STATUSES.has(status);
  let message = "Завантаження даних…";
  if (!wsConnected) {
    message = "Підключення…";
  } else if (status === "connecting" || status === "Connecting…" || status === "Discovering volumes…") {
    message = "Підключення до бірж…";
  }
  setLoadingOverlay("screener-loading", loading, message);
}

function renderScreenerStreamNote(payload) {
  const note = Dom.screener.streamNote();
  if (note) {
    const wsConnected = !!AppState.screenerWsConnected;
    const wsLabel = wsConnected ? "WS connected" : "WS disconnected";
    if (payload) {
      const status = payload.status || "unknown";
      const exchanges = (payload.exchanges || []).join(", ");
      const minVol = payload.filters ? payload.filters.stream_min_volume_usdt : 0;
      let agePart = "";
      if (payload.updated_at) {
        const updated = new Date(payload.updated_at);
        if (!Number.isNaN(updated.getTime())) {
          const ageSec = Math.max(0, Math.round((Date.now() - updated.getTime()) / 1000));
          agePart = ` · updated ${ageSec}s ago`;
        }
      }
      note.textContent = `${wsLabel} · ${status} · ${payload.symbol_count || 0} symbols · Exchanges: ${exchanges} · Stream min volume: ${Number(minVol).toLocaleString()} USDT${agePart}`;
      note.classList.toggle("stream-live", wsConnected && !SCREENER_CONNECTING_STATUSES.has(status));
      note.classList.toggle("stream-stale", !wsConnected || SCREENER_CONNECTING_STATUSES.has(status));
    } else {
      note.textContent = wsLabel;
      note.classList.toggle("stream-live", wsConnected);
      note.classList.toggle("stream-stale", !wsConnected);
    }
  }
  updateScreenerLoading();
}

/** @param {object | null | undefined} payload */
function renderScreenerMeta(payload) {
  renderScreenerStreamNote(payload);
}

/** @param {object} payload */
function renderScreenerSnapshot(payload) {
  AppState.screenerSnapshot = payload;
  if (payload?.default_opportunity) {
    AppState.defaultOpportunityFocus = payload.default_opportunity;
  }
  if (typeof populateFocusOptionLists === "function") {
    populateFocusOptionLists();
  }
  const tbody = Dom.screener.tbody();
  if (!tbody) return;

  syncScreenerFilterInputsOnce(payload?.filters);
  renderScreenerMeta(payload);
  applyScreenerClientFilter();
  if (payload.default_opportunity) {
    AppState.defaultOpportunityFocus = payload.default_opportunity;
    if (!AppState.focusOpportunity?.symbol) {
      AppState.focusOpportunity = payload.default_opportunity;
    }
  }
}

/** @param {object} delta */
function applyScreenerDelta(delta) {
  if (!AppState.screenerSnapshot) return;

  const snap = { ...AppState.screenerSnapshot };
  if (delta.status != null) snap.status = delta.status;
  if (delta.symbol_count != null) snap.symbol_count = delta.symbol_count;
  if (delta.exchanges != null) snap.exchanges = delta.exchanges;
  if (delta.filters != null) snap.filters = delta.filters;

  const rowMap = new Map((snap.rows || []).map((r) => [r.asset, r]));
  for (const asset of delta.rows_removed || []) {
    rowMap.delete(asset);
  }
  for (const row of delta.rows_changed || []) {
    rowMap.set(row.asset, row);
  }
  snap.rows = Array.from(rowMap.values());
  AppState.screenerSnapshot = snap;
  renderScreenerStreamNote(snap);
  applyScreenerClientFilter();
}

/** @type {WsClient | null} */
let _screenerClient = null;

function sendScreenerReconnect() {
  if (!_screenerClient) return;
  _screenerClient.send("screener.reconnect", {
    stream_min_volume_usdt: parseFloat(Dom.screener.filterStreamMin()?.value || "0") || 0,
  });
}

function initScreener() {
  registerDeltaHandler("screener.snapshot", renderScreenerSnapshot);
  registerDeltaHandler("screener.delta", applyScreenerDelta);

  _screenerClient = new WsClient("/ws/screener", {
    onOpen: () => {
      AppState.screenerWsConnected = true;
      renderScreenerMeta(AppState.screenerSnapshot);
      updateScreenerLoading();
    },
    onClose: () => {
      AppState.screenerWsConnected = false;
      renderScreenerMeta(AppState.screenerSnapshot);
      updateScreenerLoading();
    },
  });

  updateScreenerLoading();

  Dom.screener.reconnectBtn()?.addEventListener("click", sendScreenerReconnect);

  Dom.screener.filterBtn()?.addEventListener("click", applyScreenerClientFilter);
}

window.initScreener = initScreener;
