import React from "react";
import { fmtPnl, pnlClass, fmtNum } from "../utils/format";

interface Props {
  totalPnl: number;
  totalFees: number;
  totalFunding: number;
  openCount: number;
  closedCount: number;
  activeFilter: "all" | "open" | "closed";
  onFilterChange: (filter: "all" | "open" | "closed") => void;
}

export const OrdersSummaryPanel: React.FC<Props> = ({
  totalPnl,
  totalFees,
  totalFunding,
  openCount,
  closedCount,
  activeFilter,
  onFilterChange,
}) => {
  return (
    <div className="bg-white p-4 rounded shadow flex flex-wrap items-center justify-between gap-4">
      <div className="flex gap-6">
        <div>
          <div className="text-xs text-gray-500 uppercase font-bold">
            Total PnL
          </div>
          <div className={`text-xl font-bold ${pnlClass(totalPnl)}`}>
            {fmtPnl(totalPnl)}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 uppercase font-bold">Fees</div>
          <div className="text-xl font-medium text-gray-800">
            {fmtNum(totalFees, 2)}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 uppercase font-bold">
            Funding
          </div>
          <div className={`text-xl font-medium ${pnlClass(totalFunding)}`}>
            {fmtPnl(totalFunding)}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 uppercase font-bold">
            Orders
          </div>
          <div className="text-xl font-medium text-gray-800">
            <span className="text-blue-600">{openCount} Open</span> /{" "}
            <span className="text-gray-500">{closedCount} Closed</span>
          </div>
        </div>
      </div>

      <div className="flex gap-2 bg-gray-100 p-1 rounded">
        {(["all", "open", "closed"] as const).map((filter) => (
          <button
            key={filter}
            className={`px-4 py-1 text-sm font-medium rounded capitalize ${
              activeFilter === filter
                ? "bg-white shadow text-indigo-600"
                : "text-gray-600 hover:text-gray-900"
            }`}
            onClick={() => onFilterChange(filter)}
          >
            {filter}
          </button>
        ))}
      </div>
    </div>
  );
};
