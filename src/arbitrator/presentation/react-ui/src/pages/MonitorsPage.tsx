import React, { useState, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { HistoricalScreenerTable } from "../components/HistoricalScreenerTable";
import { LiveMonitorCard } from "../components/LiveMonitorCard";
import type { MonitorConfig, UpdateConfigPayload } from "../types";

export const MonitorsPage: React.FC = () => {
  const { data, sendMessage } = useWebSocket<any>("/ws/historical_screener");

  const [opportunities, setOpportunities] = useState<any[]>([]);
  const [monitors, setMonitors] = useState<MonitorConfig[]>([]);

  const [timeWindow, setTimeWindow] = useState(3800);
  const [minSpread, setMinSpread] = useState(1.0);
  const [minVol, setMinVol] = useState(0);

  useEffect(() => {
    // Mock Data for layout if WS is unavailable
    setOpportunities([]);

    setMonitors([
      {
        id: "mon-1",
        symbol: "ADI",
        short_exchange: "GATE",
        long_exchange: "BITGET",
        side: "Auto",
        open_spread_pct: 1.0,
        open_ticks: 2,
        close_spread_pct: 0.1,
        close_ticks: 1,
        order_size_usdt: 100,
        max_orders: 1,
        force_stop: false,
        total_stop: false,
        is_active: true,
      },
      {
        id: "mon-2",
        symbol: "AKE",
        short_exchange: "BINGX",
        long_exchange: "GATE",
        side: "Auto",
        open_spread_pct: 1.0,
        open_ticks: 2,
        close_spread_pct: 0.1,
        close_ticks: 1,
        order_size_usdt: 100,
        max_orders: 1,
        force_stop: false,
        total_stop: false,
        is_active: false,
      },
      {
        id: "mon-3",
        symbol: "ALPINE",
        short_exchange: "MEXC",
        long_exchange: "GATE",
        side: "Auto",
        open_spread_pct: 1.0,
        open_ticks: 2,
        close_spread_pct: 0.1,
        close_ticks: 1,
        order_size_usdt: 100,
        max_orders: 1,
        force_stop: false,
        total_stop: false,
        is_active: false,
      },
    ]);
  }, []);

  useEffect(() => {
    if (!data) return;
    if (data.opportunities) setOpportunities(data.opportunities);
    if (data.monitors) setMonitors(data.monitors);
  }, [data]);

  const handleUpdateFilters = () => {
    sendMessage("update_filters", { timeWindow, minSpread, minVol });
  };

  const handleStartMonitoring = () => sendMessage("start", {});
  const handleStopMonitoring = () => sendMessage("stop", {});

  const handleCopyToForm = (opp: any) => {
    console.log("Copy to form", opp.symbol);
  };

  const handleFastTrade = (opp: any) => {
    sendMessage("add_monitor", {
      symbol: opp.symbol,
      short_exchange: opp.short_exchange,
      long_exchange: opp.long_exchange,
      auto_start: true,
    });
  };

  const handleUpdateConfig = (payload: UpdateConfigPayload) => {
    sendMessage(payload.cmd, payload);
  };

  const handleCloseMonitor = (id: string) => {
    sendMessage("remove", { monitor_id: id });
  };

  return (
    <div className="w-full min-h-screen bg-gray-50 flex flex-col font-sans">
      {/* Top Panel Controls */}
      <div className="bg-white p-4 flex flex-wrap gap-4 items-end border-b border-gray-200">
        <div>
          <label className="block text-xs text-gray-600 mb-1">
            Time Window (seconds)
          </label>
          <input
            type="number"
            className="border border-gray-300 rounded px-2 py-1 w-32 text-sm outline-none focus:border-blue-500"
            value={timeWindow}
            onChange={(e) => setTimeWindow(Number(e.target.value))}
            onBlur={handleUpdateFilters}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">
            Min Spread %
          </label>
          <input
            type="number"
            step="0.1"
            className="border border-gray-300 rounded px-2 py-1 w-24 text-sm outline-none focus:border-blue-500"
            value={minSpread}
            onChange={(e) => setMinSpread(Number(e.target.value))}
            onBlur={handleUpdateFilters}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">
            Min 24h Vol (USDT)
          </label>
          <input
            type="number"
            className="border border-gray-300 rounded px-2 py-1 w-32 text-sm outline-none focus:border-blue-500"
            value={minVol}
            onChange={(e) => setMinVol(Number(e.target.value))}
            onBlur={handleUpdateFilters}
          />
        </div>

        <div className="flex gap-2 ml-4">
          <button
            onClick={handleStartMonitoring}
            className="bg-[#2ecc71] hover:bg-[#27ae60] text-white text-sm font-semibold py-1.5 px-4 rounded"
          >
            Start Monitoring
          </button>
          <button
            onClick={handleStopMonitoring}
            className="bg-[#e74c3c] hover:bg-[#c0392b] text-white text-sm font-semibold py-1.5 px-4 rounded"
          >
            Stop Monitoring
          </button>
        </div>
      </div>

      <div className="p-4 flex flex-col gap-4">
        {/* Historical Opportunities Table */}
        <HistoricalScreenerTable
          opportunities={opportunities}
          onCopyToForm={handleCopyToForm}
          onFastTrade={handleFastTrade}
        />

        {/* Live Monitors Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {monitors.map((config) => (
            <LiveMonitorCard
              key={config.id}
              config={config}
              onUpdate={handleUpdateConfig}
              onClose={handleCloseMonitor}
            />
          ))}
          {monitors.length === 0 && (
            <div className="col-span-full p-8 text-center text-gray-400 bg-white border border-dashed rounded">
              No active monitors. Use "Fast Trade" from the table above to start
              one.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};