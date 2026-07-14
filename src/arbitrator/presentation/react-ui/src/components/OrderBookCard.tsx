import React from "react";
import { fmtNum } from "../utils/format";

export interface OrderBookLevel {
  price: number;
  volume: number;
}

interface Props {
  exchangeName: string;
  bestPriceLabel: string;
  bestPrice: number;
  asks: OrderBookLevel[]; // Sorted ascending (lowest ask first)
  bids: OrderBookLevel[]; // Sorted descending (highest bid first)
  type: "Short" | "Long";
}

export const OrderBookCard: React.FC<Props> = ({
  exchangeName,
  bestPriceLabel,
  bestPrice,
  asks,
  bids,
  type,
}) => {
  // Asks are displayed above the spread line, so we need to reverse them to show the lowest ask at the bottom (closest to the spread)
  // Assuming `asks` passed in are [lowest_ask, next_ask, ...]
  // We want to render: [..., next_ask, lowest_ask]
  const displayAsks = [...asks].reverse();

  return (
    <div className="bg-white rounded shadow flex flex-col h-full border border-gray-200">
      <div
        className={`p-3 border-b text-white font-bold flex justify-between items-center rounded-t ${type === "Short" ? "bg-red-500" : "bg-green-500"}`}
      >
        <span className="uppercase">{exchangeName}</span>
        <span className="text-sm">
          {bestPriceLabel}: {fmtNum(bestPrice)}
        </span>
      </div>

      <div className="flex-1 overflow-auto bg-gray-900 p-2">
        <table className="w-full text-xs font-mono text-right">
          <thead>
            <tr className="text-gray-400 border-b border-gray-700">
              <th className="pb-1 text-left">Price</th>
              <th className="pb-1">Volume</th>
            </tr>
          </thead>
          <tbody>
            {/* Asks (Red) */}
            {displayAsks.map((ask, i) => (
              <tr key={`ask-${i}`} className="text-red-400 hover:bg-gray-800">
                <td className="py-0.5 text-left">{fmtNum(ask.price)}</td>
                <td className="py-0.5">{fmtNum(ask.volume, 2)}</td>
              </tr>
            ))}

            {/* Spread Divider */}
            <tr>
              <td colSpan={2} className="py-1">
                <div className="h-px bg-gray-600 w-full"></div>
              </td>
            </tr>

            {/* Bids (Green) */}
            {bids.map((bid, i) => (
              <tr key={`bid-${i}`} className="text-green-400 hover:bg-gray-800">
                <td className="py-0.5 text-left">{fmtNum(bid.price)}</td>
                <td className="py-0.5">{fmtNum(bid.volume, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
