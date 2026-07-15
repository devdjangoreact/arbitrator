import React from "react";
import type { ScreenerRow } from "../types";
import { fmtNum, fmtStrategyProfit, pnlClass, compactK } from "../utils/format";

interface Props {
  rows: ScreenerRow[];
  onOpenOpportunity: (symbol: string, shortEx: string, longEx: string) => void;
}

export const ScreenerDataTable: React.FC<Props> = ({
  rows,
  onOpenOpportunity,
}) => {
  return (
    <div className="overflow-x-auto w-full">
      <table className="table-strict text-sm">
        <thead className="bg-gray-50 border-b-2 border-gray-200">
          <tr>
            <th>Asset</th>
            <th>MEXC</th>
            <th>BITGET</th>
            <th>GATE</th>
            <th>BINGX</th>
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
          {rows.map((row, i) => (
            <tr key={`${row.asset}-${i}`} className="hover:bg-gray-50">
              <td className="font-bold whitespace-nowrap">{row.asset}</td>
              {/* Mock columns for exchanges - in reality this would be dynamic or parsed from the row */}
              <td>
                <div className="text-xs text-gray-500">
                  F: {fmtNum(row.max_p)}
                </div>
                <div className="text-xs text-gray-500">
                  S: {fmtNum(row.min_p)}
                </div>
              </td>
              <td>-</td>
              <td>-</td>
              <td>-</td>

              <td>{fmtNum(row.max_p)}</td>
              <td>{fmtNum(row.min_p)}</td>

              {/* Exact formatting logic using the new utils */}
              <td className={`font-bold ${pnlClass(row.spread_pct)}`}>
                {row.spread_pct > 0 ? "+" : ""}
                {fmtNum(row.spread_pct, 2)}%
              </td>

              <td className={pnlClass(row.delta)}>
                {row.delta && row.delta > 0 ? "+" : ""}
                {fmtNum(row.delta, 2)}%
              </td>

              <td>{compactK(row.vol_k_usdt)}</td>

              <td className={pnlClass(row.profits.futures_futures)}>
                {fmtStrategyProfit(row.profits.futures_futures)}
              </td>
              <td className={pnlClass(row.profits.futures_spot_2ex)}>
                {fmtStrategyProfit(row.profits.futures_spot_2ex)}
              </td>

              <td>
                <button
                  className="bg-blue-100 hover:bg-blue-200 text-blue-800 text-xs font-semibold py-1 px-2 rounded"
                  onClick={() =>
                    onOpenOpportunity(
                      row.asset,
                      row.short_exchange_id,
                      row.long_exchange_id,
                    )
                  }
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
