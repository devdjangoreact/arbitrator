import React, { useState, useEffect, useRef } from "react";
import type { MonitorConfig, UpdateConfigPayload } from "../types";
import { fmtNum, fmtPnl, pnlClass } from "../utils/format";
import { SpreadChart } from "./SpreadChart";
import { useMonitorWs } from "../hooks/useMonitorWs";

interface Props {
  config: MonitorConfig;
  pinned?: boolean;
  onPin?: (id: string) => void;
  onUpdate: (payload: UpdateConfigPayload) => void;
  onClose: (id: string) => void;
  onRestart: (id: string) => void;
  onSpreadHistory?: (id: string) => void;
}

const MAX_CHART_POINTS = 120;

function exchangeUrl(exchange: string, symbol: string): string {
  const base = symbol.split("/")[0];
  const ex = exchange.toLowerCase();
  if (ex === "mexc") return `https://futures.mexc.com/exchange/${base}_USDT`;
  if (ex === "gate" || ex === "gateio") return `https://www.gate.io/futures/usdt/${base}_USDT`;
  if (ex === "binance") return `https://www.binance.com/en/futures/${base}USDT`;
  if (ex === "bybit") return `https://www.bybit.com/trade/usdt/${base}USDT`;
  if (ex === "bitget") return `https://www.bitget.com/futures/usdt/${base}USDT`;
  if (ex === "okx") return `https://www.okx.com/trade-futures/${base}-USDT`;
  if (ex === "huobi" || ex === "htx") return `https://www.htx.com/en-us/futures/linear_swap/exchange/#symbol=${base}-USDT`;
  if (ex === "bingx") return `https://bingx.com/en/perpetual/${base}-USDT`;
  return `https://www.google.com/search?q=${exchange}+${base}+USDT+futures`;
}

export const LiveMonitorCard: React.FC<Props> = ({
  config,
  pinned = false,
  onPin,
  onUpdate,
  onClose,
  onRestart,
  onSpreadHistory,
}) => {
  // dirtyRef tracks which fields have uncommitted local edits (not in React state to avoid loops)
  const dirtyRef = useRef<Set<keyof MonitorConfig>>(new Set());
  const [localConfig, setLocalConfig] = useState<MonitorConfig>(config);
  const [collapsed, setCollapsed] = useState(false);
  // trigger re-render when dirty set changes (for indicator colors)
  const [, setDirtyVersion] = useState(0);

  const { state: ls, reconnect } = useMonitorWs(config.id);

  const openSpreadHistory = useRef<number[]>([]);
  const closeSpreadHistory = useRef<number[]>([]);
  const [chartTick, setChartTick] = useState(0);
  const prevActiveShortRef = useRef<string>("");

  // Sync config → localConfig for clean (non-dirty) fields only
  useEffect(() => {
    setLocalConfig((prev) => {
      const dirty = dirtyRef.current;
      const next = { ...prev };
      (Object.keys(config) as (keyof MonitorConfig)[]).forEach((k) => {
        if (!dirty.has(k)) {
          (next as Record<string, unknown>)[k] = config[k];
        }
      });
      return next;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  useEffect(() => {
    if (!ls) return;
    // Use same activeShort logic as UI so swap detection is in sync
    const curShort =
      localConfig.side === "auto"
        ? (ls.active_short ?? config.short_exchange)
        : localConfig.side === "long"
          ? config.long_exchange
          : config.short_exchange;
    if (prevActiveShortRef.current && prevActiveShortRef.current !== curShort) {
      const tmp = openSpreadHistory.current;
      openSpreadHistory.current = closeSpreadHistory.current;
      closeSpreadHistory.current = tmp;
    }
    prevActiveShortRef.current = curShort;
    if (ls.open_spread_current != null)
      openSpreadHistory.current = [...openSpreadHistory.current, ls.open_spread_current].slice(-MAX_CHART_POINTS);
    if (ls.close_spread_current != null)
      closeSpreadHistory.current = [...closeSpreadHistory.current, ls.close_spread_current].slice(-MAX_CHART_POINTS);
    setChartTick((t) => t + 1);
  }, [ls, localConfig.side, config.short_exchange, config.long_exchange]);

  const markDirty = (key: keyof MonitorConfig) => {
    dirtyRef.current.add(key);
    setDirtyVersion((v) => v + 1);
  };

  const markClean = (key: keyof MonitorConfig) => {
    dirtyRef.current.delete(key);
    setDirtyVersion((v) => v + 1);
  };

  const set = (key: keyof MonitorConfig, value: unknown) => {
    setLocalConfig((p) => ({ ...p, [key]: value }));
    markDirty(key);
  };

  const save = (key: keyof MonitorConfig) => {
    onUpdate({ cmd: "update_config", monitor_id: config.id, config: { [key]: localConfig[key] } });
    markClean(key);
  };

  const revert = (key: keyof MonitorConfig) => {
    setLocalConfig((p) => ({ ...p, [key]: config[key] }));
    markClean(key);
  };

  const send = (patch: Partial<MonitorConfig>) =>
    onUpdate({ cmd: "update_config", monitor_id: config.id, config: patch });

  // ✓ green = synced, grey = unsaved-but-clean; × red = dirty (local edit pending)
  const FieldControls = ({ field, noX = false }: { field: keyof MonitorConfig; noX?: boolean }) => {
    const dirty = dirtyRef.current.has(field);
    const synced = !dirty && localConfig[field] === config[field];
    return (
      <span className="flex items-center gap-0.5">
        <span
          className={`text-xs cursor-pointer leading-none select-none ${synced ? "text-green-500" : "text-gray-600"}`}
          title={synced ? "Synced with server" : "Click to save"}
          onClick={() => { if (!synced) save(field); }}
        >✓</span>
        {!noX && dirty && (
          <span
            className="text-xs cursor-pointer leading-none select-none text-red-500 hover:text-red-400"
            title="Discard change"
            onClick={() => revert(field)}
          >×</span>
        )}
      </span>
    );
  };

  // Determine display names for short/long based on current side selection
  // For auto: use WS active_short/active_long (backend picks by price)
  // For short/long: compute immediately from localConfig.side without waiting for WS tick
  const activeShort =
    localConfig.side === "auto"
      ? (ls?.active_short ?? config.short_exchange)
      : localConfig.side === "long"
        ? config.long_exchange
        : config.short_exchange;
  const activeLong =
    localConfig.side === "auto"
      ? (ls?.active_long ?? config.long_exchange)
      : localConfig.side === "long"
        ? config.short_exchange
        : config.long_exchange;
  const isSwapped = activeShort !== config.short_exchange;

  return (
    <div
      className="rounded border border-gray-700 flex flex-col text-xs font-mono"
      style={{ backgroundColor: "#1e293b", color: "#cbd5e1", width: "100%" }}
    >
      {/* ── Header ── */}
      <div className="flex justify-between items-center px-2 py-1 border-b border-gray-700 bg-[#162032]">
        <div className="flex items-center gap-1.5 font-bold text-white text-xs">
          <button onClick={() => onPin?.(config.id)}
            className={`leading-none ${pinned ? "text-yellow-400" : "text-gray-600 hover:text-yellow-300"}`}>★</button>
          <button onClick={() => setCollapsed((c) => !c)}
            className="text-gray-500 hover:text-gray-300 leading-none">{collapsed ? "▶" : "▼"}</button>
          <span
            className={`w-2 h-2 rounded-full ${localConfig.is_active ? "bg-green-500 animate-pulse" : "bg-gray-600"}`}
            title={localConfig.is_active ? "Active" : "Stopped"}
          />
          <span>{config.symbol}</span>
          {isSwapped && (
            <span className="text-yellow-500 text-[9px] font-normal" title="Auto mode swapped exchanges">⇄</span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold uppercase">
          <a href={exchangeUrl(activeShort, config.symbol)} target="_blank" rel="noopener noreferrer"
            className="text-red-400 hover:text-red-300 hover:underline">{activeShort} ↓</a>
          <span className="text-gray-600">–</span>
          <a href={exchangeUrl(activeLong, config.symbol)} target="_blank" rel="noopener noreferrer"
            className="text-green-400 hover:text-green-300 hover:underline">{activeLong} ↑</a>
          <button onClick={() => onClose(config.id)}
            className="ml-1 text-gray-500 hover:text-red-400 text-xs font-bold leading-none">×</button>
        </div>
      </div>

      {!collapsed && (
        <div className="flex flex-col">

          {/* ── Strategy Params ── */}
          <div className="px-2 py-1.5 flex flex-col gap-1 border-b border-gray-700/50">

            {/* Side */}
            {(() => {
              const hasOrders = (ls?.short_orders ?? 0) > 0 || (ls?.long_orders ?? 0) > 0;
              return (
                <div className="flex items-center gap-1">
                  <label className="w-24 text-gray-400 shrink-0">Side:</label>
                  <div className={`flex rounded border overflow-hidden ${hasOrders ? "border-gray-700 opacity-50 cursor-not-allowed" : "border-gray-600"}`}>
                    {(["auto", "long", "short"] as const).map((s) => (
                      <button key={s}
                        disabled={hasOrders}
                        className={`px-2 py-0.5 uppercase text-xs border-l border-gray-600 first:border-l-0 transition-colors
                          ${hasOrders ? "cursor-not-allowed" : ""}
                          ${localConfig.side === s ? "bg-teal-600 text-white" : "text-gray-400 hover:bg-gray-700"}`}
                        onClick={() => { if (!hasOrders) { set("side", s); send({ side: s }); } }}>
                        {s}
                      </button>
                    ))}
                  </div>
                  {hasOrders && <span className="text-yellow-600 text-xs ml-1">🔒</span>}
                  <FieldControls field="side" />
                </div>
              );
            })()}

            {/* Open Spread + Ticks */}
            <div className="flex items-center gap-1">
              <label className="w-24 text-gray-400 shrink-0">Open Spread:</label>
              <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 px-1 py-0.5 min-w-0">
                <input type="number" step="0.1" value={localConfig.open_spread_pct}
                  onChange={(e) => set("open_spread_pct", Number(e.target.value))}
                  onBlur={() => save("open_spread_pct")}
                  className="bg-transparent w-full text-white outline-none min-w-0" />
                <FieldControls field="open_spread_pct" />
              </div>
              <span className="text-gray-500 shrink-0">T:</span>
              <div className="flex items-center bg-gray-800 rounded border border-gray-700 px-1 py-0.5 w-14 shrink-0">
                <input type="number" min="1" value={localConfig.open_ticks}
                  onChange={(e) => set("open_ticks", Number(e.target.value))}
                  onBlur={() => save("open_ticks")}
                  className="bg-transparent w-full text-white outline-none" />
              </div>
              <FieldControls field="open_ticks" />
            </div>

            {/* Close Spread + Ticks */}
            <div className="flex items-center gap-1">
              <label className="w-24 text-gray-400 shrink-0">Close Spread:</label>
              <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 px-1 py-0.5 min-w-0">
                <input type="number" step="0.1" value={localConfig.close_spread_pct}
                  onChange={(e) => set("close_spread_pct", Number(e.target.value))}
                  onBlur={() => save("close_spread_pct")}
                  className="bg-transparent w-full text-white outline-none min-w-0" />
                <FieldControls field="close_spread_pct" />
              </div>
              <span className="text-gray-500 shrink-0">T:</span>
              <div className="flex items-center bg-gray-800 rounded border border-gray-700 px-1 py-0.5 w-14 shrink-0">
                <input type="number" min="1" value={localConfig.close_ticks}
                  onChange={(e) => set("close_ticks", Number(e.target.value))}
                  onBlur={() => save("close_ticks")}
                  className="bg-transparent w-full text-white outline-none" />
              </div>
              <FieldControls field="close_ticks" />
            </div>

            {/* Order Size */}
            <div className="flex items-center gap-1">
              <label className="w-24 text-gray-400 shrink-0">Order Size:</label>
              <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 px-1 py-0.5">
                <input type="number" value={localConfig.order_size_usdt}
                  onChange={(e) => set("order_size_usdt", Number(e.target.value))}
                  onBlur={() => save("order_size_usdt")}
                  className="bg-transparent w-full text-white outline-none" />
                <FieldControls field="order_size_usdt" />
              </div>
            </div>

            {/* Max orders */}
            <div className="flex items-center gap-1">
              <label className="w-24 text-gray-400 shrink-0">Max orders:</label>
              <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 px-1 py-0.5">
                <input type="number" value={localConfig.max_orders}
                  onChange={(e) => set("max_orders", Number(e.target.value))}
                  onBlur={() => save("max_orders")}
                  className="bg-transparent w-full text-white outline-none" />
                <FieldControls field="max_orders" />
              </div>
            </div>

            {/* Allowed size */}
            <div className="flex items-center gap-1">
              <label className="w-24 text-gray-400 shrink-0">Allowed size:</label>
              <div className="flex flex-col text-[10px]">
                <span>
                  <span className="text-red-400 font-bold">S({activeShort}):</span>{" "}
                  <span className="text-teal-400">{fmtNum(config.allowed_size_current_usdt, 0)}</span>
                  {" / Max:"}
                  {ls?.allowed_short != null
                    ? <span className="text-green-400">{fmtNum(ls.allowed_short, 0)}</span>
                    : <span className="text-gray-500">{fmtNum(config.allowed_size_usdt, 0)}</span>
                  }
                </span>
                <span>
                  <span className="text-green-400 font-bold">L({activeLong}):</span>{" "}
                  <span className="text-teal-400">{fmtNum(config.allowed_size_current_usdt, 0)}</span>
                  {" / Max:"}
                  {ls?.allowed_long != null
                    ? <span className="text-green-400">{fmtNum(ls.allowed_long, 0)}</span>
                    : <span className="text-gray-500">{fmtNum(config.allowed_size_usdt, 0)}</span>
                  }
                </span>
              </div>
            </div>

            {/* Flags */}
            <div className="flex gap-4">
              <label className="flex items-center gap-1 text-gray-400 cursor-pointer">
                Force Stop:
                <input type="checkbox" checked={localConfig.force_stop}
                  onChange={(e) => { set("force_stop", e.target.checked); send({ force_stop: e.target.checked }); }}
                  className="w-3 h-3 accent-gray-500" />
                <FieldControls field="force_stop" />
              </label>
              <label className="flex items-center gap-1 text-gray-400 cursor-pointer">
                Total Stop:
                <input type="checkbox" checked={localConfig.total_stop}
                  onChange={(e) => { set("total_stop", e.target.checked); send({ total_stop: e.target.checked }); }}
                  className="w-3 h-3 accent-gray-500" />
                <FieldControls field="total_stop" />
              </label>
            </div>

            {/* Is Active */}
            <div className="flex items-center gap-1">
              <label className="w-24 text-gray-400 shrink-0">Is Active?:</label>
              <div className="flex gap-1 flex-1">
                <button onClick={() => { set("is_active", true); send({ is_active: true }); }}
                  className={`flex-1 py-0.5 px-2 rounded border flex items-center justify-center gap-1 text-xs transition-colors ${
                    localConfig.is_active
                      ? "bg-green-700 text-white border-green-600"
                      : "text-gray-400 border-gray-700 hover:bg-gray-800"
                  }`}>
                  ▶ Start
                </button>
                <button onClick={() => { set("is_active", false); send({ is_active: false }); }}
                  className={`flex-1 py-0.5 px-2 rounded border flex items-center justify-center gap-1 text-xs transition-colors ${
                    !localConfig.is_active
                      ? "bg-red-900/60 text-red-400 border-red-900"
                      : "text-gray-400 border-gray-700 hover:bg-gray-800"
                  }`}>
                  ■ Stop
                </button>
                <button onClick={() => { onRestart(config.id); reconnect(); }}
                  className="flex-1 py-0.5 px-2 rounded border text-blue-400 border-gray-700 hover:bg-gray-800 flex items-center justify-center gap-1 text-xs">
                  ⟳ Restart
                </button>
              </div>
            </div>
          </div>

          {/* ── Exchange Data Grid ── */}
          {(() => {
            const V = "text-xs";
            const fmtSz = (v: number | null | undefined) => {
              if (v == null) return "null";
              if (v >= 100_000) return "∞";
              return v === 0 ? "0" : v.toFixed(2);
            };
            const sOf = ls?.short_open_fee;
            const sCf = ls?.short_close_fee_est;
            const lOf = ls?.long_open_fee;
            const lCf = ls?.long_close_fee_est;
            const hasFees = sOf != null || lOf != null;
            const feesShortTotal = (sOf ?? 0) + (sCf ?? 0);
            const feesLongTotal = (lOf ?? 0) + (lCf ?? 0);
            const feesTotal = feesShortTotal + feesLongTotal;
            const fmtFee = (open: number | null | undefined, close: number | null | undefined) =>
              open == null && close == null ? "null"
              : `${Math.abs(open ?? 0).toFixed(2)}/${Math.abs(close ?? 0).toFixed(2)}`;
            // Funding: accrued (already charged) / est.next (rate * size)
            const sAccrued = ls?.short_accrued_funding;
            const lAccrued = ls?.long_accrued_funding;
            // short: positive rate → short RECEIVES; long: positive rate → long PAYS (negative income)
            const sEstNext = ls?.short_funding_rate != null && ls?.short_size != null
              ? ls.short_funding_rate * ls.short_size : null;
            const lEstNext = ls?.long_funding_rate != null && ls?.long_size != null
              ? -(ls.long_funding_rate * ls.long_size) : null;
            const hasFunding = sAccrued != null || lAccrued != null;
            const fundingTotal = (sAccrued ?? 0) + (lAccrued ?? 0);
            const hasPos = ls != null && (ls.short_orders > 0 || ls.long_orders > 0);
            const gross = (ls?.short_pnl ?? 0) + (ls?.long_pnl ?? 0);
            const net = gross + feesTotal + fundingTotal;
            const fmtFundCell = (accrued: number | null | undefined, est: number | null | undefined) => {
              const a = accrued != null ? fmtPnl(accrued) : "null";
              const e = est != null ? fmtPnl(est) : "null";
              return `${a} / ${e}`;
            };
            return (
              <div className="px-2 py-1.5 grid grid-cols-[auto_1fr_1fr] gap-x-3 gap-y-1 items-center">
                {/* header */}
                <div />
                <div className="font-bold text-red-400 uppercase text-xs">{activeShort}</div>
                <div className="font-bold text-green-400 uppercase text-xs text-right">{activeLong}</div>

                {/* Funding rate / next */}
                <div className="text-gray-400 text-xs">Fund. rate/next</div>
                <div className={`${V} ${pnlClass(ls?.short_funding_rate ?? 0)}`}>
                  {ls?.short_funding_rate != null ? `${fmtPnl(ls.short_funding_rate)}%` : "null"}
                  {" / "}{ls?.short_next_funding ?? "null"}
                </div>
                <div className={`${V} text-right ${pnlClass(ls?.long_funding_rate ?? 0)}`}>
                  {ls?.long_funding_rate != null ? `${fmtPnl(ls.long_funding_rate)}%` : "null"}
                  {" / "}{ls?.long_next_funding ?? "null"}
                </div>

                {/* Ask / Bid + liq price */}
                <div className="text-gray-400 text-xs">Ask / Bid</div>
                <div className={`${V} text-gray-300`}>
                  {ls?.short_ask != null ? fmtNum(ls.short_ask) : "null"}
                  {" / "}
                  {ls?.short_bid != null ? fmtNum(ls.short_bid) : "null"}
                </div>
                <div className={`${V} text-gray-300 text-right`}>
                  {ls?.long_ask != null ? fmtNum(ls.long_ask) : "null"}
                  {" / "}
                  {ls?.long_bid != null ? fmtNum(ls.long_bid) : "null"}
                </div>

                {/* Leverage */}
                <div className="text-gray-400 text-xs">Leverage</div>
                <div className="flex items-center gap-0.5">
                  <div className="flex items-center bg-gray-800 rounded border border-gray-700 px-1 py-0.5 w-14">
                    <input type="number" min="1" max="125" step="1"
                      value={localConfig.short_leverage ?? 1}
                      onChange={(e) => set("short_leverage", Math.max(1, Number(e.target.value)))}
                      onBlur={() => save("short_leverage")}
                      className="bg-transparent w-full text-white text-xs outline-none" />
                  </div>
                  <FieldControls field="short_leverage" noX />
                </div>
                <div className="flex items-center gap-0.5 justify-end">
                  <div className="flex items-center bg-gray-800 rounded border border-gray-700 px-1 py-0.5 w-14">
                    <input type="number" min="1" max="125" step="1"
                      value={localConfig.long_leverage ?? 1}
                      onChange={(e) => set("long_leverage", Math.max(1, Number(e.target.value)))}
                      onBlur={() => save("long_leverage")}
                      className="bg-transparent w-full text-white text-xs outline-none" />
                  </div>
                  <FieldControls field="long_leverage" noX />
                </div>

                {/* Adjustment — label + buttons in same row */}
                <div className="text-gray-400 text-xs">Adjustment</div>
                <div className="col-span-2 flex border border-gray-600 rounded overflow-hidden w-fit">
                  {(["notify_only", "adjust"] as const).map((mode) => (
                    <button key={mode}
                      className={`px-2 py-0.5 text-xs border-l border-gray-600 first:border-l-0 ${localConfig.adjustment_mode === mode ? "bg-gray-700 text-gray-200" : "text-gray-400 hover:bg-gray-800"}`}
                      onClick={() => { set("adjustment_mode", mode); send({ adjustment_mode: mode }); }}>
                      {mode === "notify_only" ? "Notify" : "Adjust"}
                    </button>
                  ))}
                </div>

                {/* Size: pos / min / max */}
                <div className="text-gray-400 text-xs">Size</div>
                <div className={V}>
                  <span className="text-red-400 font-bold">{fmtSz(ls?.short_size)}</span>
                  <span className="text-gray-500"> / {fmtSz(ls?.min_size_short)} / {fmtSz(ls?.max_size_short)}</span>
                </div>
                <div className={`${V} text-right`}>
                  <span className="text-green-400 font-bold">{fmtSz(ls?.long_size)}</span>
                  <span className="text-gray-500"> / {fmtSz(ls?.min_size_long)} / {fmtSz(ls?.max_size_long)}</span>
                </div>

                {/* Entry price from open positions */}
                <div className="text-gray-400 text-xs">Entry</div>
                <div className={`${V} text-gray-300`}>
                  {ls?.short_entry_price != null ? fmtNum(ls.short_entry_price) : "null"}
                </div>
                <div className={`${V} text-gray-300 text-right`}>
                  {ls?.long_entry_price != null ? fmtNum(ls.long_entry_price) : "null"}
                </div>

                {/* Fees: open/close per exchange = total */}
                <div className="text-gray-400 text-xs">Fees</div>
                {hasFees ? (<>
                  <div className={`${V} text-red-400`}>{fmtFee(sOf, sCf)}</div>
                  <div className={`${V} text-red-400 text-right`}>
                    {fmtFee(lOf, lCf)}
                    <span className="text-gray-500 ml-1">= {fmtPnl(feesTotal)}</span>
                  </div>
                </>) : (
                  <div className={`${V} text-gray-500 col-span-2`}>null</div>
                )}

                {/* Funding: accrued / est.next per exchange = total */}
                <div className="text-gray-400 text-xs">Funding</div>
                {hasFunding ? (<>
                  <div className={`${V} ${pnlClass(sAccrued ?? 0)}`}>{fmtFundCell(sAccrued, sEstNext)}</div>
                  <div className={`${V} text-right ${pnlClass(lAccrued ?? 0)}`}>
                    {fmtFundCell(lAccrued, lEstNext)}
                    <span className="text-gray-500 ml-1">= {fmtPnl(fundingTotal)}</span>
                  </div>
                </>) : (
                  <div className={`${V} text-gray-500 col-span-2`}>null</div>
                )}

                {/* P/L unrealized per leg */}
                <div className="text-gray-400 text-xs">P/L</div>
                <div className={`${V} ${ls?.short_pnl != null ? pnlClass(ls.short_pnl) : "text-gray-500"}`}>
                  {ls?.short_pnl != null ? fmtPnl(ls.short_pnl) : "null"}
                </div>
                <div className={`${V} text-right ${ls?.long_pnl != null ? pnlClass(ls.long_pnl) : "text-gray-500"}`}>
                  {ls?.long_pnl != null ? fmtPnl(ls.long_pnl) : "null"}
                </div>

                {/* Entry spread */}
                <div className="text-gray-400 text-xs">Entry spread</div>
                <div className={`${V} col-span-2 ${ls?.enter_spread != null ? pnlClass(ls.enter_spread) : "text-gray-500"}`}>
                  {ls?.enter_spread != null ? `${fmtPnl(ls.enter_spread)}%` : "null"}
                </div>

                {/* P/L net */}
                <div className="text-gray-400 text-xs">P/L net</div>
                {hasPos ? (
                  <div className={`${V} col-span-2 font-bold ${pnlClass(net)}`}>
                    {fmtPnl(net)}
                    <span className="text-gray-500 font-normal text-xs ml-1">
                      ({fmtPnl(gross)}{feesTotal !== 0 ? ` ${fmtPnl(feesTotal)}` : ""}{fundingTotal !== 0 ? ` ${fmtPnl(fundingTotal)}` : ""})
                    </span>
                  </div>
                ) : (
                  <div className={`${V} text-gray-500 col-span-2`}>null</div>
                )}

                {/* Orders */}
                <div className="text-gray-400 text-xs">Orders</div>
                <div className={`${V} text-gray-300`}>{ls?.short_orders ?? 0}</div>
                <div className={`${V} text-gray-300 text-right`}>{ls?.long_orders ?? 0}</div>
              </div>
            );
          })()}

          {/* ── Spread tracking + chart ── */}
          <div className="px-2 pb-2 flex flex-col gap-1 border-t border-gray-700/50 pt-1">
            {(() => {
              const openArr = openSpreadHistory.current;
              const closeArr = closeSpreadHistory.current;
              const openMin = openArr.length ? Math.min(...openArr) : null;
              const openMax = openArr.length ? Math.max(...openArr) : null;
              const closeMin = closeArr.length ? Math.min(...closeArr) : null;
              const closeMax = closeArr.length ? Math.max(...closeArr) : null;
              return (
                <div className="grid grid-cols-[auto_auto_1fr_auto] gap-x-2 gap-y-1 items-center text-xs">
                  {/* open row: label | spread | min/max | short entry / liq */}
                  <span className="text-green-400 font-bold text-sm">Open</span>
                  <span className={`font-bold text-sm text-center w-12 inline-block ${pnlClass(ls?.open_spread_current ?? 0)}`}>
                    {ls != null ? ls.open_spread_current.toFixed(2) : "-"}
                  </span>
                  <div className="text-white text-xs text-center">
                    {openMin != null ? openMin.toFixed(2) : "-"} / {openMax != null ? openMax.toFixed(2) : "-"}
                  </div>
                  {/* short current price (ask) + liq */}
                  <div className="text-xs text-center">
                    <span className="text-red-300">{ls?.short_price != null ? fmtNum(ls.short_price) : "-"}</span>
                    {ls?.short_liq_price != null && (
                      <span className="text-red-400 underline ml-1 text-[10px]">{fmtNum(ls.short_liq_price)}</span>
                    )}
                  </div>

                  {/* close row: label | spread | min/max | long current price (bid) + liq */}
                  <span className="text-red-400 font-bold text-sm">Close</span>
                  <span className={`font-bold text-sm text-center w-12 inline-block ${pnlClass(ls?.close_spread_current ?? 0)}`}>
                    {ls != null ? ls.close_spread_current.toFixed(2) : "-"}
                  </span>
                  <div className="text-white text-xs text-center">
                    {closeMin != null ? closeMin.toFixed(2) : "-"} / {closeMax != null ? closeMax.toFixed(2) : "-"}
                  </div>
                  <div className="text-xs text-center">
                    <span className="text-green-300">{ls?.long_price != null ? fmtNum(ls.long_price) : "-"}</span>
                    {ls?.long_liq_price != null && (
                      <span className="text-green-400 underline ml-1 text-[10px]">{fmtNum(ls.long_liq_price)}</span>
                    )}
                  </div>
                </div>
              );
            })()}

            <button
              className="self-start px-2 py-0.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-xs mt-0.5"
              onClick={() => onSpreadHistory?.(config.id)}
            >
              📈 Spread history
            </button>

            <div className="border border-gray-700 rounded overflow-hidden">
              <SpreadChart
                openSpreads={openSpreadHistory.current}
                closeSpreads={closeSpreadHistory.current}
                shortLabel={activeShort}
                longLabel={activeLong}
                version={chartTick}
                height={160}
              />
            </div>
          </div>

        </div>
      )}
    </div>
  );
};
