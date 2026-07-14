import React, { useMemo } from "react";
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  Area,
} from "recharts";

interface ChartDataPoint {
  time: string;
  spread: number;
  shortPrice?: number;
  longPrice?: number;
}

interface Props {
  data: ChartDataPoint[];
  shortEx: string;
  longEx: string;
}

export const OpportunityChart: React.FC<Props> = ({
  data,
  shortEx,
  longEx,
}) => {
  // Format data for recharts if needed (e.g., converting dates)
  const formattedData = useMemo(() => {
    return data.map((d) => ({
      ...d,
      // Ensure spread is a number for smooth area charting
      spread: Number(d.spread.toFixed(2)),
    }));
  }, [data]);

  if (!data || data.length === 0) {
    return (
      <div className="w-full h-64 flex items-center justify-center bg-gray-50 border rounded text-gray-400">
        Waiting for chart data...
      </div>
    );
  }

  return (
    <div className="w-full h-96 bg-white p-4 rounded shadow">
      <h3 className="text-md font-semibold mb-4">Opportunity Chart</h3>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={formattedData}
          margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} />

          {/* Left Y-Axis for Prices */}
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 12 }}
            domain={["auto", "auto"]}
          />

          {/* Right Y-Axis for Spread */}
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fontSize: 12 }}
            domain={["auto", "auto"]}
            tickFormatter={(v) => `${v}%`}
          />

          <Tooltip />
          <Legend />

          {/* Prices on Left Axis */}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="shortPrice"
            name={`${shortEx.toUpperCase()} Price`}
            stroke="#ef4444" // red for short
            dot={false}
            strokeWidth={2}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="longPrice"
            name={`${longEx.toUpperCase()} Price`}
            stroke="#22c55e" // green for long
            dot={false}
            strokeWidth={2}
          />

          {/* Spread on Right Axis as an Area */}
          <Area
            yAxisId="right"
            type="monotone"
            dataKey="spread"
            name="Spread %"
            fill="#3b82f6"
            stroke="#2563eb"
            fillOpacity={0.2}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
