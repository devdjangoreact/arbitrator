import React, { useState, useEffect, useMemo } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { ScreenerFilterPanel } from "../components/ScreenerFilterPanel";
import { ScreenerDataTable } from "../components/ScreenerDataTable";
import type { ScreenerRow, SetScreenerFilterPayload } from "../types";

export const ScreenerPage: React.FC = () => {
  const { data, type, status, sendMessage } = useWebSocket<any>("/ws/screener");

  const [rows, setRows] = useState<ScreenerRow[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [backendStatus, setBackendStatus] = useState<string>("");

  const [minVol, setMinVol] = useState<number>(0);
  const [minSpread, setMinSpread] = useState<number>(0);
  const [defaultsLoaded, setDefaultsLoaded] = useState(false);

  useEffect(() => {
    if (!data) return;

    if (type === "screener.snapshot") {
      setBackendStatus(data.status || "Active");
      setTotalCount(data.symbol_count || 0);
      setRows(data.rows || []);

      if (!defaultsLoaded && data.filters) {
        if (data.filters.min_volume_k_usdt != null)
          setMinVol(data.filters.min_volume_k_usdt);
        if (data.filters.min_spread_pct != null)
          setMinSpread(data.filters.min_spread_pct);
        setDefaultsLoaded(true);
      }
    } else if (type === "screener.delta") {
      if (data.status != null) setBackendStatus(data.status);
      if (data.symbol_count != null) setTotalCount(data.symbol_count);

      setRows((prevRows) => {
        const rowMap = new Map(prevRows.map((r) => [r.asset, r]));

        for (const asset of data.rows_removed || []) {
          rowMap.delete(asset);
        }
        for (const row of data.rows_changed || []) {
          // Merge partial updates if necessary, or assume full replacement
          rowMap.set(row.asset, { ...rowMap.get(row.asset), ...row });
        }

        // Sort descending by spread_pct
        return Array.from(rowMap.values()).sort(
          (a, b) => (b.spread_pct || 0) - (a.spread_pct || 0),
        );
      });
    }
  }, [data, type, defaultsLoaded]);

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      if (row.vol_k_usdt !== undefined && row.vol_k_usdt < minVol) return false;
      if (row.spread_pct !== undefined && row.spread_pct < minSpread)
        return false;
      return true;
    });
  }, [rows, minVol, minSpread]);

  const displayStatus =
    status === "connecting"
      ? "Connecting..."
      : status === "closed"
        ? "Disconnected"
        : backendStatus;

  const handleApplyFilter = (payload: SetScreenerFilterPayload) => {
    // Update local state immediately for fast feedback
    setMinVol(payload.min_volume_k_usdt);
    setMinSpread(payload.min_spread_pct);
    sendMessage("screener.set_filter", payload);
  };

  const handleOpenOpportunity = (
    symbol: string,
    shortEx: string,
    longEx: string,
  ) => {
    // Open in new tab preserving the parameters
    window.open(
      `/?page=opportunity&asset=${symbol}&short=${shortEx}&long=${longEx}`,
      "_blank",
    );
  };

  return (
    <div className="p-4 w-full h-screen flex flex-col bg-gray-50">
      <h1 className="text-xl font-bold mb-4 text-gray-800">Live Screener</h1>

      <ScreenerFilterPanel
        status={displayStatus}
        filteredCount={filteredRows.length}
        totalCount={totalCount}
        initialMinVol={minVol}
        initialMinSpread={minSpread}
        onApply={handleApplyFilter}
      />

      <div className="flex-1 bg-white rounded shadow overflow-auto">
        <ScreenerDataTable
          rows={filteredRows}
          onOpenOpportunity={handleOpenOpportunity}
        />
      </div>
    </div>
  );
};
