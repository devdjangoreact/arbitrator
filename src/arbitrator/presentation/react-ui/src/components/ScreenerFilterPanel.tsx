import React, { useState, useEffect } from "react";
import type { SetScreenerFilterPayload } from "../types";

interface Props {
  status: string;
  filteredCount: number;
  totalCount: number;
  initialMinVol: number;
  initialMinSpread: number;
  onApply: (payload: SetScreenerFilterPayload) => void;
}

export const ScreenerFilterPanel: React.FC<Props> = ({
  status,
  filteredCount,
  totalCount,
  initialMinVol,
  initialMinSpread,
  onApply,
}) => {
  const [minVol, setMinVol] = useState(initialMinVol);
  const [minSpread, setMinSpread] = useState(initialMinSpread);

  // Sync state if backend initial values change
  useEffect(() => {
    setMinVol(initialMinVol);
    setMinSpread(initialMinSpread);
  }, [initialMinVol, initialMinSpread]);

  const handleApply = () => {
    onApply({
      min_volume_k_usdt: minVol,
      min_spread_pct: minSpread,
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-4 bg-white p-4 rounded shadow mb-4">
      <div className="flex items-center gap-2">
        <span
          className={`px-2 py-1 text-xs rounded font-bold ${status === "Connected" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}
        >
          {status}
        </span>
        <span className="text-sm text-gray-600">
          {filteredCount} / {totalCount} пар
        </span>
      </div>

      <div className="flex items-center gap-2">
        <label className="text-sm font-medium">Min 24h vol (K USDT):</label>
        <input
          type="number"
          value={minVol}
          onChange={(e) => setMinVol(Number(e.target.value))}
          className="border border-gray-300 rounded px-2 py-1 w-24"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-sm font-medium">Min spread %:</label>
        <input
          type="number"
          step="0.1"
          value={minSpread}
          onChange={(e) => setMinSpread(Number(e.target.value))}
          className="border border-gray-300 rounded px-2 py-1 w-24"
        />
      </div>

      <button
        onClick={handleApply}
        className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-1 px-4 rounded"
      >
        Apply to Server
      </button>
    </div>
  );
};
