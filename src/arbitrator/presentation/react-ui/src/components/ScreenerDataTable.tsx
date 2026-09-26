import React from "react";
import type { ScreenerRow } from "../types";
import { fmtNum, fmtStrategyProfit, pnlClass, compactK } from "../utils/format";

interface Props {
  rows: ScreenerRow[];
  exchanges?: string[];
  onOpenOpportunity: (symbol: string, shortEx: string, longEx: string) => void;
}

export const ScreenerDataTable: React.FC<Props> = ({
  rows,
  exchanges = [],
  onOpenOpportunity,
}) => {
  // Derive exchange list from rows if not passed explicitly
  const exchCols = exchanges.length > 0
    ? exchanges
    : Array.from(new Set(rows.flatMap((r) => Object.keys(r.prices ?? {}))));

  return (
    <div className="overflow-x-auto w-full">
      <table className="table-strict text-sm">
        <thead className="bg-gray-50 border-b-2 border-gray-200">
          <tr>
            <th>Asset</th>
            {exchCols.map((ex) => <th key={ex}>{ex.toUpperCase()}</th>)}
            <th>Max P</th>
            <th>Min P</th>
            <th>Spread</th>
            <th>Delta</th>
            <th>Vol(K)</th>
            <th>F-F</th>
            <th>F-S 2Ex</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={exchCols.length + 9} className="text-center py-4 text-gray-500">
                No data
              </td>
            </tr>
          ) : rows.map((row, i) => (
            <tr key={`${row.asset}-${i}`} className="hover:bg-gray-50">
              <td className="font-bold whitespace-nowrap">{row.asset}</td>
              {exchCols.map((ex) => {
                const price = row.prices?.[ex]?.futures;
                const isShort = row.short_exchange_id === ex;
                const isLong = row.long_exchange_id === ex;
                return (
                  <td key={ex} className={`text-xs ${isShort ? "text-red-600 font-bold" : isLong ? "text-green-600 font-bold" : "text-gray-600"}`}>
                    {price != null ? fmtNum(price) : "-"}
                  </td>
                );
              })}

              <td>{fmtNum(row.max_price)}</td>
              <td>{fmtNum(row.min_price)}</td>

              <td className={`font-bold ${pnlClass(row.spread_pct)}`}>
                {row.spread_pct > 0 ? "+" : ""}
                {fmtNum(row.spread_pct, 2)}%
              </td>

              <td className={pnlClass(row.spread_delta)}>
                {row.spread_delta != null && row.spread_delta > 0 ? "+" : ""}
                {fmtNum(row.spread_delta, 2)}%
              </td>

              <td>{compactK(row.volume_k_usdt)}</td>

              <td className={pnlClass(row.strategy_profits?.futures_futures)}>
                {fmtStrategyProfit(row.strategy_profits?.futures_futures)}
              </td>
              <td className={pnlClass(row.strategy_profits?.futures_spot_2ex)}>
                {fmtStrategyProfit(row.strategy_profits?.futures_spot_2ex)}
              </td>

              <td>
                <button
                  className="bg-blue-100 hover:bg-blue-200 text-blue-800 text-xs font-semibold py-1 px-2 rounded"
                  onClick={() => onOpenOpportunity(row.asset, row.short_exchange_id, row.long_exchange_id)}
                >
                  Open
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
