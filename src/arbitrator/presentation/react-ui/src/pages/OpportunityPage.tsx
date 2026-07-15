import React, { useState, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { OpportunityChart } from "../components/OpportunityChart";
import { StrategyCalculationsTable } from "../components/StrategyCalculationsTable";
import { OrderBookCard } from "../components/OrderBookCard";
import type { OpportunityActionPayload } from "../types";

export const OpportunityPage: React.FC = () => {
  const getQueryParam = (key: string, defaultVal: string) => {
    const params = new URLSearchParams(window.location.search);
    return params.get(key) || defaultVal;
  };

  const [symbol, setSymbol] = useState(getQueryParam("asset", "DOGE/USDT"));
  const [shortEx, setShortEx] = useState(getQueryParam("short", "binance"));
  const [longEx, setLongEx] = useState(getQueryParam("long", "mexc"));

  const [activeUrl, setActiveUrl] = useState(
    `/ws/opportunity?symbol=${encodeURIComponent(symbol)}&short=${shortEx}&long=${longEx}`,
  );

  const handleLoad = () => {
    setActiveUrl(
      `/ws/opportunity?symbol=${encodeURIComponent(symbol)}&short=${shortEx}&long=${longEx}`,
    );
  };

  const { data, status, sendMessage } = useWebSocket<any>(activeUrl);

  const [chartData, setChartData] = useState<any[]>([]);

  useEffect(() => {
    if (!data) return;

    // Append to chart data on each update (basic mock-up of streaming logic)
    if (data.strategy_rows && data.books) {
      const spread =
        data.strategy_rows.find((r: any) => r.name === "futures_futures")
          ?.spread_pct || 0;
      const shortBook = data.books.find((b: any) => b.side === "short");
      const longBook = data.books.find((b: any) => b.side === "long");

      setChartData((prev) => {
        const newData = [
          ...prev,
          {
            time: new Date().toLocaleTimeString(),
            spread: spread,
            shortPrice: shortBook?.best_ask,
            longPrice: longBook?.best_bid,
          },
        ];
        // Keep last 50 points
        if (newData.length > 50) return newData.slice(newData.length - 50);
        return newData;
      });
    }
  }, [data]);

  const handleExecuteStrategy = (strategy: string) => {
    const payload: OpportunityActionPayload = {
      action: "accumulate",
      symbol,
      strategy,
    };
    sendMessage("opportunity.action", payload);
  };

  const handleAction = (
    action: "accumulate" | "close_partial" | "close_all",
  ) => {
    const payload: OpportunityActionPayload = { action, symbol };
    sendMessage("opportunity.action", payload);
  };

  const shortBookData = data?.books?.find((b: any) => b.side === "short");
  const longBookData = data?.books?.find((b: any) => b.side === "long");

  return (
    <div className="p-4 w-full min-h-screen bg-gray-100 flex flex-col gap-4">
      {/* Top Panel */}
      <div className="bg-white p-4 rounded shadow flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
            Symbol
          </label>
          <input
            className="border rounded px-2 py-1 w-32"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
            Short Ex
          </label>
          <input
            className="border rounded px-2 py-1 w-24"
            value={shortEx}
            onChange={(e) => setShortEx(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
            Long Ex
          </label>
          <input
            className="border rounded px-2 py-1 w-24"
            value={longEx}
            onChange={(e) => setLongEx(e.target.value)}
          />
        </div>
        <button
          onClick={handleLoad}
          className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-1 px-4 rounded"
        >
          Load Data
        </button>

        <div className="ml-auto flex gap-2 items-center">
          <span className="text-sm font-bold text-gray-500 mr-2">
            {status === "open" ? "Connected" : "Disconnected"}
          </span>
          <span className="bg-red-100 text-red-800 px-3 py-1 rounded font-bold uppercase">
            S: {shortEx}
          </span>
          <span className="bg-green-100 text-green-800 px-3 py-1 rounded font-bold uppercase">
            L: {longEx}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Main Content (Chart & Strategies) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <OpportunityChart
            data={chartData}
            shortEx={shortEx}
            longEx={longEx}
          />

          <StrategyCalculationsTable
            calculations={
              data?.strategy_rows?.map((r: any) => ({
                strategy_name: r.name,
                spread_pct: r.spread_pct || 0,
                delta: r.spread_delta || 0,
                fee_pct: r.fee_pct,
                max_vol: r.max_volume,
                details:
                  r.reasons && r.reasons.length > 0
                    ? r.reasons.join(", ")
                    : "OK",
              })) || []
            }
            onExecute={handleExecuteStrategy}
          />

          {/* Trading Actions */}
          <div className="bg-white p-4 rounded shadow">
            <h3 className="text-md font-semibold mb-3">Trading Actions</h3>
            <div className="flex gap-2">
              <button
                onClick={() => handleAction("accumulate")}
                className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
              >
                Добрати (Accumulate)
              </button>
              <button
                onClick={() => handleAction("close_partial")}
                className="bg-orange-500 hover:bg-orange-600 text-white font-bold py-2 px-4 rounded"
              >
                Закрити (Close Partial)
              </button>
              <button
                onClick={() => handleAction("close_all")}
                className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
              >
                Закрити всі позиції (Close All)
              </button>
            </div>
          </div>
        </div>

        {/* Order Books Sidebar */}
        <div className="flex flex-col gap-4 h-[800px]">
          <h3 className="text-md font-semibold hidden lg:block">Order Books</h3>
          <div className="flex-1 min-h-[300px]">
            {shortBookData ? (
              <OrderBookCard
                exchangeName={shortBookData.exchange_id}
                type="Short"
                bestPriceLabel="Best Ask"
                bestPrice={shortBookData.best_ask}
                asks={shortBookData.asks.slice(0, 15)}
                bids={shortBookData.bids.slice(0, 15)}
              />
            ) : (
              <div className="bg-white rounded shadow h-full flex items-center justify-center text-gray-400">
                Loading Short Book...
              </div>
            )}
          </div>
          <div className="flex-1 min-h-[300px]">
            {longBookData ? (
              <OrderBookCard
                exchangeName={longBookData.exchange_id}
                type="Long"
                bestPriceLabel="Best Bid"
                bestPrice={longBookData.best_bid}
                asks={longBookData.asks.slice(0, 15)}
                bids={longBookData.bids.slice(0, 15)}
              />
            ) : (
              <div className="bg-white rounded shadow h-full flex items-center justify-center text-gray-400">
                Loading Long Book...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
