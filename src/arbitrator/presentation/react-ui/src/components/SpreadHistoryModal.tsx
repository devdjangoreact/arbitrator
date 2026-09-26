import React, { useRef, useEffect, useCallback, useState } from "react";
import { createChart, LineSeries, ColorType } from "lightweight-charts";
import type { IChartApi, ISeriesApi, LineSeriesOptions, UTCTimestamp } from "lightweight-charts";
import { useMonitorWs } from "../hooks/useMonitorWs";
import type { MonitorConfig } from "../types";

interface Props {
  config: MonitorConfig;
  activeShort?: string;
  activeLong?: string;
  onClose: () => void;
}

interface CandlesResponse {
  short_exchange: string;
  long_exchange: string;
  symbol: string;
  timeframe: string;
  short_candles: [number, number, number, number, number, number][];
  long_candles: [number, number, number, number, number, number][];
}

const CHART_BG = "#060d1a";
const GRID_COLOR = "#0f2233";
const TEXT_COLOR = "#ffffff";
const BORDER_COLOR = "#1e3a5f";

const SHORT_COLOR = "#f87171";
const LONG_COLOR  = "#4ade80";
const SPREAD_COLOR = "#22d3ee";

/**
 * Detect how many decimal places are needed to represent a price without
 * losing significant digits. E.g. 0.02738 → 5, 45000.12 → 2, 0.000012 → 6.
 */
function detectPrecision(values: number[]): number {
  let maxPrec = 2;
  for (const v of values) {
    if (!v || !isFinite(v)) continue;
    // Convert to string without scientific notation
    const s = v.toFixed(10).replace(/0+$/, "");
    const dot = s.indexOf(".");
    if (dot === -1) continue;
    const prec = s.length - dot - 1;
    if (prec > maxPrec) maxPrec = prec;
  }
  // Cap at 8 significant decimals
  return Math.min(maxPrec, 8);
}

function makeChartOptions(height: number) {
  return {
    layout: {
      background: { type: ColorType.Solid, color: CHART_BG },
      textColor: TEXT_COLOR,
      fontSize: 10,
      fontFamily: "monospace",
    },
    grid: {
      vertLines: { color: GRID_COLOR },
      horzLines: { color: GRID_COLOR },
    },
    crosshair: { mode: 1 },
    rightPriceScale: {
      borderColor: BORDER_COLOR,
      // width is auto — lightweight-charts expands as needed for label length
    },
    timeScale: {
      borderColor: BORDER_COLOR,
      timeVisible: true,
      secondsVisible: false,
    },
    height,
  };
}

export const SpreadHistoryModal: React.FC<Props> = ({ config, activeShort: propShort, activeLong: propLong, onClose }) => {
  const { state: ls } = useMonitorWs(config.id);
  const shortLabel = ls?.active_short ?? propShort ?? config.short_exchange;
  const longLabel = ls?.active_long ?? propLong ?? config.long_exchange;

  const [spreadInverted, setSpreadInverted] = useState(false);

  const priceContainerRef = useRef<HTMLDivElement>(null);
  const spreadContainerRef = useRef<HTMLDivElement>(null);

  const priceChartRef = useRef<IChartApi | null>(null);
  const spreadChartRef = useRef<IChartApi | null>(null);
  const shortSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const longSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const spreadSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  // Current precision state — updated once real data arrives
  const pricePrecRef = useRef(8);

  const loadingRef = useRef(false);
  const shortCandlesRef = useRef<[number, number, number, number, number, number][]>([]);
  const longCandlesRef = useRef<[number, number, number, number, number, number][]>([]);

  const buildSpreadPoints = useCallback(
    (
      shortCandles: [number, number, number, number, number, number][],
      longCandles: [number, number, number, number, number, number][],
      inverted: boolean,
    ) => {
      const shortMap = new Map<number, number>();
      const longMap = new Map<number, number>();
      for (const c of shortCandles) shortMap.set(Math.floor(c[0] / 1000), c[4]);
      for (const c of longCandles) longMap.set(Math.floor(c[0] / 1000), c[4]);
      const times = [...new Set([...shortMap.keys(), ...longMap.keys()])].sort((a, b) => a - b);
      const out: { time: UTCTimestamp; value: number }[] = [];
      for (const t of times) {
        const sp = shortMap.get(t);
        const lp = longMap.get(t);
        if (sp == null || lp == null) continue;
        const base = inverted ? sp : lp;
        const quote = inverted ? lp : sp;
        if (base > 0) out.push({ time: t as UTCTimestamp, value: ((quote - base) / base) * 100 });
      }
      return out;
    },
    [],
  );

  // Init charts once on mount
  useEffect(() => {
    if (!priceContainerRef.current || !spreadContainerRef.current) return;

    const priceChart = createChart(priceContainerRef.current, makeChartOptions(280));
    const spreadChart = createChart(spreadContainerRef.current, makeChartOptions(180));

    const shortOpts: Partial<LineSeriesOptions> = {
      color: SHORT_COLOR,
      lineWidth: 1,
      title: `↓${shortLabel}`,
      // lastValueVisible shows the current price label at the end of the line on the Y axis
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: { type: "price", precision: 8, minMove: 0.00000001 },
    };
    const longOpts: Partial<LineSeriesOptions> = {
      color: LONG_COLOR,
      lineWidth: 1,
      title: `↑${longLabel}`,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: { type: "price", precision: 8, minMove: 0.00000001 },
    };
    const spreadOpts: Partial<LineSeriesOptions> = {
      color: SPREAD_COLOR,
      lineWidth: 1,
      title: "spread %",
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
    };

    shortSeriesRef.current = priceChart.addSeries(LineSeries, shortOpts);
    longSeriesRef.current = priceChart.addSeries(LineSeries, longOpts);
    spreadSeriesRef.current = spreadChart.addSeries(LineSeries, spreadOpts);

    priceChartRef.current = priceChart;
    spreadChartRef.current = spreadChart;

    const handleResize = () => {
      if (priceContainerRef.current)
        priceChart.applyOptions({ width: priceContainerRef.current.clientWidth });
      if (spreadContainerRef.current)
        spreadChart.applyOptions({ width: spreadContainerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      priceChart.remove();
      spreadChart.remove();
      priceChartRef.current = null;
      spreadChartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch 24h OHLCV history on mount
  useEffect(() => {
    if (loadingRef.current) return;
    loadingRef.current = true;

    fetch(`/api/candles/${encodeURIComponent(config.id)}?timeframe=1m&limit=1440`)
      .then((r) => r.json() as Promise<CandlesResponse>)
      .then((data) => {
        shortCandlesRef.current = data.short_candles;
        longCandlesRef.current = data.long_candles;

        const shortPoints: { time: UTCTimestamp; value: number }[] = [];
        const longPoints: { time: UTCTimestamp; value: number }[] = [];

        for (const c of data.short_candles) {
          shortPoints.push({ time: Math.floor(c[0] / 1000) as UTCTimestamp, value: c[4] });
        }
        for (const c of data.long_candles) {
          longPoints.push({ time: Math.floor(c[0] / 1000) as UTCTimestamp, value: c[4] });
        }

        // Auto-detect precision from actual price values
        const samplePrices = [
          ...shortPoints.slice(0, 50).map((p) => p.value),
          ...longPoints.slice(0, 50).map((p) => p.value),
        ];
        const prec = detectPrecision(samplePrices);
        pricePrecRef.current = prec;
        const minMove = Math.pow(10, -prec);

        shortSeriesRef.current?.applyOptions({
          priceFormat: { type: "price", precision: prec, minMove },
        });
        longSeriesRef.current?.applyOptions({
          priceFormat: { type: "price", precision: prec, minMove },
        });

        shortSeriesRef.current?.setData(shortPoints);
        longSeriesRef.current?.setData(longPoints);
        spreadSeriesRef.current?.setData(buildSpreadPoints(data.short_candles, data.long_candles, false));

        priceChartRef.current?.timeScale().fitContent();
        spreadChartRef.current?.timeScale().fitContent();
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recompute spread when inversion changes
  useEffect(() => {
    if (!spreadSeriesRef.current) return;
    const pts = buildSpreadPoints(shortCandlesRef.current, longCandlesRef.current, spreadInverted);
    if (pts.length > 0) spreadSeriesRef.current.setData(pts);
  }, [spreadInverted, buildSpreadPoints]);

  // Push live data point on each WS tick
  const pushData = useCallback(() => {
    if (!ls) return;
    const t = Math.floor(Date.now() / 1000) as UTCTimestamp;

    const sp = ls.short_price;
    const lp = ls.long_price;

    if (sp != null && shortSeriesRef.current) {
      // Update precision if live price has more decimals than historical
      const prec = detectPrecision([sp]);
      if (prec > pricePrecRef.current) {
        pricePrecRef.current = prec;
        const minMove = Math.pow(10, -prec);
        shortSeriesRef.current.applyOptions({ priceFormat: { type: "price", precision: prec, minMove } });
        longSeriesRef.current?.applyOptions({ priceFormat: { type: "price", precision: prec, minMove } });
      }
      shortSeriesRef.current.update({ time: t, value: sp });
    }
    if (lp != null && longSeriesRef.current) longSeriesRef.current.update({ time: t, value: lp });

    if (sp != null && lp != null && spreadSeriesRef.current) {
      const base = spreadInverted ? sp : lp;
      const quote = spreadInverted ? lp : sp;
      if (base > 0) {
        spreadSeriesRef.current.update({ time: t, value: ((quote - base) / base) * 100 });
      }
    }
  }, [ls, spreadInverted]);

  useEffect(() => { pushData(); }, [pushData]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75"
      onClick={onClose}
    >
      <div
        className="bg-[#060d1a] text-[#cbd5e1] rounded border border-gray-700 shadow-2xl font-mono flex flex-col"
        style={{ width: "min(1100px, 96vw)", maxHeight: "92vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex justify-between items-center px-3 py-2 border-b border-gray-700 bg-[#0d1f33] shrink-0">
          <div className="flex items-center gap-3 text-xs">
            <span className="text-white font-bold text-sm">{config.symbol}</span>
            <span style={{ color: SHORT_COLOR }} className="uppercase font-bold">{shortLabel} ↓</span>
            <span className="text-gray-600">–</span>
            <span style={{ color: LONG_COLOR }} className="uppercase font-bold">{longLabel} ↑</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span style={{ color: SHORT_COLOR }}>━ {shortLabel}</span>
            <span style={{ color: LONG_COLOR }}>━ {longLabel}</span>
            <span style={{ color: SPREAD_COLOR }}>━ spread %</span>
            <button
              className="px-2 py-0.5 rounded border border-gray-600 hover:bg-gray-800 text-gray-400 hover:text-white text-[10px]"
              title="Swap spread direction"
              onClick={() => setSpreadInverted((v) => !v)}
            >
              {spreadInverted ? `${longLabel}−${shortLabel}` : `${shortLabel}−${longLabel}`} ⇄
            </button>
            <button
              className="text-gray-500 hover:text-white text-base font-bold leading-none px-1 ml-1"
              onClick={onClose}
            >×</button>
          </div>
        </div>

        {/* Charts */}
        <div className="p-3 flex flex-col gap-2 overflow-auto">
          <div className="text-[10px] uppercase tracking-wide">
            <span className="text-gray-500">Price · </span>
            <span style={{ color: SHORT_COLOR }}>{shortLabel}</span>
            <span className="text-gray-500"> vs </span>
            <span style={{ color: LONG_COLOR }}>{longLabel}</span>
          </div>
          <div ref={priceContainerRef} className="w-full rounded" style={{ height: 280 }} />

          <div className="text-[10px] text-gray-500 uppercase tracking-wide mt-1">
            Spread % · <span style={{ color: SPREAD_COLOR }}>{spreadInverted ? `(${longLabel}−${shortLabel})/${shortLabel}` : `(${shortLabel}−${longLabel})/${longLabel}`}</span>
          </div>
          <div ref={spreadContainerRef} className="w-full rounded" style={{ height: 180 }} />
        </div>

        <div className="px-3 pb-2 text-gray-700 text-[10px] shrink-0">
          24h history (1m candles) + live ticks
        </div>
      </div>
    </div>
  );
};
