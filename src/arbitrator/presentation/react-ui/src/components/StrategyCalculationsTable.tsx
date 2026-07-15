import React from "react";
import type { StrategyCalculation } from "../types";
import { fmtNum, pnlClass } from "../utils/format";

interface Props {
  calculations: StrategyCalculation[];
  onExecute: (strategyName: string) => void;
}

export const StrategyCalculationsTable: React.FC<Props> = ({
  calculations,
  onExecute,
}) => {
  return (
    <div className="overflow-x-auto bg-white rounded shadow">
      <h3 className="text-md font-semibold p-4 border-b">
        Strategy Calculations
      </h3>
      <table className="table-strict text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th>Strategy</th>
            <th>Spread (%)</th>
            <th>Delta</th>
            <th>Fee %</th>
            <th>Max Vol</th>
            <th>Details</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {calculations.length === 0 ? (
            <tr>
              <td colSpan={7} className="text-center py-4 text-gray-500">
                No calculations available
              </td>
            </tr>
          ) : (
            calculations.map((calc, i) => (
              <tr key={`${calc.strategy_name}-${i}`}>
                <td className="font-medium">{calc.strategy_name}</td>
                <td className={`font-bold ${pnlClass(calc.spread_pct)}`}>
                  {calc.spread_pct > 0 ? "+" : ""}
                  {fmtNum(calc.spread_pct, 2)}%
                </td>
                <td className={pnlClass(calc.delta)}>
                  {calc.delta > 0 ? "+" : ""}
                  {fmtNum(calc.delta, 2)}%
                </td>
                <td>{fmtNum(calc.fee_pct, 4)}%</td>
                <td>{fmtNum(calc.max_vol, 2)}</td>
                <td>
                  <span
                    className={
                      calc.details === "OK"
                        ? "text-green-600 font-bold"
                        : "text-red-500"
                    }
                  >
                    {calc.details}
                  </span>
                </td>
                <td>
                  {calc.details === "OK" && (
                    <button
                      className="bg-green-500 hover:bg-green-600 text-white text-xs font-bold py-1 px-3 rounded"
                      onClick={() => onExecute(calc.strategy_name)}
                    >
                      Execute
                    </button>
                  )}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};
