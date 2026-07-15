import { useState } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { DataTable, type ColumnDef } from "../components/ui/DataTable";
import { Badge } from "../components/ui/Badge";
import { Card, CardContent } from "../components/ui/Card";

interface OrderLeg {
  exchange_id: string;
  side: string;
  leverage: number;
  volume: number;
  entry_price: number | null;
  exit_price: number | null;
  fees_usdt: number;
  funding_usdt: number;
  pnl_usdt: number;
}

interface OrderGroup {
  id: string;
  asset: string;
  symbol: string;
  short_exchange_id: string;
  long_exchange_id: string;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
  entry_spread_pct: number;
  exit_spread_pct: number | null;
  current_spread_pct: number | null;
  fees_usdt: number;
  funding_usdt: number;
  pnl_usdt: number;
  funding_countdown_sec?: number;
  legs: OrderLeg[];
}

interface OrdersSummary {
  open_count: number;
  closed_count: number;
  total_pnl_usdt: number;
  total_fees_usdt: number;
  total_funding_usdt: number;
}

interface OrdersSnapshot {
  summary: OrdersSummary;
  groups: OrderGroup[];
  filter: string;
}

export function PaperTradesPage() {
  const { data, status, sendMessage } =
    useWebSocket<OrdersSnapshot>("/ws/paper_trades");
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  if (status !== "open") {
    return (
      <div className="p-6">
        <p className="text-gray-500">Connecting to paper trades stream...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Loading paper trades...</p>
      </div>
    );
  }

  const {
    summary = {
      open_count: 0,
      closed_count: 0,
      total_pnl_usdt: 0,
      total_fees_usdt: 0,
      total_funding_usdt: 0,
    },
    groups = [],
    filter = "all",
  } = data;

  const toggleRow = (id: string) => {
    const newSet = new Set(expandedRows);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setExpandedRows(newSet);
  };

  const handleFilterChange = (newFilter: string) => {
    sendMessage("paper_trades.set_filter", { filter: newFilter });
  };

  const formatNumber = (num: number | null | undefined, decimals = 2) =>
    num !== null && num !== undefined ? num.toFixed(decimals) : "—";

  const formatPnl = (num: number) => {
    const colorClass =
      num >= 0
        ? "text-green-600 dark:text-green-400"
        : "text-red-600 dark:text-red-400";
    return (
      <span className={`font-medium ${colorClass}`}>
        {num > 0 ? "+" : ""}
        {formatNumber(num)}
      </span>
    );
  };

  const columns: ColumnDef<OrderGroup>[] = [
    {
      header: "",
      cell: (row) => (
        <button
          onClick={() => toggleRow(row.id)}
          className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
        >
          {expandedRows.has(row.id) ? "▼" : "▶"}
        </button>
      ),
      className: "w-10",
    },
    {
      header: "Asset",
      cell: (row) => (
        <span className="font-bold text-gray-900 dark:text-white">
          {row.asset || row.symbol}
        </span>
      ),
    },
    {
      header: "Exchanges",
      cell: (row) => (
        <div className="flex gap-2">
          <Badge variant="short">S: {row.short_exchange_id}</Badge>
          <Badge variant="long">L: {row.long_exchange_id}</Badge>
        </div>
      ),
    },
    {
      header: "Status",
      cell: (row) => (
        <Badge variant={row.status === "open" ? "neutral" : "default"}>
          {row.status}
        </Badge>
      ),
    },
    { header: "Opened", accessorKey: "opened_at" },
    {
      header: "Spread",
      cell: (row) => {
        const exit =
          row.status === "open" ? row.current_spread_pct : row.exit_spread_pct;
        return (
          <div className="flex flex-col">
            <span className="text-xs text-gray-500">
              In: {formatNumber(row.entry_spread_pct)}%
            </span>
            <span>Out: {formatPnl(exit || 0)}%</span>
          </div>
        );
      },
    },
    { header: "Fees", cell: (row) => formatNumber(row.fees_usdt) },
    { header: "Funding", cell: (row) => formatPnl(row.funding_usdt) },
    { header: "PnL", cell: (row) => formatPnl(row.pnl_usdt) },
  ];

  return (
    <div className="w-full flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between p-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shrink-0">
        <div className="flex items-center space-x-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Paper Trades
          </h1>
          <Badge variant="warning">
            Live demo · real exchange prices · simulated orders
          </Badge>
        </div>
        <div className="flex items-center space-x-2 bg-gray-100 dark:bg-gray-800 p-1 rounded-md">
          {["all", "open", "closed"].map((f) => (
            <button
              key={f}
              onClick={() => handleFilterChange(f)}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                filter === f
                  ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                  : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <CardContent className="p-4 flex items-center justify-between text-sm">
          <div className="flex space-x-6">
            <div>
              <span className="text-gray-500 dark:text-gray-400">
                Total PnL:{" "}
              </span>
              <span className="text-lg font-bold">
                {formatPnl(summary.total_pnl_usdt)} USDT
              </span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">Fees: </span>
              <span className="font-semibold text-gray-900 dark:text-white">
                {formatNumber(summary.total_fees_usdt)}
              </span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">
                Funding:{" "}
              </span>
              <span className="font-semibold">
                {formatPnl(summary.total_funding_usdt)}
              </span>
            </div>
          </div>
          <div className="text-gray-500 dark:text-gray-400">
            {summary.open_count} open · {summary.closed_count} closed
          </div>
        </CardContent>
      </Card>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm overflow-hidden border border-gray-200 dark:border-gray-700">
        <DataTable
          data={groups}
          columns={columns}
          keyExtractor={(row) =>
            row.id ||
            `${row.asset}-${row.short_exchange_id}-${row.long_exchange_id}`
          }
          emptyMessage="No paper trades match the current filter."
          rowClassName={(row) =>
            expandedRows.has(row.id) ? "bg-gray-50 dark:bg-gray-800/50" : ""
          }
        />

        {/* Render expanded legs */}
        {groups.map((group) => {
          if (
            !expandedRows.has(group.id) ||
            !group.legs ||
            group.legs.length === 0
          )
            return null;

          return (
            <div
              key={`${group.id}-legs`}
              className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4"
            >
              <table className="min-w-full text-sm divide-y divide-gray-200 dark:divide-gray-800">
                <thead>
                  <tr className="text-gray-500 dark:text-gray-400 text-left">
                    <th className="font-medium pb-2">Leg</th>
                    <th className="font-medium pb-2">Volume</th>
                    <th className="font-medium pb-2">Entry</th>
                    <th className="font-medium pb-2">Exit</th>
                    <th className="font-medium pb-2">Fees</th>
                    <th className="font-medium pb-2">Funding</th>
                    <th className="font-medium pb-2">PnL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {group.legs.map((leg, i) => (
                    <tr key={i} className="text-gray-900 dark:text-gray-300">
                      <td className="py-2 flex items-center gap-2">
                        <Badge variant={leg.side === "sell" ? "short" : "long"}>
                          {leg.side.toUpperCase()}
                        </Badge>
                        <span>{leg.exchange_id}</span>
                        <span className="text-xs text-gray-500">
                          {leg.leverage}x
                        </span>
                      </td>
                      <td className="py-2">{leg.volume}</td>
                      <td className="py-2">
                        {formatNumber(leg.entry_price, 4)}
                      </td>
                      <td className="py-2">
                        {formatNumber(leg.exit_price, 4)}
                      </td>
                      <td className="py-2">{formatNumber(leg.fees_usdt)}</td>
                      <td className="py-2">{formatPnl(leg.funding_usdt)}</td>
                      <td className="py-2">{formatPnl(leg.pnl_usdt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
    </div>
  );
}
