/** @type {WsClient | null} */
let _ordersClient = null;

/** @param {object} payload */
function renderOrdersSnapshot(payload) {
  AppState.ordersSnapshot = payload;
  const list = Dom.orders.list();
  const summaryEl = Dom.orders.summary();
  const openLabel = Dom.orders.openLabel();
  if (!list) return;

  const summary = payload.summary || {};
  const summaryText = `${summary.open_count || 0} open · ${summary.closed_count || 0} closed`;
  if (summaryEl) {
    summaryEl.innerHTML = `<span class="dot"></span>${summaryText}`;
  }
  if (openLabel) openLabel.textContent = String(summary.open_count ?? "—");
  updateOrdersNavBadge(summary.open_count);

  const groups = payload.groups || [];
  if (!groups.length) {
    list.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.style.padding = "12px";
    empty.textContent = "Немає ордерів для фільтра";
    list.appendChild(empty);
    return;
  }

  const isFirstRender = list.children.length === 0;

  // Build a map of existing DOM elements by groupKey
  /** @type {Map<string, HTMLElement>} */
  const existing = new Map();
  list.querySelectorAll(".ord-group[data-group-key]").forEach((el) => {
    existing.set(el.dataset.groupKey, /** @type {HTMLElement} */ (el));
  });

  /** @param {HTMLElement} el @param {object} group */
  function patchGroupElement(el, group) {
    const pnlCls = pnlClass(group.pnl_usdt);
    const parent = el.querySelector(".ord-parent");
    if (!parent) return;
    const cells = parent.querySelectorAll(":scope > div");
    // cells indices: 0=caret, 1=asset, 2=strategy_code, 3=exchanges,
    //   4=opened_at, 5=closed_at, 6=leverage, 7=volume, 8=entry(—), 9=exit(—),
    //   10=fees, 11=funding, 12=pnl, 13=status, 14=opp-btn (optional)
    if (cells[4]) cells[4].textContent = group.opened_at || "—";
    if (cells[5]) cells[5].textContent = group.closed_at || "—";
    if (cells[9]) {
      const spreadNow = group.status === "open" && group.current_spread_pct != null
        ? `<span class="${group.current_spread_pct >= 0 ? "pos" : "neg"}">${group.current_spread_pct >= 0 ? "+" : ""}${Number(group.current_spread_pct).toFixed(2)}%</span>`
        : group.exit_spread_pct != null
          ? `<span class="${group.exit_spread_pct >= 0 ? "pos" : "neg"}">${group.exit_spread_pct >= 0 ? "+" : ""}${Number(group.exit_spread_pct).toFixed(2)}%</span>`
          : "—";
      cells[9].innerHTML = spreadNow;
    }
    if (cells[10]) cells[10].textContent = fmtNum(group.fees_usdt, 2);
    if (cells[11]) {
      const fundingCountdown = group.status === "open" && group.funding_countdown_sec != null
        ? `<br><span class="muted" style="font-size:0.8em;">⏱${fmtCountdownSec(group.funding_countdown_sec)}</span>`
        : "";
      cells[11].innerHTML = fmtPnl(group.funding_usdt) + fundingCountdown;
    }
    if (cells[12]) {
      cells[12].textContent = fmtPnl(group.pnl_usdt);
      cells[12].className = `num ${pnlCls}`;
    }
    // Update legs (children)
    const childrenEl = el.querySelector(".ord-children");
    if (childrenEl) {
      const legEls = childrenEl.querySelectorAll(".ord-child");
      const legs = group.legs || [];
      legs.forEach((leg, i) => {
        const row = legEls[i];
        if (!row) return;
        const legCells = row.querySelectorAll(":scope > div");
        // leg cells: 0-2 empty, 3=exchange+side, 4 empty, 5 empty,
        //   6=leverage, 7=volume, 8=entry, 9=exit, 10=fees, 11=funding, 12=pnl, 13 empty
        if (legCells[8]) legCells[8].textContent = fmtNum(leg.entry_price, 5);
        if (legCells[9]) legCells[9].textContent = leg.exit_price != null ? fmtNum(leg.exit_price, 5) : "—";
        if (legCells[10]) legCells[10].textContent = fmtNum(leg.fees_usdt, 2);
        if (legCells[11]) legCells[11].textContent = fmtPnl(leg.funding_usdt);
        if (legCells[12]) {
          const lPnlCls = pnlClass(leg.pnl_usdt);
          legCells[12].textContent = fmtPnl(leg.pnl_usdt);
          legCells[12].className = `num ${lPnlCls}`;
        }
      });
    }
  }

  // Determine the ordered list of keys from incoming groups
  const incomingKeys = groups.map((g) => `${g.symbol || g.asset}:${g.short_exchange_id}:${g.long_exchange_id}`);
  const incomingSet = new Set(incomingKeys);

  // Remove stale groups
  existing.forEach((el, key) => {
    if (!incomingSet.has(key)) el.remove();
  });

  // Insert or patch groups in order
  groups.forEach((group, index) => {
    const key = incomingKeys[index];
    const existingEl = existing.get(key);

    if (existingEl) {
      // Patch numbers only — do not touch expanded state
      patchGroupElement(existingEl, group);
      // Ensure correct DOM order
      const currentAtIndex = list.children[index];
      if (currentAtIndex !== existingEl) {
        list.insertBefore(existingEl, currentAtIndex || null);
      }
    } else {
      // New group — create and insert
      const el = renderOrderGroup(group);
      el.dataset.groupKey = key;
      if (isFirstRender && group.status === "open") {
        el.classList.add("expanded");
      }
      const refNode = list.children[index] || null;
      list.insertBefore(el, refNode);
    }
  });

  Dom.orders.filters()?.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
  const active = Dom.orders.filters()?.querySelector(`.chip[data-filter="${payload.filter || "all"}"]`);
  active?.classList.add("active");
}

function bindOrdersFilters() {
  Dom.orders.filters()?.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const filter = chip.getAttribute("data-filter");
      if (_ordersClient && filter) {
        _ordersClient.send("orders.set_filter", { filter });
      }
    });
  });
}

function initOrders() {
  registerDeltaHandler("orders.snapshot", renderOrdersSnapshot);
  bindOrdersFilters();
  _ordersClient = new WsClient("/ws/orders", {
    onMessage(data) {
      if (data.type === "orders.summary" && data.payload) {
        updateOrdersNavBadge(data.payload.open_count);
      }
    },
  });
}

window.initOrders = initOrders;
