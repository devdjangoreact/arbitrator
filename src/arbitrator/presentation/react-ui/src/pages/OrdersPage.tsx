import React, { useState, useEffect, useMemo } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { OrdersSummaryPanel } from "../components/OrdersSummaryPanel";
import { OrderGroupRow } from "../components/OrderRow";
import type { OrderGroup } from "../types";

export const OrdersPage: React.FC = () => {
  const { data, status } = useWebSocket<any>("/ws/orders");
  const [orders, setOrders] = useState<OrderGroup[]>([]);
  const [filter, setFilter] = useState<"all" | "open" | "closed">("open");

  useEffect(() => {
    // Mock data for initial render since WS won't return without backend
    setOrders([
      {
        id: "1",
        asset: "DOGE/USDT",
        short_exchange: "binance",
        long_exchange: "mexc",
        status: "open",
        opened_at: new Date(Date.now() - 3600000).toISOString(),
        spread_in: 1.5,
        total_fees: 0.15,
        total_funding: -0.05,
        total_pnl: 10.5,
        legs: [
          {
            side: "Short",
            exchange: "binance",
            leverage: 10,
            volume: 1000,
            entry_price: 0.125,
            fees: 0.08,
            funding: -0.02,
            pnl: 5.2,
          },
          {
            side: "Long",
            exchange: "mexc",
            leverage: 10,
            volume: 1000,
            entry_price: 0.123,
            fees: 0.07,
            funding: -0.03,
            pnl: 5.3,
          },
        ],
      },
      {
        id: "2",
        asset: "BTC/USDT",
        short_exchange: "bitget",
        long_exchange: "gate",
        status: "closed",
        opened_at: new Date(Date.now() - 86400000).toISOString(),
        spread_in: 0.2,
        spread_out: -0.1,
        total_fees: 2.5,
        total_funding: 1.2,
        total_pnl: -5.4,
        legs: [
          {
            side: "Short",
            exchange: "bitget",
            leverage: 5,
            volume: 0.1,
            entry_price: 65000,
            exit_price: 64900,
            fees: 1.2,
            funding: 0.5,
            pnl: -2.0,
          },
          {
            side: "Long",
            exchange: "gate",
            leverage: 5,
            volume: 0.1,
            entry_price: 64800,
            exit_price: 64950,
            fees: 1.3,
            funding: 0.7,
            pnl: -3.4,
          },
        ],
      },
    ]);
  }, []);

  useEffect(() => {
    if (data && Array.isArray(data)) {
      setOrders(data);
    } else if (data && data.groups) {
      setOrders(data.groups);
    }
  }, [data]);

  const filteredOrders = useMemo(() => {
    if (filter === "all") return orders;
    return orders.filter((o) => o.status === filter);
  }, [orders, filter]);

  // Calculate totals based on ALL orders for the summary panel
  const totals = useMemo(() => {
    return orders.reduce(
      (acc, order) => {
        acc.pnl += order.total_pnl;
        acc.fees += order.total_fees;
        acc.funding += order.total_funding;
        return acc;
      },
      { pnl: 0, fees: 0, funding: 0 },
    );
  }, [orders]);

  const openCount = orders.filter((o) => o.status === "open").length;
  const closedCount = orders.filter((o) => o.status === "closed").length;

  return (
    <div className="p-4 w-full min-h-screen bg-gray-50 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">
          Orders & Paper Trades
        </h1>
        <div className="text-sm font-bold text-gray-500">
          {status === "open" ? (
            <span className="text-green-600">WS Connected</span>
          ) : (
            <span className="text-red-500">WS Disconnected</span>
          )}
        </div>
      </div>

      <OrdersSummaryPanel
        totalPnl={totals.pnl}
        totalFees={totals.fees}
        totalFunding={totals.funding}
        openCount={openCount}
        closedCount={closedCount}
        activeFilter={filter}
        onFilterChange={setFilter}
      />

      <div className="flex-1 bg-white rounded shadow overflow-hidden flex flex-col">
        <div className="overflow-x-auto">
          <table className="table-strict w-full text-left">
            <thead className="bg-gray-100 border-b border-gray-200 text-gray-700 text-sm">
              <tr>
                <th className="w-8"></th>
                <th>Asset</th>
                <th>Exchanges</th>
                <th>Status</th>
                <th>Opened</th>
                <th>Spread</th>
                <th>Fees</th>
                <th>Funding</th>
                <th>PnL</th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-gray-500">
                    No orders found matching the filter.
                  </td>
                </tr>
              ) : (
                filteredOrders.map((group) => (
                  <OrderGroupRow key={group.id} group={group} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
