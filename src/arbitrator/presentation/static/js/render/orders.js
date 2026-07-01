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

  list.replaceChildren();
  const groups = payload.groups || [];
  if (!groups.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.style.padding = "12px";
    empty.textContent = "Немає ордерів для фільтра";
    list.appendChild(empty);
    return;
  }
  for (const group of groups) {
    list.appendChild(renderOrderGroup(group));
  }

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
