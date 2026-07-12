import re

with open("src/arbitrator/presentation/static/js/render/monitors.js", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add activeCardWs tracking
if "let activeCardWs = {};" not in content:
    content = content.replace("let activeMonitors = {};", "let activeMonitors = {};\nlet activeCardWs = {}; // Track ws clients per card")

# 2. Add startCardWs, stopCardWs, handleCardSnapshot
ws_functions = """
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

    // For now, let's just populate the short side PnL / execution price with mock or real if available
    const execPrice1 = cardEl.querySelector(".lc-ex1-exec-price");
    if (execPrice1) execPrice1.textContent = stratRow.prices_label.split(" / ")[0] || "—";
    const execPrice2 = cardEl.querySelector(".lc-ex2-exec-price");
    if (execPrice2) execPrice2.textContent = stratRow.prices_label.split(" / ")[1] || "—";

    const pnl1 = cardEl.querySelector(".lc-ex1-pnl");
    if (pnl1) pnl1.textContent = stratRow.net_profit_usdt != null ? stratRow.net_profit_usdt.toFixed(2) : "—";
  }
}
"""

if "function startCardWs" not in content:
    content += "\n" + ws_functions

# 3. Hook it into syncMonitorsFromServer
sync_find = "activeMonitors[config.symbol] = true;"
if "startCardWs(cardEl, config);" not in content:
    content = content.replace(sync_find, sync_find + "\n      startCardWs(cardEl, config);")

remove_find = "delete activeMonitors[symbol];"
if "stopCardWs(symbol);" not in content:
    content = content.replace(remove_find, remove_find + "\n      stopCardWs(symbol);")


with open("src/arbitrator/presentation/static/js/render/monitors.js", "w", encoding="utf-8") as f:
    f.write(content)
