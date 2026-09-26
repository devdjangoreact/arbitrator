import React, { useState } from "react";
import { fmtNum, fmtPnl, pnlClass, compactK } from "../utils/format";
import type { HistoricalOpportunity } from "../types";

interface Props {
  opportunities: HistoricalOpportunity[];
  activeMonitorIds?: Set<string>;
  onCopyToForm: (opp: HistoricalOpportunity) => void;
  onFastTrade: (opp: HistoricalOpportunity) => void;
  onSpreadHistory?: (opp: HistoricalOpportunity) => void;
}

function fmtSecs(secs: number): string {
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h`;
}

export const HistoricalScreenerTable: React.FC<Props> = ({
  opportunities,
  activeMonitorIds,
  onCopyToForm,
  onFastTrade,
  onSpreadHistory,
}) => {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="bg-white rounded shadow overflow-x-auto">
      <div className="flex items-center gap-2 px-3 py-2 border-b">
        <button
          className="text-gray-500 hover:text-gray-800 text-xs leading-none"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Expand table" : "Collapse table"}
        >
          {collapsed ? "▶" : "▼"}
        </button>
        <h3 className="text-sm font-semibold">
          Found Opportunities
          {opportunities.length > 0 && (
            <span className="ml-1.5 text-gray-400 font-normal">({opportunities.length})</span>
          )}
        </h3>
      </div>
      {!collapsed && (
        <table className="table-strict text-xs w-full">
          <thead className="bg-gray-50 text-gray-700">
            <tr>
              <th className="px-2 py-1">Symbol</th>
              <th className="px-2 py-1">Δ / Exit</th>
              <th className="px-2 py-1">Signal</th>
              <th className="px-2 py-1">Exchanges</th>
              <th className="px-2 py-1">Funding Rate</th>
              <th className="px-2 py-1">Next Funding</th>
              <th className="px-2 py-1">F.Spread</th>
              <th className="px-2 py-1">Price</th>
              <th className="px-2 py-1">Vol 24h</th>
              <th className="px-2 py-1">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {opportunities.length === 0 ? (
              <tr>
                <td colSpan={10} className="text-center py-3 text-gray-500">
                  No opportunities found
                </td>
              </tr>
            ) : (
              opportunities.map((opp) => {
                const monitorId = `${opp.symbol}:${opp.short_exchange}:${opp.long_exchange}`;
                const isActive = activeMonitorIds?.has(monitorId) ?? false;
                const fundingSpread = opp.short_funding_rate - opp.long_funding_rate;
                return (
                  <tr key={monitorId} className="hover:bg-gray-50">
                    <td className="font-bold whitespace-nowrap px-2 py-0.5">{opp.symbol}</td>
                    <td className="whitespace-nowrap px-2 py-0.5">
                      <span className={`font-bold ${pnlClass(opp.current_spread_pct)}`}>
                        Δ {fmtPnl(opp.current_spread_pct)}
                      </span>
                      {" / "}
                      <span className="text-blue-700 font-bold">
                        {fmtPnl(opp.max_historical_spread_pct)}
                      </span>
                    </td>
                    <td className="text-gray-500 whitespace-nowrap px-2 py-0.5">
                      {opp.signal_time_seconds > 0 ? fmtSecs(opp.signal_time_seconds) : "-"}
                    </td>
                    <td className="px-2 py-0.5">
                      <div className="flex flex-col gap-0 font-bold uppercase">
                        <span className="text-red-600">
                          S: {opp.short_exchange}{isActive && <span className="ml-0.5 text-gray-400" title="Monitor active">⊘</span>}
                        </span>
                        <span className="text-green-600">
                          L: {opp.long_exchange}{isActive && <span className="ml-0.5 text-gray-400" title="Monitor active">⊘</span>}
                        </span>
                      </div>
                    </td>
                    <td className="px-2 py-0.5">
                      <div>S: <span className={pnlClass(opp.short_funding_rate)}>{fmtPnl(opp.short_funding_rate)}</span></div>
                      <div>L: <span className={pnlClass(opp.long_funding_rate)}>{fmtPnl(opp.long_funding_rate)}</span></div>
                    </td>
                    <td className="font-mono px-2 py-0.5">
                      <div>{opp.short_next_funding > 0 ? new Date(opp.short_next_funding * 1000).toLocaleTimeString() : "-"}</div>
                      <div>{opp.long_next_funding > 0 ? new Date(opp.long_next_funding * 1000).toLocaleTimeString() : "-"}</div>
                    </td>
                    <td className="px-2 py-0.5">
                      <span className={`font-bold ${pnlClass(fundingSpread)}`}>
                        {fmtPnl(fundingSpread)}
                      </span>
                    </td>
                    <td className="text-gray-600 px-2 py-0.5">
                      <div>S: {fmtNum(opp.short_price)}</div>
                      <div>L: {fmtNum(opp.long_price)}</div>
                    </td>
                    <td className="px-2 py-0.5">
                      <div>{compactK(opp.short_volume_24h)}</div>
                      <div>{compactK(opp.long_volume_24h)}</div>
                    </td>
                    <td className="px-2 py-0.5">
                      <div className="flex flex-col gap-0.5">
                        <button
                          className="bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold py-0.5 px-1.5 rounded whitespace-nowrap"
                          onClick={() => onCopyToForm(opp)}
                        >
                          Copy
                        </button>
                        <button
                          className="bg-blue-500 hover:bg-blue-600 text-white font-semibold py-0.5 px-1.5 rounded whitespace-nowrap"
                          onClick={() => onFastTrade(opp)}
                        >
                          ⚡ Fast
                        </button>
                        {onSpreadHistory && (
                          <button
                            className="bg-indigo-100 hover:bg-indigo-200 text-indigo-800 font-semibold py-0.5 px-1.5 rounded whitespace-nowrap"
                            onClick={() => onSpreadHistory(opp)}
                          >
                            📈 History
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      )}
    </div>
  );
};
