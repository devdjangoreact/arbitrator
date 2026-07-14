import React from "react";
import { fmtNum, fmtPnl, pnlClass, compactK } from "../utils/format";

interface OpportunityRow {
  symbol: string;
  short_exchange: string;
  long_exchange: string;
  short_funding: number;
  long_funding: number;
  next_funding_timer: string;
  funding_spread: number;
  short_price: number;
  long_price: number;
  volume_usdt: number;
}

interface Props {
  opportunities: OpportunityRow[];
  onCopyToForm: (opp: OpportunityRow) => void;
  onFastTrade: (opp: OpportunityRow) => void;
}

export const HistoricalScreenerTable: React.FC<Props> = ({
  opportunities,
  onCopyToForm,
  onFastTrade,
}) => {
  return (
    <div className="bg-white rounded shadow overflow-x-auto">
      <h3 className="text-md font-semibold p-4 border-b">
        Found Opportunities
      </h3>
      <table className="table-strict text-sm">
        <thead className="bg-gray-50 text-gray-700">
          <tr>
            <th>Symbol</th>
            <th>Exchanges</th>
            <th>Funding Rate</th>
            <th>Next Funding</th>
            <th>Funding Spread</th>
            <th>Price</th>
            <th>Volume USDT ↕</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {opportunities.length === 0 ? (
            <tr>
              <td colSpan={8} className="text-center py-4 text-gray-500">
                No opportunities found
              </td>
            </tr>
          ) : (
            opportunities.map((opp, i) => (
              <tr key={`${opp.symbol}-${i}`} className="hover:bg-gray-50">
                <td className="font-bold whitespace-nowrap">{opp.symbol}</td>
                <td>
                  <div className="flex flex-col gap-1 text-xs font-bold uppercase">
                    <span className="text-red-600">
                      S: {opp.short_exchange}
                    </span>
                    <span className="text-green-600">
                      L: {opp.long_exchange}
                    </span>
                  </div>
                </td>
                <td className="text-xs">
                  <div>
                    S:{" "}
                    <span className={pnlClass(opp.short_funding)}>
                      {fmtPnl(opp.short_funding)}
                    </span>
                  </div>
                  <div>
                    L:{" "}
                    <span className={pnlClass(opp.long_funding)}>
                      {fmtPnl(opp.long_funding)}
                    </span>
                  </div>
                </td>
                <td className="font-mono text-xs">{opp.next_funding_timer}</td>
                <td className={`font-bold ${pnlClass(opp.funding_spread)}`}>
                  {fmtPnl(opp.funding_spread)}
                </td>
                <td className="text-xs text-gray-600">
                  <div>S: {fmtNum(opp.short_price)}</div>
                  <div>L: {fmtNum(opp.long_price)}</div>
                </td>
                <td>{compactK(opp.volume_usdt)}</td>
                <td>
                  <div className="flex flex-col gap-1">
                    <button
                      className="bg-gray-200 hover:bg-gray-300 text-gray-800 text-xs font-semibold py-1 px-2 rounded w-full whitespace-nowrap"
                      onClick={() => onCopyToForm(opp)}
                    >
                      Copy to Form
                    </button>
                    <button
                      className="bg-blue-500 hover:bg-blue-600 text-white text-xs font-semibold py-1 px-2 rounded w-full whitespace-nowrap"
                      onClick={() => onFastTrade(opp)}
                    >
                      Fast Trade
                    </button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};
