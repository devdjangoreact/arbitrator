/** @type {WsClient | null} */
let _opportunityClient = null;
/** @type {string | null} */
let _opportunityWsUrl = null;
/** @type {string | null} */
let _connectedFocusKey = null;
/** @type {string | null} */
let _paramsInitializedForFocusKey = null;
let _oppOrdersFilter = "open";

function resolveOpportunityFocus() {
  if (AppState.focusOpportunity?.symbol) {
    return AppState.focusOpportunity;
  }
  if (AppState.defaultOpportunityFocus?.symbol) {
    return AppState.defaultOpportunityFocus;
  }
  const row = AppState.screenerSnapshot?.rows?.[0];
  if (row?.asset) {
    return {
      symbol: row.asset,
      short_exchange_id: row.short_exchange_id,
      long_exchange_id: row.long_exchange_id,
    };
  }
  return null;
}

function opportunityWsPathFor(focus) {
  const q = new URLSearchParams({
    symbol: focus.symbol,
    short: focus.short_exchange_id,
    long: focus.long_exchange_id,
  });
  return `/ws/opportunity?${q.toString()}`;
}

/** @param {{ symbol: string, short_exchange_id: string, long_exchange_id: string }} focus */
function opportunityFocusKey(focus) {
  return `${focus.symbol}|${focus.short_exchange_id}|${focus.long_exchange_id}`;
}

/** @param {object} payload */
function snapshotMatchesFocus(payload) {
  if (!_connectedFocusKey) return true;
  const payloadKey = opportunityFocusKey({
    symbol: payload.symbol,
    short_exchange_id: payload.short_exchange_id,
    long_exchange_id: payload.long_exchange_id,
  });
  return payloadKey === _connectedFocusKey;
}

/** @param {number} sec */
function fmtCountdown(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** @param {number | null | undefined} value */
function fmtVolumeCompact(value) {
  if (value == null) return "—";
  const n = Number(value);
  if (Number.isFinite(n) && Math.abs(n - Math.round(n)) < 0.005) {
    return String(Math.round(n));
  }
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** @param {number | null | undefined} min @param {number | null | undefined} max */
function fmtVolumeRange(min, max) {
  return `${fmtVolumeCompact(min)}/${fmtVolumeCompact(max)}`;
}

/** @param {object} card */
function fmtVolumeLimitsLine(card) {
  const fut = `F ${fmtVolumeRange(card.min_order_volume_usdt, card.max_order_volume_usdt)}`;
  const spot = `S ${fmtVolumeRange(card.spot_min_order_volume_usdt, card.spot_max_order_volume_usdt)}`;
  return `${fut} · ${spot}`;
}

/** @param {object[]} rows */
function sortStrategyRowsByPercent(rows) {
  return [...(rows || [])].sort((a, b) => {
    const ap = a.percent_to_deposit;
    const bp = b.percent_to_deposit;
    if (ap == null && bp == null) return 0;
    if (ap == null) return 1;
    if (bp == null) return -1;
    return bp - ap;
  });
}

/** @param {object} row */
function strategyRowTooltip(row) {
  if (row.unavailable_reason) return row.unavailable_reason;
  return "";
}

/** @param {object} row */
function renderStrategyRow(row) {
  const reason = strategyRowTooltip(row);
  const tip = reason ? ` title="${reason}"` : "";
  const naTip = reason ? ` title="${reason}"` : "";
  return `
      <tr>
        <td>${row.strategy_label}</td>
        <td class="num">${fmtNum(row.spread_pct, 2)}%</td>
        <td class="num">${row.prices_label}</td>
        <td class="num">${fmtNum(row.fees_usdt, 2)}</td>
        <td class="num ${pnlClass(row.funding_usdt)}">${fmtPnl(row.funding_usdt)}</td>
        <td class="num">${fmtNum(row.volume_usdt, 2)}</td>
        <td class="num">${row.leverage}x</td>
        <td class="num ${pnlClass(row.gross_profit_usdt)}"${naTip}>${fmtPnlOrNa(row.gross_profit_usdt)}</td>
        <td class="num">${fmtNum(row.costs_usdt, 2)}${row.costs_breakdown && row.costs_breakdown !== "—" ? `<span class="sub-cost">(${row.costs_breakdown})</span>` : ""}</td>
        <td class="num ${pnlClass(row.net_profit_usdt)}"${naTip}>${fmtPnlOrNa(row.net_profit_usdt)}</td>
        <td class="num ${pnlClass(row.percent_to_deposit)}"${tip}>${fmtPercentDeposit(row.percent_to_deposit)}</td>
      </tr>`;
}

/** @param {object} card */
function renderExCard(card) {
  const sideCls = card.side === "short" ? "short" : "long";
  const fund = card.funding_rate_pct;
  const fundCls = fund !== null && fund < 0 ? "fund-red" : "fund-green";
  const fundStr =
    fund !== null ? `${fund >= 0 ? "+" : ""}${Number(fund).toFixed(3)}%` : "—";
  const levOptions = [1, 2, 3, 5, 10, 20, 50, 100]
    .map(
      (l) =>
        `<option value="${l}"${l === card.leverage ? " selected" : ""}>${l}x</option>`
    )
    .join("");
  const nativeId = card.native_market_id || "—";
  return `
    <div class="ex-info-card" data-exchange-id="${card.exchange_id}">
      <div class="ex-info-title">${card.exchange_id.toUpperCase()} <span class="badge ${sideCls}">${card.side}</span></div>
      <div class="ex-info-line"><span>База</span><span>${card.base_asset || "—"}</span></div>
      <div class="ex-info-line"><span>Символ</span><span class="ex-symbol">${card.market_symbol || "—"}</span></div>
      <div class="ex-info-line"><span>ID біржі</span><span class="ex-native-id">${nativeId}</span></div>
      <div class="ex-info-line"><span>Баланс</span><span>${card.balance_usdt != null ? `${Number(card.balance_usdt).toFixed(2)} USDT` : "—"}</span></div>
      <div class="ex-info-line"><span>Фандінг</span><span><span class="${fundCls}">${fundStr}</span> · ${card.funding_countdown_sec != null ? fmtCountdown(card.funding_countdown_sec) : "—"}</span></div>
      <div class="ex-info-line ex-lev"><span>Плече</span>
        <select class="lev-select" data-exchange-id="${card.exchange_id}">${levOptions}</select>
      </div>
      <div class="ex-info-line"><span>Комісія ф'ючерс</span><span class="ex-futures-fee">${card.futures_fee}</span></div>
      <div class="ex-info-line"><span>Комісія спот</span><span class="ex-spot-fee">${card.spot_fee}</span></div>
      <div class="ex-info-line"><span>Обʼєм</span><span class="ex-volume-limits">${fmtVolumeLimitsLine(card)}</span></div>
      <div class="ex-info-line"><span>Ордери</span><span>${card.open_orders_count} відкр. / ${card.closed_orders_count} закр.</span></div>
    </div>`;
}

function syncFocusSelectorsFromPayload(payload, force = false) {
  const symSel = Dom.opportunity.symbolSelect();
  const shortSel = Dom.opportunity.shortSelect();
  const longSel = Dom.opportunity.longSelect();
  if (!symSel || !shortSel || !longSel) return;
  if (force || document.activeElement !== symSel) {
    symSel.value = payload.symbol;
  }
  if (force || document.activeElement !== shortSel) {
    shortSel.value = payload.short_exchange_id;
  }
  if (force || document.activeElement !== longSel) {
    longSel.value = payload.long_exchange_id;
  }
}

function populateFocusOptionLists() {
  const symSel = Dom.opportunity.symbolSelect();
  const shortSel = Dom.opportunity.shortSelect();
  const longSel = Dom.opportunity.longSelect();
  if (!symSel || !shortSel || !longSel) return;
  const screener = AppState.screenerSnapshot;
  const exchanges = screener?.exchanges?.length
    ? screener.exchanges
    : ["mexc", "bitget", "gate", "bingx"];
  const symbols = screener?.rows?.map((row) => row.asset) || [];
  const focus = resolveOpportunityFocus();
  const snapshotSymbol = AppState.opportunitySnapshot?.symbol;
  for (const sym of [focus?.symbol, snapshotSymbol]) {
    if (sym && !symbols.includes(sym)) {
      symbols.unshift(sym);
    }
  }
  const prevSym = symSel.value;
  symSel.innerHTML = symbols.map((s) => `<option value="${s}">${s}</option>`).join("");
  if (prevSym && symbols.includes(prevSym)) symSel.value = prevSym;
  else if (focus?.symbol) symSel.value = focus.symbol;

  const fillEx = (sel, selected) => {
    const prev = sel.value;
    sel.innerHTML = exchanges.map((ex) => `<option value="${ex}">${ex.toUpperCase()}</option>`).join("");
    if (prev && exchanges.includes(prev)) sel.value = prev;
    else if (selected) sel.value = selected;
  };
  fillEx(shortSel, focus?.short_exchange_id);
  fillEx(longSel, focus?.long_exchange_id);
}

function launchOpportunityFromSelectors() {
  populateFocusOptionLists();
  const status = Dom.opportunity.status();
  let symbol = Dom.opportunity.symbolSelect()?.value || "";
  let short_exchange_id = Dom.opportunity.shortSelect()?.value || "";
  let long_exchange_id = Dom.opportunity.longSelect()?.value || "";
  const snap = AppState.opportunitySnapshot;
  if (!symbol && snap?.symbol) symbol = snap.symbol;
  if (!short_exchange_id && snap?.short_exchange_id) short_exchange_id = snap.short_exchange_id;
  if (!long_exchange_id && snap?.long_exchange_id) long_exchange_id = snap.long_exchange_id;
  if (!symbol || !short_exchange_id || !long_exchange_id) {
    if (status) {
      status.textContent = "Оберіть символ, Short і Long біржі (або дочекайтесь Screener)";
    }
    return;
  }
  if (short_exchange_id === long_exchange_id) {
    if (status) status.textContent = "Short і Long біржі мають бути різними";
    return;
  }
  if (status) status.textContent = "";
  navigateToOpportunity({ symbol, short_exchange_id, long_exchange_id });
  ensureOpportunityWs(true);
}

function bindExCardLeverage(root) {
  root.querySelectorAll(".lev-select").forEach((sel) => {
    sel.addEventListener("change", () => {
      _opportunityClient?.send("opportunity.set_leverage", {
        exchange_id: sel.getAttribute("data-exchange-id"),
        leverage: parseInt(sel.value, 10),
      });
    });
  });
}

/** @param {HTMLElement} container @param {number[]} presets @param {(pct: number) => void} onPick */
function renderPctChips(container, presets, onPick) {
  if (!container) return;
  container.replaceChildren();
  for (const pct of presets || []) {
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.type = "button";
    btn.textContent = `${pct}%`;
    btn.addEventListener("click", () => onPick(pct));
    container.appendChild(btn);
  }
}

/** @param {number | null | undefined} value */
function updateAccumulatedVolume(value) {
  const accumulated = Dom.opportunity.paramAccumulated();
  if (accumulated) {
    accumulated.value = Number(value || 0).toFixed(2);
  }
}

/**
 * @param {object} params
 * @param {object[]} strategyRows
 */
function renderParamsInitial(params, strategyRows) {
  if (!params) return;
  const stratSelect = Dom.opportunity.paramStrategy();
  if (stratSelect && strategyRows.length) {
    stratSelect.innerHTML = strategyRows
      .map(
        (row) =>
          `<option value="${row.strategy_id}"${row.strategy_id === params.active_strategy_id ? " selected" : ""}>${row.strategy_label}</option>`
      )
      .join("");
  }
  updateAccumulatedVolume(params.accumulated_volume_usdt);
  const setVal = (el, val) => {
    if (el) el.value = val;
  };
  setVal(Dom.opportunity.paramTarget(), Number(params.target_volume_usdt || 0).toFixed(2));
  setVal(Dom.opportunity.paramOpenSpread(), Number(params.open_spread_threshold_pct || 0).toFixed(2));
  setVal(Dom.opportunity.paramCloseSpread(), Number(params.close_spread_threshold_pct || 0).toFixed(2));
  setVal(Dom.opportunity.accumulateUsdt(), Number(params.accumulate_volume_usdt || 0).toFixed(2));
  setVal(Dom.opportunity.accumulatePct(), Number(params.accumulate_volume_pct || 0).toFixed(2));
  setVal(Dom.opportunity.closeUsdt(), Number(params.close_volume_usdt || 0).toFixed(2));
  setVal(Dom.opportunity.closePct(), Number(params.close_volume_pct || 0).toFixed(2));
  const autoAcc = Dom.opportunity.autoAccumulate();
  const autoClose = Dom.opportunity.autoClose();
  if (autoAcc) autoAcc.checked = !!params.auto_accumulate_enabled;
  if (autoClose) autoClose.checked = !!params.auto_close_enabled;
  const presets = params.volume_pct_presets || [];
  renderPctChips(Dom.opportunity.accumulatePctChips(), presets, (pct) => {
    const el = Dom.opportunity.accumulatePct();
    if (el) el.value = String(pct);
  });
  renderPctChips(Dom.opportunity.closePctChips(), presets, (pct) => {
    const el = Dom.opportunity.closePct();
    if (el) el.value = String(pct);
  });
}

/** @param {object} card @param {HTMLElement} el */
function patchExCardElement(el, card) {
  const fund = card.funding_rate_pct;
  const fundCls = fund !== null && fund < 0 ? "fund-red" : "fund-green";
  const fundStr = fund !== null ? `${fund >= 0 ? "+" : ""}${Number(fund).toFixed(3)}%` : "—";
  const setLine = (label, html) => {
    for (const line of el.querySelectorAll(".ex-info-line")) {
      const lineLabel = line.querySelector("span:first-child")?.textContent;
      if (lineLabel !== label) continue;
      const valueSpan = line.querySelector("span:last-child");
      if (valueSpan) valueSpan.innerHTML = html;
    }
  };
  const symEl = el.querySelector(".ex-symbol");
  if (symEl) symEl.textContent = card.market_symbol || "—";
  const nativeEl = el.querySelector(".ex-native-id");
  if (nativeEl) nativeEl.textContent = card.native_market_id || "—";
  setLine(
    "Баланс",
    card.balance_usdt != null ? `${Number(card.balance_usdt).toFixed(2)} USDT` : "—"
  );
  setLine(
    "Фандінг",
    `<span class="${fundCls}">${fundStr}</span> · ${card.funding_countdown_sec != null ? fmtCountdown(card.funding_countdown_sec) : "—"}`
  );
  const futFee = el.querySelector(".ex-futures-fee");
  if (futFee) futFee.textContent = card.futures_fee;
  const spotFee = el.querySelector(".ex-spot-fee");
  if (spotFee) spotFee.textContent = card.spot_fee;
  const volEl = el.querySelector(".ex-volume-limits");
  if (volEl) volEl.textContent = fmtVolumeLimitsLine(card);
  setLine("Ордери", `${card.open_orders_count} відкр. / ${card.closed_orders_count} закр.`);
}

/** @param {object[]} cards */
function patchExchangeCards(cards) {
  const exRow = Dom.opportunity.exInfoRow();
  if (!exRow) return;
  for (const card of cards || []) {
    const el = exRow.querySelector(`.ex-info-card[data-exchange-id="${card.exchange_id}"]`);
    if (!el) continue;
    patchExCardElement(el, card);
  }
}

/** @param {object[]} groups */
function renderOppOrders(groups) {
  const list = Dom.opportunity.ordersList();
  if (!list) return;
  list.replaceChildren();
  const filtered = groups.filter((g) => g.status === _oppOrdersFilter);
  if (!filtered.length) {
    list.innerHTML = '<p class="muted" style="padding:8px;">Немає ордерів</p>';
    return;
  }
  for (const group of filtered) {
    list.appendChild(renderOrderGroup(group, { showOpportunityBtn: false }));
  }
}

/** @param {object} payload */
function renderOpportunitySnapshot(payload) {
  if (!payload || !snapshotMatchesFocus(payload)) return;
  AppState.opportunitySnapshot = payload;
  AppState.focusOpportunity = {
    symbol: payload.symbol,
    short_exchange_id: payload.short_exchange_id,
    long_exchange_id: payload.long_exchange_id,
  };

  populateFocusOptionLists();
  syncFocusSelectorsFromPayload(payload);
  const badgeShort = Dom.opportunity.badgeShort();
  const badgeLong = Dom.opportunity.badgeLong();
  if (badgeShort) badgeShort.textContent = `S · ${payload.short_exchange_id.toUpperCase()}`;
  if (badgeLong) badgeLong.textContent = `L · ${payload.long_exchange_id.toUpperCase()}`;
  const status = Dom.opportunity.status();
  if (status) status.textContent = payload.status || "";

  const focusKey = opportunityFocusKey({
    symbol: payload.symbol,
    short_exchange_id: payload.short_exchange_id,
    long_exchange_id: payload.long_exchange_id,
  });
  const initParams = _paramsInitializedForFocusKey !== focusKey;
  const exRow = Dom.opportunity.exInfoRow();
  if (initParams) {
    if (exRow) {
      exRow.innerHTML = (payload.exchange_cards || []).map(renderExCard).join("");
      bindExCardLeverage(exRow);
    }
    renderParamsInitial(payload.params, payload.strategy_rows || []);
    _paramsInitializedForFocusKey = focusKey;
  } else {
    patchExchangeCards(payload.exchange_cards || []);
    updateAccumulatedVolume(payload.params?.accumulated_volume_usdt);
  }

  const stratBody = Dom.opportunity.strategyTbody();
  if (stratBody) {
    const sorted = sortStrategyRowsByPercent(payload.strategy_rows || []);
    stratBody.innerHTML = sorted.map(renderStrategyRow).join("");
  }
  const title = Dom.opportunity.ordersTitle();
  if (title) title.textContent = payload.symbol;
  renderOppOrders(payload.orders || []);

  if (payload.chart && window.OpportunityChart && initParams) {
    OpportunityChart.updateFromSnapshot(payload.chart);
  }

  const booksRoot = Dom.opportunity.booksRoot();
  const books = payload.books || [];
  if (booksRoot && books.length) {
    if (initParams || !booksRoot.querySelector("[data-book]")) {
      renderOrderBooks(booksRoot, books);
    } else {
      for (const book of books) {
        patchOrderBook(booksRoot, book);
      }
    }
  }
  updateOpportunityLoading();
}

function bindOppOrdersFilter() {
  Dom.opportunity.ordersFilters()?.querySelectorAll("[data-opp-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      Dom.opportunity.ordersFilters()?.querySelectorAll("[data-opp-filter]").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      _oppOrdersFilter = chip.getAttribute("data-opp-filter") || "open";
      if (AppState.opportunitySnapshot) {
        renderOppOrders(AppState.opportunitySnapshot.orders || []);
      }
    });
  });
}

function bindOppActions() {
  const sendParams = () => {
    _opportunityClient?.send("opportunity.set_params", {
      active_strategy_id: Dom.opportunity.paramStrategy()?.value || "",
      target_volume_usdt: parseFloat(Dom.opportunity.paramTarget()?.value || "0") || 0,
      open_spread_threshold_pct: parseFloat(Dom.opportunity.paramOpenSpread()?.value || "0") || 0,
      close_spread_threshold_pct: parseFloat(Dom.opportunity.paramCloseSpread()?.value || "0") || 0,
      accumulate_volume_usdt: parseFloat(Dom.opportunity.accumulateUsdt()?.value || "0") || 0,
      accumulate_volume_pct: parseFloat(Dom.opportunity.accumulatePct()?.value || "0") || 0,
      close_volume_usdt: parseFloat(Dom.opportunity.closeUsdt()?.value || "0") || 0,
      close_volume_pct: parseFloat(Dom.opportunity.closePct()?.value || "0") || 0,
      auto_accumulate_enabled: !!Dom.opportunity.autoAccumulate()?.checked,
      auto_close_enabled: !!Dom.opportunity.autoClose()?.checked,
    });
  };

  [
    Dom.opportunity.paramStrategy(),
    Dom.opportunity.paramTarget(),
    Dom.opportunity.paramOpenSpread(),
    Dom.opportunity.paramCloseSpread(),
    Dom.opportunity.accumulateUsdt(),
    Dom.opportunity.accumulatePct(),
    Dom.opportunity.closeUsdt(),
    Dom.opportunity.closePct(),
    Dom.opportunity.autoAccumulate(),
    Dom.opportunity.autoClose(),
  ].forEach((el) => {
    if (!el) return;
    const eventName = el.tagName === "SELECT" || el.type === "checkbox" ? "change" : "blur";
    el.addEventListener(eventName, sendParams);
  });

  Dom.opportunity.btnAccumulate()?.addEventListener("click", () => {
    _opportunityClient?.send("opportunity.accumulate", {
      volume_usdt: parseFloat(Dom.opportunity.accumulateUsdt()?.value || "0") || 0,
      volume_pct: parseFloat(Dom.opportunity.accumulatePct()?.value || "0") || 0,
    });
  });
  Dom.opportunity.btnClosePartial()?.addEventListener("click", () => {
    _opportunityClient?.send("opportunity.close_partial", {
      volume_usdt: parseFloat(Dom.opportunity.closeUsdt()?.value || "0") || 0,
      volume_pct: parseFloat(Dom.opportunity.closePct()?.value || "0") || 0,
    });
  });
  Dom.opportunity.btnCloseAll()?.addEventListener("click", () => {
    _opportunityClient?.send("opportunity.close_all", {});
  });
}

function updateOpportunityLoading() {
  const focus = resolveOpportunityFocus();
  const hasFocus = !!(focus?.symbol && focus.short_exchange_id && focus.long_exchange_id);
  const onPage = AppState.activePage === "opportunity";
  const loading = onPage && hasFocus && !AppState.opportunitySnapshot;
  let message = "Завантаження даних…";
  if (!AppState.opportunityWsConnected) {
    message = "Підключення…";
  }
  setLoadingOverlay("opportunity-loading", loading, message);
}

function stopOpportunityWs() {
  if (_opportunityClient) {
    _opportunityClient.close();
  }
  _opportunityClient = null;
  _opportunityWsUrl = null;
  _connectedFocusKey = null;
  _paramsInitializedForFocusKey = null;
  AppState.opportunityWsConnected = false;
  updateOpportunityLoading();
}

function ensureOpportunityWs(force = false) {
  const focus = resolveOpportunityFocus();
  if (!focus?.symbol || !focus.short_exchange_id || !focus.long_exchange_id) return;
  AppState.focusOpportunity = focus;
  const path = opportunityWsPathFor(focus);
  const focusKey = opportunityFocusKey(focus);
  if (
    !force &&
    _opportunityClient &&
    _opportunityWsUrl === path &&
    _connectedFocusKey === focusKey
  ) {
    return;
  }
  stopOpportunityWs();
  AppState.opportunitySnapshot = null;
  _opportunityWsUrl = path;
  _connectedFocusKey = focusKey;
  updateOpportunityLoading();
  _opportunityClient = new WsClient(path, {
    onOpen: () => {
      AppState.opportunityWsConnected = true;
      updateOpportunityLoading();
    },
    onClose: () => {
      AppState.opportunityWsConnected = false;
      updateOpportunityLoading();
    },
  });
}

/** @param {{ symbol: string, short_exchange_id: string, long_exchange_id: string }} focus */
function navigateToOpportunity(focus) {
  if (!focus?.symbol || !focus.short_exchange_id || !focus.long_exchange_id) return;
  AppState.focusOpportunity = focus;
  AppState.opportunitySnapshot = null;
  populateFocusOptionLists();
  syncFocusSelectorsFromPayload(focus, true);
  showPage("opportunity");
  updateOpportunityLoading();
}

function refreshOpportunityView() {
  if (AppState.opportunitySnapshot && snapshotMatchesFocus(AppState.opportunitySnapshot)) {
    renderOpportunitySnapshot(AppState.opportunitySnapshot);
  }
  if (window.OpportunityChart) {
    requestAnimationFrame(() => {
      OpportunityChart.chartResize();
      OpportunityChart.chartDraw();
    });
  }
}

function startOpportunityWs() {
  populateFocusOptionLists();
  ensureOpportunityWs(false);
  refreshOpportunityView();
  updateOpportunityLoading();
}

/** @param {object} payload */
function handleOpportunityError(payload) {
  const status = Dom.opportunity.status();
  if (status) {
    status.textContent = payload?.message ? String(payload.message) : "Opportunity error";
  }
  setLoadingOverlay("opportunity-loading", false);
}

function initOpportunity() {
  registerDeltaHandler("opportunity.snapshot", renderOpportunitySnapshot);
  registerDeltaHandler("opportunity.error", handleOpportunityError);
  registerDeltaHandler("opportunity.delta", (payload) => {
    if (!payload) return;
    if (payload.chart_series?.length && window.OpportunityChart) {
      OpportunityChart.applyDelta(payload.chart_series);
    }
    const booksRoot = Dom.opportunity.booksRoot();
    if (payload.books?.length && booksRoot) {
      if (!booksRoot.querySelector("[data-book]")) {
        renderOrderBooks(booksRoot, payload.books);
      } else {
        for (const book of payload.books) {
          patchOrderBook(booksRoot, book);
        }
      }
    }
  });
  bindOppOrdersFilter();
  bindOppActions();
  populateFocusOptionLists();
  Dom.opportunity.launchBtn()?.addEventListener("click", launchOpportunityFromSelectors);
}

window.populateFocusOptionLists = populateFocusOptionLists;
window.navigateToOpportunity = navigateToOpportunity;
window.ensureOpportunityWs = ensureOpportunityWs;
window.startOpportunityWs = startOpportunityWs;
window.stopOpportunityWs = stopOpportunityWs;
window.initOpportunity = initOpportunity;
window.refreshOpportunityView = refreshOpportunityView;
