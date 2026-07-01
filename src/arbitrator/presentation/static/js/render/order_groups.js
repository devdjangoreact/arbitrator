/** @param {HTMLElement} group */
function toggleGroup(group) {
  group.classList.toggle("expanded");
}

/** @param {object} leg @param {boolean} [withActionCol] */
function renderOrderLeg(leg, withActionCol = true) {
  const sideCls = leg.side === "short" ? "short" : "long";
  const pnlCls = pnlClass(leg.pnl_usdt);
  const actionCol = withActionCol ? "<div></div>" : "";
  return `
    <div class="ord-grid ord-child">
      <div></div><div></div><div></div>
      <div><span class="badge ${sideCls}">${leg.exchange_id} ${leg.side}</span></div>
      <div></div><div></div>
      <div class="num">${leg.leverage}x</div>
      <div class="num">${fmtNum(leg.volume_usdt, 2)}</div>
      <div class="num">${fmtNum(leg.entry_price, 5)}</div>
      <div class="num">${leg.exit_price != null ? fmtNum(leg.exit_price, 5) : "—"}</div>
      <div class="num">${fmtNum(leg.fees_usdt, 2)}</div>
      <div class="num">${fmtPnl(leg.funding_usdt)}</div>
      <div class="num ${pnlCls}">${fmtPnl(leg.pnl_usdt)}</div>
      <div></div>${actionCol}
    </div>`;
}

/**
 * @param {object} group
 * @param {{ showOpportunityBtn?: boolean }} [opts]
 */
function renderOrderGroup(group, opts = {}) {
  const showBtn = opts.showOpportunityBtn !== false;
  const pnlCls = pnlClass(group.pnl_usdt);
  const statusBadge = group.status === "open" ? "open" : "closed";
  const statusLabel = group.status === "open" ? "Open" : "Closed";
  const legsHtml = (group.legs || []).map((leg) => renderOrderLeg(leg, showBtn)).join("");
  const oppBtn = showBtn
    ? `<div><button class="btn btn-primary btn-opp" type="button">Opportunity</button></div>`
    : "";

  const div = document.createElement("div");
  div.className = `ord-group${group.status === "open" ? " expanded" : ""}`;
  div.dataset.status = group.status;
  div.innerHTML = `
    <div class="ord-grid ord-parent">
      <div class="caret">▸</div>
      <div>${group.asset}</div>
      <div>${group.strategy_code}</div>
      <div><span class="badge short">S·${group.short_exchange_id.toUpperCase()}</span> <span class="badge long">L·${group.long_exchange_id.toUpperCase()}</span></div>
      <div>${group.opened_at}</div>
      <div>${group.closed_at || "—"}</div>
      <div class="num">${group.leverage}x</div>
      <div class="num">${fmtNum(group.volume_usdt, 2)}</div>
      <div class="num">—</div>
      <div class="num">—</div>
      <div class="num">${fmtNum(group.fees_usdt, 2)}</div>
      <div class="num">${fmtPnl(group.funding_usdt)}</div>
      <div class="num ${pnlCls}">${fmtPnl(group.pnl_usdt)}</div>
      <div><span class="status-badge ${statusBadge}">${statusLabel}</span></div>
      ${showBtn ? oppBtn : ""}
    </div>
    <div class="ord-children">${legsHtml}</div>`;
  div.querySelector(".ord-parent")?.addEventListener("click", () => toggleGroup(div));
  const btn = div.querySelector(".btn-opp");
  if (btn) {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof navigateToOpportunity === "function") {
        navigateToOpportunity({
          symbol: group.asset,
          short_exchange_id: group.short_exchange_id,
          long_exchange_id: group.long_exchange_id,
        });
      }
    });
  }
  return div;
}

window.toggleGroup = toggleGroup;
window.renderOrderGroup = renderOrderGroup;
