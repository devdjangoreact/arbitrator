/** @type {WsClient | null} */
let _ptClient = null;

/** @param {object} payload */
function renderPaperTradesSnapshot(payload) {
  AppState.paperTradesSnapshot = payload;

  const summary = payload.summary || {};
  const openPairs = summary.open_pairs ?? 0;
  const closedPairs = summary.closed_pairs ?? 0;
  const totalPnl = summary.total_pnl_usdt ?? 0;
  const totalNetPnl = summary.total_net_pnl_usdt ?? 0;
  const totalFees = summary.total_fees_usdt ?? 0;
  const totalFunding = summary.total_funding_usdt ?? 0;
  const totalOrders = summary.total_orders ?? 0;

  const elOpen = document.getElementById("pt-open-pairs");
  const elClosed = document.getElementById("pt-closed-pairs");
  const elPnl = document.getElementById("pt-total-pnl");
  const elNetPnl = document.getElementById("pt-total-net-pnl");
  const elFees = document.getElementById("pt-total-fees");
  const elFunding = document.getElementById("pt-total-funding");
  const elOrders = document.getElementById("pt-total-orders");
  const elStatus = document.getElementById("pt-status");

  if (elOpen) elOpen.textContent = String(openPairs);
  if (elClosed) elClosed.textContent = String(closedPairs);
  if (elPnl) {
    const sign = totalPnl > 0 ? "+" : totalPnl < 0 ? "−" : "";
    elPnl.textContent = `${sign}${Math.abs(totalPnl).toFixed(2)} USDT`;
    elPnl.className = "value " + (totalPnl > 0 ? "green" : totalPnl < 0 ? "red" : "");
  }
  if (elNetPnl) {
    const sign = totalNetPnl > 0 ? "+" : totalNetPnl < 0 ? "−" : "";
    elNetPnl.textContent = `${sign}${Math.abs(totalNetPnl).toFixed(2)} USDT`;
    elNetPnl.className = "value " + (totalNetPnl > 0 ? "green" : totalNetPnl < 0 ? "red" : "");
  }
  if (elFees) {
    elFees.textContent = `−${Math.abs(totalFees).toFixed(2)} USDT`;
    elFees.className = "value red";
  }
  if (elFunding) {
    const fSign = totalFunding > 0 ? "−" : totalFunding < 0 ? "+" : "";
    elFunding.textContent = `${fSign}${Math.abs(totalFunding).toFixed(2)} USDT`;
    elFunding.className = "value " + (totalFunding > 0 ? "red" : totalFunding < 0 ? "green" : "");
  }
  if (elOrders) elOrders.textContent = String(totalOrders);
  if (elStatus) {
    elStatus.innerHTML = `<span class="dot" style="background:var(--green)"></span>${openPairs} open · ${closedPairs} closed`;
  }

  // update sidebar badge
  const navEl = Dom.nav.ptOpen ? Dom.nav.ptOpen() : document.getElementById("nav-pt-open");
  if (navEl) navEl.textContent = openPairs > 0 ? String(openPairs) : "—";

  const list = document.getElementById("pt-list");
  if (!list) return;

  const groups = payload.groups || [];
  if (!groups.length) {
    list.replaceChildren();
    const p = document.createElement("p");
    p.className = "muted";
    p.style.padding = "20px 12px";
    p.textContent = "Немає ордерів";
    list.appendChild(p);
    return;
  }

  const isFirstRender = list.children.length === 0;

  // Build map of existing DOM elements by pair_id
  /** @type {Map<string, HTMLElement>} */
  const existing = new Map();
  list.querySelectorAll(".pt-group[data-pair-id]").forEach((el) => {
    existing.set(el.dataset.pairId, /** @type {HTMLElement} */ (el));
  });

  const incomingIds = groups.map((g) => g.pair_id);
  const incomingSet = new Set(incomingIds);

  // Remove stale
  existing.forEach((el, id) => {
    if (!incomingSet.has(id)) el.remove();
  });

  groups.forEach((group, index) => {
    const id = group.pair_id;
    const existingEl = existing.get(id);

    if (existingEl) {
      patchPaperTradeGroup(existingEl, group);
      const currentAtIndex = list.children[index];
      if (currentAtIndex !== existingEl) {
        list.insertBefore(existingEl, currentAtIndex || null);
      }
    } else {
      const el = renderPaperTradeGroup(group);
      if (isFirstRender && group.status === "open") {
        el.classList.add("expanded");
        const caret = el.querySelector(".caret");
        if (caret) caret.style.transform = "rotate(90deg)";
      }
      list.insertBefore(el, list.children[index] || null);
    }
  });

  // sync filter chips
  document.querySelectorAll("#pt-filters .chip").forEach((c) => c.classList.remove("active"));
  const active = document.querySelector(`#pt-filters .chip[data-filter="${payload.filter || "all"}"]`);
  if (active) active.classList.add("active");
}

/** Build per-leg funding HTML: accrued USDT + countdown + rate */
function _legFundingHtml(leg) {
  const legFunding = leg.accrued_funding_usdt || 0;
  let html = legFunding !== 0
    ? `${legFunding > 0 ? "−" : "+"}${Math.abs(legFunding).toFixed(2)}`
    : "0.00";
  if (leg.status === "filled") {
    if (leg.next_funding_ms) {
      const diff = leg.next_funding_ms - Date.now();
      if (diff > 0) {
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        const s = Math.floor((diff % 60000) / 1000);
        const countdown = h > 0
          ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
          : `${m}:${String(s).padStart(2, "0")}`;
        const charge = leg.next_funding_charge_usdt;
        const chargeStr = charge != null
          ? ` (${charge > 0 ? "−" : "+"}${Math.abs(charge).toFixed(2)})`
          : "";
        html += `<br><span class="muted" style="font-size:0.8em;">⏱${countdown}${chargeStr}</span>`;
      }
    }
    if (leg.funding_rate_pct != null) {
      const rateCls = leg.funding_rate_pct > 0 ? "neg" : leg.funding_rate_pct < 0 ? "pos" : "";
      html += `<br><span class="${rateCls}" style="font-size:0.8em;">${leg.funding_rate_pct >= 0 ? "+" : ""}${Number(leg.funding_rate_pct).toFixed(4)}%</span>`;
    }
  }
  return html;
}

/** Build group-level funding summary HTML */
function _ptFundingHtml(group) {
  const fundingVal = group.funding_usdt ?? 0;
  return fundingVal !== 0
    ? `${fundingVal > 0 ? "−" : "+"}${Math.abs(fundingVal).toFixed(2)}`
    : "0.00";
}

/** Compute live exit spread % from group-level current prices */
function _liveExitSpread(group) {
  const sp = group.current_short_price;
  const lp = group.current_long_price;
  if (sp != null && lp != null && lp > 0) {
    return (sp - lp) / lp * 100;
  }
  return null;
}

/** Patch only the changing numeric fields of an existing group element */
function patchPaperTradeGroup(el, group) {
  const isOpen = group.status === "open";
  const netPnl = group.net_pnl_usdt;

  const parent = el.querySelector(".pt-parent");
  if (!parent) return;
  const cells = parent.querySelectorAll(":scope > div");
  // pt-grid cells: 0=caret, 1=symbol, 2=short-badge, 3=long-badge,
  //   4=opened_at, 5=closed_at, 6=entry%, 7=exit%, 8=notional,
  //   9=fees, 10=funding, 11=pnl, 12=net_pnl, 13=status

  // closed_at — update when pair just closed
  if (cells[5]) {
    const _dtFmt = { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" };
    const closedStr = group.closed_at ? new Date(group.closed_at).toLocaleString("uk-UA", _dtFmt) : "—";
    cells[5].textContent = closedStr;
  }

  // exit spread: live spread for open pairs, recorded spread for closed
  if (cells[7]) {
    let exitHtml;
    if (isOpen) {
      const live = _liveExitSpread(group);
      exitHtml = live != null
        ? `<span class="muted">${Number(live).toFixed(2)}%</span>`
        : "<span class='muted'>—</span>";
    } else {
      exitHtml = group.exit_spread_pct != null
        ? `${Number(group.exit_spread_pct).toFixed(2)}%`
        : "—";
    }
    cells[7].innerHTML = exitHtml;
  }
  // fees
  if (cells[9]) cells[9].textContent = group.fees_usdt ? `−${Number(group.fees_usdt).toFixed(2)}` : "0.00";
  // funding + countdown
  if (cells[10]) cells[10].innerHTML = _ptFundingHtml(group);
  // pnl
  if (cells[11]) {
    const pnlVal = group.pnl_usdt;
    if (isOpen && (pnlVal === null || pnlVal === undefined)) {
      cells[11].innerHTML = "<span class='muted'>—</span>";
    } else {
      const v = Number(pnlVal ?? 0);
      const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
      cells[11].innerHTML = `<span class="${cls}">${v >= 0 ? "+" : ""}${v.toFixed(2)}</span>`;
    }
  }
  // net pnl
  if (cells[12]) {
    const netPnlCls = netPnl > 0 ? "pos" : netPnl < 0 ? "neg" : "";
    cells[12].innerHTML = netPnl != null
      ? `<span class="${netPnlCls}">${netPnl >= 0 ? "+" : ""}${Number(netPnl).toFixed(2)}</span>`
      : "<span class='muted'>0.00</span>";
  }
  // status badge — update when pair transitions open → closed
  if (cells[13]) {
    cells[13].innerHTML = isOpen
      ? "<span class='status-badge open'>Open</span>"
      : "<span class='status-badge closed'>Closed</span>";
  }

  // Patch leg rows
  const legRows = el.querySelectorAll(".pt-leg");
  (group.legs || []).forEach((leg, i) => {
    const row = legRows[i];
    if (!row) return;
    const legCells = row.querySelectorAll(":scope > div");
    // pt-leg cells: 0 empty, 1 empty, 2=exchange+side, 3 empty, 4 empty,
    //   5 empty, 6=entry_price, 7=exit/current_price, 8=notional,
    //   9=fees, 10=funding, 11=pnl, 12=net_pnl, 13=status

    // entry price column (static — only set on first render via renderPaperTradeLegs)
    if (legCells[6]) {
      legCells[6].innerHTML = _legEntryPriceHtml(leg);
    }
    // exit/current price column — updates dynamically on every push
    if (legCells[7]) {
      legCells[7].innerHTML = _legExitPriceHtml(leg);
    }
    // leg funding + countdown + rate per exchange
    if (legCells[10]) {
      legCells[10].innerHTML = _legFundingHtml(leg);
    }
    // leg pnl (live for open legs)
    if (legCells[11]) {
      const livePnl = _legLivePnl(leg);
      const legPnlCls = (livePnl ?? 0) > 0 ? "pos" : (livePnl ?? 0) < 0 ? "neg" : "";
      legCells[11].innerHTML = livePnl != null
        ? `<span class="${legPnlCls}">${livePnl >= 0 ? "+" : ""}${Number(livePnl).toFixed(2)}</span>`
        : "<span class='muted'>—</span>";
    }
    // leg net pnl
    if (legCells[12]) {
      legCells[12].innerHTML = leg.net_pnl_usdt != null
        ? `<span class="${leg.net_pnl_usdt >= 0 ? "pos" : "neg"}">${leg.net_pnl_usdt >= 0 ? "+" : ""}${Number(leg.net_pnl_usdt).toFixed(2)}</span>`
        : "<span class='muted'>—</span>";
    }
  });
}

/** @param {object} group */
function renderPaperTradeGroup(group) {
  const isOpen = group.status === "open";
  const pnlVal = group.pnl_usdt;
  const pnlCls = (pnlVal ?? 0) > 0 ? "pos" : (pnlVal ?? 0) < 0 ? "neg" : "";
  const pnlStr = (isOpen && (pnlVal === null || pnlVal === undefined))
    ? "<span class='muted'>—</span>"
    : `<span class="${pnlCls}">${Number(pnlVal ?? 0) >= 0 ? "+" : ""}${Number(pnlVal ?? 0).toFixed(2)}</span>`;

  const netPnl = group.net_pnl_usdt;
  const netPnlCls = netPnl > 0 ? "pos" : netPnl < 0 ? "neg" : "";
  const netPnlStr = netPnl != null ? `<span class="${netPnlCls}">${netPnl >= 0 ? "+" : ""}${Number(netPnl).toFixed(2)}</span>` : "<span class='muted'>0.00</span>";

  const feesStr = group.fees_usdt ? `−${Number(group.fees_usdt).toFixed(2)}` : "0.00";
  const fundingStr = _ptFundingHtml(group);

  const _dtFmt = { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" };
  const openedStr = group.opened_at ? new Date(group.opened_at).toLocaleString("uk-UA", _dtFmt) : "—";
  const closedStr = group.closed_at ? new Date(group.closed_at).toLocaleString("uk-UA", _dtFmt) : "—";

  const entrySpread = group.entry_spread_pct != null ? `${Number(group.entry_spread_pct).toFixed(2)}%` : "—";
  let exitSpread;
  if (!isOpen && group.exit_spread_pct != null) {
    exitSpread = `${Number(group.exit_spread_pct).toFixed(2)}%`;
  } else if (isOpen) {
    const live = _liveExitSpread(group);
    exitSpread = live != null ? `<span class="muted">${Number(live).toFixed(2)}%</span>` : "<span class='muted'>—</span>";
  } else {
    exitSpread = "—";
  }
  const notional = group.notional_usdt != null ? `$${Number(group.notional_usdt).toFixed(0)}` : "—";

  const statusBadge = isOpen
    ? `<span class="status-badge open">Open</span>`
    : `<span class="status-badge closed">Closed</span>`;

  const wrapper = document.createElement("div");
  wrapper.className = "pt-group";
  wrapper.dataset.status = group.status;
  wrapper.dataset.pairId = group.pair_id;

  wrapper.innerHTML = `
    <div class="pt-grid pt-parent">
      <div class="caret">▸</div>
      <div><strong>${group.symbol.replace("/USDT:USDT", "")}</strong><span class="muted" style="font-size:0.85em;">/USDT</span></div>
      <div><span class="badge short">S·${group.short_exchange_id.toUpperCase()}</span></div>
      <div><span class="badge long">L·${group.long_exchange_id.toUpperCase()}</span></div>
      <div class="muted" style="font-size:0.9em;">${openedStr}</div>
      <div class="muted" style="font-size:0.9em;">${closedStr}</div>
      <div class="num" style="color:var(--accent)">${entrySpread}</div>
      <div class="num">${exitSpread}</div>
      <div class="num muted">${notional}</div>
      <div class="num muted">${feesStr}</div>
      <div class="num muted">${fundingStr}</div>
      <div class="num">${pnlStr}</div>
      <div class="num">${netPnlStr}</div>
      <div>${statusBadge}</div>
    </div>
    <div class="pt-children">${renderPaperTradeLegs(group.legs || [], group)}</div>`;

  wrapper.querySelector(".pt-parent")?.addEventListener("click", () => {
    wrapper.classList.toggle("expanded");
    const caret = wrapper.querySelector(".caret");
    if (caret) caret.style.transform = wrapper.classList.contains("expanded") ? "rotate(90deg)" : "";
  });

  return wrapper;
}

/** Entry price column HTML for a leg: only the open price */
function _legEntryPriceHtml(leg) {
  return leg.entry_price != null ? String(Number(leg.entry_price).toPrecision(6)) : "—";
}

/** Exit/current price column HTML for a leg: live price (open) or close price (closed) */
function _legExitPriceHtml(leg) {
  if (leg.status === "filled" && leg.current_price != null) {
    return `<span class="muted">${Number(leg.current_price).toPrecision(6)}</span>`;
  }
  if (leg.status === "closed" && leg.close_price != null) {
    return String(Number(leg.close_price).toPrecision(6));
  }
  return "<span class='muted'>—</span>";
}

/** Compute live PnL for an open leg from current_price if available */
function _legLivePnl(leg) {
  if (leg.pnl_usdt != null) return leg.pnl_usdt;
  if (leg.status === "filled" && leg.current_price != null && leg.entry_price != null) {
    const qty = leg.notional_usdt / leg.entry_price;
    return leg.side === "sell"
      ? (leg.entry_price - leg.current_price) * qty
      : (leg.current_price - leg.entry_price) * qty;
  }
  return null;
}

/** @param {Array} legs @param {object} group */
function renderPaperTradeLegs(legs, group) {
  if (!legs.length) return "<p class='muted' style='padding:8px 12px'>Нема ніг</p>";
  return legs.map((leg) => {
    const isSell = leg.side === "sell";
    const sideCls = isSell ? "short" : "long";
    const sideLabel = isSell ? "Short (sell)" : "Long (buy)";
    const livePnl = _legLivePnl(leg);
    const pnlCls = (livePnl ?? 0) > 0 ? "pos" : (livePnl ?? 0) < 0 ? "neg" : "";
    const pnlStr = livePnl != null
      ? `<span class="${pnlCls}">${livePnl >= 0 ? "+" : ""}${Number(livePnl).toFixed(2)}</span>`
      : "<span class='muted'>—</span>";
    const legFee = (leg.open_fee_usdt || 0) + (leg.close_fee_usdt || 0);
    const legFeeStr = legFee > 0 ? `−${legFee.toFixed(2)}` : "0.00";
    const netPnl = leg.net_pnl_usdt;
    const netPnlStr = netPnl != null
      ? `<span class="${netPnl >= 0 ? "pos" : "neg"}">${netPnl >= 0 ? "+" : ""}${Number(netPnl).toFixed(2)}</span>`
      : "<span class='muted'>—</span>";

    const entryPriceHtml = _legEntryPriceHtml(leg);
    const exitPriceHtml = _legExitPriceHtml(leg);
    const legFundingHtml = _legFundingHtml(leg);
    const notional = leg.notional_usdt != null ? `$${Number(leg.notional_usdt).toFixed(2)}` : "—";
    const statusStr = leg.status === "filled" ? "<span class='status-badge open'>Live</span>" : "<span class='status-badge closed'>Closed</span>";
    return `
      <div class="pt-grid pt-leg">
        <div></div>
        <div></div>
        <div><span class="badge ${sideCls}">${leg.exchange_id} · ${sideLabel}</span></div>
        <div></div>
        <div></div>
        <div></div>
        <div class="num muted">${entryPriceHtml}</div>
        <div class="num muted">${exitPriceHtml}</div>
        <div class="num muted">${notional}</div>
        <div class="num muted">${legFeeStr}</div>
        <div class="num muted">${legFundingHtml}</div>
        <div class="num">${pnlStr}</div>
        <div class="num">${netPnlStr}</div>
        <div>${statusStr}</div>
      </div>`;
  }).join("");
}

function bindPtFilters() {
  document.querySelectorAll("#pt-filters .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const filter = chip.getAttribute("data-filter");
      if (_ptClient && filter) {
        _ptClient.send("paper_trades.set_filter", { filter });
      }
    });
  });
}

function initPaperTrades() {
  registerDeltaHandler("paper_trades.snapshot", renderPaperTradesSnapshot);
  bindPtFilters();
  _ptClient = new WsClient("/ws/paper_trades", {});
}

window.initPaperTrades = initPaperTrades;
