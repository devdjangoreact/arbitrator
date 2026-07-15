import React, { useState } from "react";
import type { OrderGroup } from "../types";
import { fmtPnl, pnlClass, fmtNum } from "../utils/format";

interface RowProps {
  group: OrderGroup;
}

export const OrderGroupRow: React.FC<RowProps> = ({ group }) => {
  const [expanded, setExpanded] = useState(false);

  // Format dates: ISO string to readable localized
  const dateObj = new Date(group.opened_at);
  const dateStr = isNaN(dateObj.getTime())
    ? group.opened_at
    : dateObj.toLocaleString();

  return (
    <>
      <tr className="hover:bg-gray-50 border-b border-gray-100">
        <td
          className="w-8 text-center cursor-pointer text-gray-500 hover:text-indigo-600"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "▼" : "▶"}
        </td>
        <td className="font-bold text-gray-900">{group.asset}</td>
        <td>
          <div className="flex gap-2">
            <span className="bg-red-100 text-red-800 text-xs px-2 py-0.5 rounded font-medium uppercase">
              S: {group.short_exchange}
            </span>
            <span className="bg-green-100 text-green-800 text-xs px-2 py-0.5 rounded font-medium uppercase">
              L: {group.long_exchange}
            </span>
          </div>
        </td>
        <td>
          <span
            className={`text-xs px-2 py-1 rounded font-bold uppercase ${group.status === "open" ? "bg-blue-100 text-blue-800" : "bg-gray-200 text-gray-800"}`}
          >
            {group.status}
          </span>
        </td>
        <td className="text-gray-500 text-sm whitespace-nowrap">{dateStr}</td>
        <td className="text-sm">
          <div className="text-gray-600">In: {fmtNum(group.spread_in, 2)}%</div>
          {group.spread_out !== undefined && (
            <div className="text-gray-600">
              Out: {fmtNum(group.spread_out, 2)}%
            </div>
          )}
        </td>
        <td className="text-gray-600 text-sm">{fmtNum(group.total_fees, 4)}</td>
        <td className={`font-medium text-sm ${pnlClass(group.total_funding)}`}>
          {fmtPnl(group.total_funding)}
        </td>
        <td className={`font-bold text-base ${pnlClass(group.total_pnl)}`}>
          {fmtPnl(group.total_pnl)}
        </td>
      </tr>

      {expanded && (
        <tr className="bg-gray-50 border-b-2 border-gray-200">
          <td></td>
          <td colSpan={8} className="p-4">
            <table className="w-full text-sm">
              <thead className="text-gray-500 border-b border-gray-200">
                <tr>
                  <th className="pb-2 text-left font-medium">Leg</th>
                  <th className="pb-2 text-left font-medium">Volume</th>
                  <th className="pb-2 text-left font-medium">Entry</th>
                  <th className="pb-2 text-left font-medium">Exit</th>
                  <th className="pb-2 text-left font-medium">Fees</th>
                  <th className="pb-2 text-left font-medium">Funding</th>
                  <th className="pb-2 text-left font-medium">PnL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 border-b border-gray-200">
                {group.legs.map((leg, i) => (
                  <tr key={i} className="hover:bg-white">
                    <td className="py-2 flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${leg.side === "Short" ? "bg-red-500" : "bg-green-500"}`}
                      ></span>
                      <span className="font-semibold">{leg.side}</span>
                      <span className="uppercase text-gray-500">
                        {leg.exchange}
                      </span>
                      <span className="text-gray-400 border border-gray-300 rounded px-1 text-xs">
                        {leg.leverage}x
                      </span>
                    </td>
                    <td className="py-2 text-gray-700">
                      {fmtNum(leg.volume, 2)}
                    </td>
                    <td className="py-2 text-gray-700">
                      {fmtNum(leg.entry_price)}
                    </td>
                    <td className="py-2 text-gray-700">
                      {leg.exit_price !== undefined
                        ? fmtNum(leg.exit_price)
                        : "—"}
                    </td>
                    <td className="py-2 text-gray-600">
                      {fmtNum(leg.fees, 4)}
                    </td>
                    <td className={`py-2 ${pnlClass(leg.funding)}`}>
                      {fmtPnl(leg.funding)}
                    </td>
                    <td className={`py-2 font-medium ${pnlClass(leg.pnl)}`}>
                      {fmtPnl(leg.pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
};
