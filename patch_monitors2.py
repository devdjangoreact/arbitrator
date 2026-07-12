import re

with open("src/arbitrator/presentation/static/js/render/monitors.js", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Hook live_state into the ws message handler
ws_handler_target = """        if (msg.data.monitors) {
          syncMonitorsFromServer(msg.data.monitors);
        }"""
new_ws_handler = """        if (msg.data.monitors) {
          syncMonitorsFromServer(msg.data.monitors);
          if (msg.data.live_state) {
             applyLiveStateToMonitors(msg.data.live_state, msg.data.monitors);
          }
        }"""
if "applyLiveStateToMonitors" not in content:
    content = content.replace(ws_handler_target, new_ws_handler)

# 2. Add applyLiveStateToMonitors function
apply_fn = """
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
"""

if "function applyLiveStateToMonitors" not in content:
    content += "\n" + apply_fn

# 3. Clean up the old startCardWs stuff since we don't use it anymore
# Remove startCardWs call from syncMonitorsFromServer
content = re.sub(r'\s*startCardWs\(cardEl, config\);', '', content)
content = re.sub(r'\s*stopCardWs\(symbol\);', '', content)

with open("src/arbitrator/presentation/static/js/render/monitors.js", "w", encoding="utf-8") as f:
    f.write(content)
