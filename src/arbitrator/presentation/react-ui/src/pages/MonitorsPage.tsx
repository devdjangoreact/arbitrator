import React, { useState, useEffect, useCallback } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { HistoricalScreenerTable } from "../components/HistoricalScreenerTable";
import { LiveMonitorCard } from "../components/LiveMonitorCard";
import { SpreadHistoryModal } from "../components/SpreadHistoryModal";
import type {
  MonitorConfig,
  UpdateConfigPayload,
  HistoricalOpportunity,
} from "../types";

export const MonitorsPage: React.FC = () => {
  const { data, status: wsStatus, sendMessage } = useWebSocket<any>("/ws/historical_screener");

  const [opportunities, setOpportunities] = useState<HistoricalOpportunity[]>([]);
  const [monitors, setMonitors] = useState<MonitorConfig[]>([]);
  const [screenerStatus, setScreenerStatus] = useState<string>("Idle");
  const [supportsAnalysisVol, setSupportsAnalysisVol] = useState(false);
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(new Set());
  const [spreadHistoryId, setSpreadHistoryId] = useState<string | null>(null);

  // Filter state
  const [lookbackSeconds, setLookbackSeconds] = useState(1800);
  const [minSpread, setMinSpread] = useState(1.0);
  const [minVol, setMinVol] = useState(100000);
  const [minAnalysisVol, setMinAnalysisVol] = useState(0);
  const [pushInterval, setPushInterval] = useState(5);
  const [candleInterval, setCandleInterval] = useState(5);
  const [priceDevFilter, setPriceDevFilter] = useState(0.0);

  useEffect(() => {
    if (wsStatus !== "open") return;
    handleUpdateFilters();
  }, [wsStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!data) return;
    if (data.type === "error" && data.data?.code === "duplicate_monitor") {
      setDuplicateWarning(`Monitor already exists: ${data.data.monitor_id}`);
      setTimeout(() => setDuplicateWarning(null), 4000);
      return;
    }
    const payload = data.data ?? data;
    if (payload.opportunities !== undefined) setOpportunities(payload.opportunities);
    if (payload.monitors !== undefined) setMonitors(payload.monitors);
    if (payload.status !== undefined) setScreenerStatus(payload.status);
    if (payload.supports_analysis_volume_filter !== undefined)
      setSupportsAnalysisVol(payload.supports_analysis_volume_filter);
  }, [data]);

  const handleUpdateFilters = useCallback(() => {
    sendMessage("update_filters", {
      lookback_seconds: lookbackSeconds,
      min_spread_pct: minSpread,
      min_volume_usdt: minVol,
      min_analysis_volume_usdt: minAnalysisVol,
      push_interval_seconds: pushInterval,
      candle_interval_seconds: candleInterval,
      price_deviation_filter_pct: priceDevFilter,
    });
  }, [lookbackSeconds, minSpread, minVol, minAnalysisVol, pushInterval, candleInterval, priceDevFilter, sendMessage]);

  const handleStartMonitoring = () => sendMessage("start", {});
  const handleStopMonitoring = () => sendMessage("stop", {});

  const handleCopyToForm = (opp: HistoricalOpportunity) => {
    sendMessage("add_monitor", {
      symbol: opp.symbol,
      short_exchange: opp.short_exchange,
      long_exchange: opp.long_exchange,
      max_spread: opp.max_historical_spread_pct,
      auto_start: false,
    });
  };

  const handleFastTrade = (opp: HistoricalOpportunity) => {
    sendMessage("add_monitor", {
      symbol: opp.symbol,
      short_exchange: opp.short_exchange,
      long_exchange: opp.long_exchange,
      max_spread: opp.max_historical_spread_pct,
      auto_start: true,
    });
  };

  const handleUpdateConfig = (payload: UpdateConfigPayload) => {
    sendMessage(payload.cmd, payload);
  };

  const handleCloseMonitor = (id: string) => {
    sendMessage("remove", { monitor_id: id });
  };

  const handleRestartMonitor = (id: string) => {
    sendMessage("restart", { monitor_id: id });
  };

  const isRunning = screenerStatus === "Running";
  const isIdle = screenerStatus === "Idle";

  const togglePin = (id: string) => {
    setPinnedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const sortedMonitors = [...monitors].sort((a, b) => {
    const pa = pinnedIds.has(a.id) ? 0 : 1;
    const pb = pinnedIds.has(b.id) ? 0 : 1;
    return pa - pb;
  });

  const spreadHistoryConfig = spreadHistoryId
    ? monitors.find((m) => m.id === spreadHistoryId) ?? null
    : null;

  return (
    <div className="w-full min-h-screen bg-gray-50 flex flex-col font-sans">
      {spreadHistoryConfig && (
        <SpreadHistoryModal
          config={spreadHistoryConfig}
          onClose={() => setSpreadHistoryId(null)}
        />
      )}

      {duplicateWarning && (
        <div className="bg-yellow-100 border border-yellow-400 text-yellow-800 text-sm px-4 py-2 text-center">
          ⚠ {duplicateWarning}
        </div>
      )}

      {/* Controls */}
      <div className="bg-white p-4 flex flex-wrap gap-4 items-end border-b border-gray-200">
        <div>
          <label className="block text-xs text-gray-600 mb-1">Analysis Period (s)</label>
          <input type="number" className="border border-gray-300 rounded px-2 py-1 w-28 text-sm outline-none focus:border-blue-500"
            value={lookbackSeconds} onChange={(e) => setLookbackSeconds(Number(e.target.value))} onBlur={handleUpdateFilters} />
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">Min Spread %</label>
          <input type="number" step="0.1" className="border border-gray-300 rounded px-2 py-1 w-24 text-sm outline-none focus:border-blue-500"
            value={minSpread} onChange={(e) => setMinSpread(Number(e.target.value))} onBlur={handleUpdateFilters} />
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">Min 24h Vol (USDT)</label>
          <input type="number" className="border border-gray-300 rounded px-2 py-1 w-32 text-sm outline-none focus:border-blue-500"
            value={minVol} onChange={(e) => setMinVol(Number(e.target.value))} onBlur={handleUpdateFilters} />
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1 whitespace-nowrap">
            Min Analysis Vol (USDT){!supportsAnalysisVol && <span className="ml-1 text-gray-400">(unavailable)</span>}
          </label>
          <input type="number" className="border border-gray-300 rounded px-2 py-1 w-32 text-sm outline-none focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-400"
            value={minAnalysisVol} disabled={!supportsAnalysisVol}
            onChange={(e) => setMinAnalysisVol(Number(e.target.value))} onBlur={handleUpdateFilters} />
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">Refresh Interval (s)</label>
          <input type="number" min="1" className="border border-gray-300 rounded px-2 py-1 w-24 text-sm outline-none focus:border-blue-500"
            value={pushInterval} onChange={(e) => setPushInterval(Math.max(1, Number(e.target.value)))} onBlur={handleUpdateFilters} />
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">Candle Interval (s)</label>
          <select className="border border-gray-300 rounded px-2 py-1 text-sm outline-none focus:border-blue-500"
            value={candleInterval} onChange={(e) => setCandleInterval(Number(e.target.value))} onBlur={handleUpdateFilters}>
            {[5, 15, 30, 60].map((v) => <option key={v} value={v}>{v}s</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">Price Dev Filter %</label>
          <input type="number" step="0.1" className="border border-gray-300 rounded px-2 py-1 w-28 text-sm outline-none focus:border-blue-500"
            value={priceDevFilter} onChange={(e) => setPriceDevFilter(Number(e.target.value))} onBlur={handleUpdateFilters} placeholder="0 = off" />
        </div>
        <div className="flex gap-2 ml-4 items-end">
          <span className="text-xs text-gray-500 self-center">{screenerStatus}</span>
          <button onClick={handleStartMonitoring} disabled={isRunning}
            className="bg-[#2ecc71] hover:bg-[#27ae60] disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold py-1.5 px-4 rounded">
            Start
          </button>
          <button onClick={handleStopMonitoring} disabled={isIdle}
            className="bg-[#e74c3c] hover:bg-[#c0392b] disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold py-1.5 px-4 rounded">
            Stop
          </button>
        </div>
      </div>

      <div className="p-4 flex flex-col gap-4">
        <HistoricalScreenerTable
          opportunities={opportunities}
          activeMonitorIds={new Set(monitors.map((m) => m.id))}
          onCopyToForm={handleCopyToForm}
          onFastTrade={handleFastTrade}
          onSpreadHistory={(opp) => {
            // Find existing monitor or use opp id
            const id = `${opp.symbol}:${opp.short_exchange}:${opp.long_exchange}`;
            const existing = monitors.find((m) => m.id === id);
            if (existing) setSpreadHistoryId(existing.id);
          }}
        />

        {/* Monitor cards — auto-fill columns ~400px each, like reference */}
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(360px, 460px))" }}>
          {sortedMonitors.map((config) => (
            <LiveMonitorCard
              key={config.id}
              config={config}
              pinned={pinnedIds.has(config.id)}
              onPin={togglePin}
              onUpdate={handleUpdateConfig}
              onClose={handleCloseMonitor}
              onRestart={handleRestartMonitor}
              onSpreadHistory={setSpreadHistoryId}
            />
          ))}
          {monitors.length === 0 && (
            <div className="p-8 text-center text-gray-400 bg-white border border-dashed rounded">
              No active monitors. Use "Fast Trade" from the table above to start one.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
