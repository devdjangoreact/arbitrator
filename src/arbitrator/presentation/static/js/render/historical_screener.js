let hsWs = null;

function initHistoricalScreener() {
  const reconnectBtn = document.getElementById("hist-reconnect");
  if (reconnectBtn) {
    reconnectBtn.addEventListener("click", () => {
      if (hsWs) {
        hsWs.send(JSON.stringify({ cmd: "refresh" }));
      } else {
        startHistoricalScreenerWs();
      }
    });
  }

  startHistoricalScreenerWs();
}

function startHistoricalScreenerWs() {
  if (hsWs) {
    hsWs.close();
  }

  const loc = window.location;
  const wsUri = (loc.protocol === "https:" ? "wss:" : "ws:") + "//" + loc.host + "/ws/historical_screener";
  hsWs = new WebSocket(wsUri);

  hsWs.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "historical_screener_update") {
        renderHistoricalScreenerTable(msg.data);
      }
    } catch (e) {
      console.error("Historical Screener JSON parse error:", e);
    }
  };

  hsWs.onclose = () => {
    setTimeout(() => {
      if (AppState.activePage === "historical_screener") {
        startHistoricalScreenerWs();
      }
    }, 2000);
  };
}

function stopHistoricalScreenerWs() {
  if (hsWs) {
    hsWs.close();
    hsWs = null;
  }
}

function renderHistoricalScreenerTable(opportunities) {
  const tbody = document.getElementById("hist-tbody");
  if (!tbody) return;

  if (!opportunities || opportunities.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No historical opportunities found yet</td></tr>';
    return;
  }

  let html = "";
  opportunities.forEach(opp => {
    const d = new Date(opp.detected_at * 1000);
    const timeStr = d.toLocaleTimeString();
    html += `<tr>
      <td><a href="#" onclick="showPage('opportunity'); if(window.setOpportunitySymbol) window.setOpportunitySymbol('${opp.symbol}', '${opp.short_ex}', '${opp.long_ex}'); return false;">${opp.symbol}</a></td>
      <td>${opp.short_ex}</td>
      <td>${opp.long_ex}</td>
      <td>${opp.max_historical_spread_pct.toFixed(2)}%</td>
      <td>${timeStr}</td>
      <td>${opp.lookback_minutes}</td>
      <td>${opp.status || "Unknown"}</td>
    </tr>`;
  });

  tbody.innerHTML = html;
}

// Ensure init is called
document.addEventListener("DOMContentLoaded", () => {
  // Bind to navigation to start/stop WS if needed, or just let it run.
  // Using AppState activePage logic if possible, or just start it.
  if (document.getElementById("page-historical_screener")) {
    initHistoricalScreener();
  }
});
