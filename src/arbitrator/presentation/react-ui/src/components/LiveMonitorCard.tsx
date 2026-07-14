import React, { useState } from "react";
import type { MonitorConfig, UpdateConfigPayload } from "../types";

interface Props {
  config: MonitorConfig;
  onUpdate: (payload: UpdateConfigPayload) => void;
  onClose: (id: string) => void;
}

export const LiveMonitorCard: React.FC<Props> = ({
  config,
  onUpdate,

}) => {
  const [localConfig, setLocalConfig] = useState<MonitorConfig>(config);
  const [saving, setSaving] = useState(false);

  const handleLocalChange = (key: keyof MonitorConfig, value: any) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
  };

  const saveConfig = (key: keyof MonitorConfig) => {
    setSaving(true);
    onUpdate({
      cmd: "update_config",
      monitor_id: config.id,
      config: { [key]: localConfig[key] },
    });
    setTimeout(() => setSaving(false), 500);
  };

  const handleActiveToggle = (isActive: boolean) => {
    handleLocalChange("is_active", isActive);
    onUpdate({
      cmd: "update_config",
      monitor_id: config.id,
      config: { is_active: isActive },
    });
  };

  const Checkmark = () => (
    <span className={`text-gray-500 text-xs ml-1 ${saving ? "text-green-500" : ""}`}>
      ✓
    </span>
  );

  return (
    <div
      className="rounded-md border border-gray-700 flex flex-col font-sans text-sm w-full"
      style={{ backgroundColor: "#1e293b", color: "#cbd5e1" }}
    >
      {/* Header */}
      <div
        className="flex justify-between items-center p-3 border-b border-gray-700"
        style={{ backgroundColor: "#1e293b" }}
      >
        <div className="font-bold flex items-center gap-2 text-white text-lg">
          <span className="text-gray-400">★</span>
          <span>{config.symbol}</span>
          <span className="text-red-500 text-xs">📌</span>
        </div>
        <div className="text-xs font-bold flex gap-4 uppercase tracking-wider items-center">
          <span className="text-red-500 flex items-center gap-1 border-b border-dashed border-red-500 pb-0.5">
            {config.short_exchange} <span className="text-lg leading-none">↓</span>
          </span>
          <span className="text-gray-500">-</span>
          <span className="text-green-500 flex items-center gap-1 border-b border-dashed border-green-500 pb-0.5">
            {config.long_exchange} <span className="text-lg leading-none">↑</span>
          </span>
        </div>
      </div>

      <div className="p-4 flex flex-col gap-4">
        {/* Strategy Params */}
        <div className="space-y-3">
          {/* Side */}
          <div className="flex items-center">
            <label className="w-28 text-gray-400">Side:</label>
            <div className="flex rounded border border-gray-600 overflow-hidden text-xs">
              {["Auto", "LONG", "SHORT"].map((s) => (
                <button
                  key={s}
                  className={`px-3 py-1 ${localConfig.side === s ? "bg-teal-500 text-white" : "bg-transparent text-gray-400 hover:bg-gray-700"}`}
                  onClick={() => {
                    handleLocalChange("side", s);
                    saveConfig("side");
                  }}
                >
                  {s} {localConfig.side === s && "✓"}
                </button>
              ))}
            </div>
          </div>

          {/* Open Spread */}
          <div className="flex items-center">
            <label className="w-28 text-gray-400">Open Spread:</label>
            <div className="flex items-center gap-2 flex-1">
              <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 p-1">
                <input
                  type="number"
                  step="0.1"
                  value={localConfig.open_spread_pct || ""}
                  onChange={(e) =>
                    handleLocalChange("open_spread_pct", Number(e.target.value))
                  }
                  onBlur={() => saveConfig("open_spread_pct")}
                  className="bg-transparent w-full text-white outline-none pl-1"
                />
                <Checkmark />
              </div>
              <span className="text-gray-400">T:</span>
              <div className="flex items-center w-16 bg-gray-800 rounded border border-gray-700 p-1">
                <input
                  type="number"
                  value={localConfig.open_ticks || ""}
                  onChange={(e) =>
                    handleLocalChange("open_ticks", Number(e.target.value))
                  }
                  onBlur={() => saveConfig("open_ticks")}
                  className="bg-transparent w-full text-white outline-none text-center"
                />
                <Checkmark />
              </div>
            </div>
          </div>

          {/* Close Spread */}
          <div className="flex items-center">
            <label className="w-28 text-gray-400">Close Spread:</label>
            <div className="flex items-center gap-2 flex-1">
              <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 p-1">
                <input
                  type="number"
                  step="0.1"
                  value={localConfig.close_spread_pct || ""}
                  onChange={(e) =>
                    handleLocalChange("close_spread_pct", Number(e.target.value))
                  }
                  onBlur={() => saveConfig("close_spread_pct")}
                  className="bg-transparent w-full text-white outline-none pl-1"
                />
                <Checkmark />
              </div>
              <span className="text-gray-400">T:</span>
              <div className="flex items-center w-16 bg-gray-800 rounded border border-gray-700 p-1">
                <input
                  type="number"
                  value={localConfig.close_ticks || ""}
                  onChange={(e) =>
                    handleLocalChange("close_ticks", Number(e.target.value))
                  }
                  onBlur={() => saveConfig("close_ticks")}
                  className="bg-transparent w-full text-white outline-none text-center"
                />
                <Checkmark />
              </div>
            </div>
          </div>

          {/* Order Size */}
          <div className="flex items-center">
            <label className="w-28 text-gray-400">Order Size:</label>
            <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 p-1">
              <input
                type="number"
                value={localConfig.order_size_usdt || ""}
                onChange={(e) =>
                  handleLocalChange("order_size_usdt", Number(e.target.value))
                }
                onBlur={() => saveConfig("order_size_usdt")}
                className="bg-transparent w-full text-white outline-none pl-1"
              />
              <span className="text-gray-500 whitespace-nowrap mr-1">
                ≈312.48 $
              </span>
              <Checkmark />
            </div>
          </div>

          {/* Max orders */}
          <div className="flex items-center">
            <label className="w-28 text-gray-400">Max orders:</label>
            <div className="flex items-center flex-1 bg-gray-800 rounded border border-gray-700 p-1">
              <input
                type="number"
                value={localConfig.max_orders || ""}
                onChange={(e) =>
                  handleLocalChange("max_orders", Number(e.target.value))
                }
                onBlur={() => saveConfig("max_orders")}
                className="bg-transparent w-full text-white outline-none pl-1"
              />
              <Checkmark />
            </div>
          </div>

          {/* Allowed size */}
          <div className="flex items-center">
            <label className="w-28 text-gray-400">Allowed size:</label>
            <span className="text-teal-400 font-bold">0/ Max:4000</span>
          </div>

          {/* Checks */}
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-gray-400 cursor-pointer">
              <span className="w-24">Force Stop:</span>
              <input
                type="checkbox"
                checked={localConfig.force_stop}
                onChange={(e) => {
                  handleLocalChange("force_stop", e.target.checked);
                  saveConfig("force_stop");
                }}
                className="accent-gray-600 w-3 h-3"
              />
              <Checkmark />
            </label>
            <label className="flex items-center gap-2 text-gray-400 cursor-pointer">
              <span className="w-24">Total Stop:</span>
              <input
                type="checkbox"
                checked={localConfig.total_stop}
                onChange={(e) => {
                  handleLocalChange("total_stop", e.target.checked);
                  saveConfig("total_stop");
                }}
                className="accent-gray-600 w-3 h-3"
              />
              <Checkmark />
            </label>
          </div>

          {/* Is Active Controls */}
          <div className="flex items-center gap-2 pt-1">
            <label className="w-20 text-gray-400">Is Active?:</label>
            <div className="flex gap-1 flex-1">
              <button
                onClick={() => handleActiveToggle(true)}
                className={`flex-1 py-1 px-2 text-xs rounded border flex items-center justify-center gap-1 ${localConfig.is_active ? "bg-gray-700 text-white border-gray-600" : "bg-[#1e293b] text-gray-400 border-gray-700 hover:bg-gray-800"}`}
              >
                ▶ Start
              </button>
              <button
                onClick={() => handleActiveToggle(false)}
                className={`flex-1 py-1 px-2 text-xs rounded border flex items-center justify-center gap-1 ${!localConfig.is_active ? "bg-red-900/50 text-red-400 border-red-900" : "bg-[#1e293b] text-gray-400 border-gray-700 hover:bg-gray-800"}`}
              >
                ■ Stop
              </button>
              <button className="flex-1 py-1 px-2 text-xs rounded border bg-[#1e293b] text-blue-400 border-gray-700 hover:bg-gray-800 flex items-center justify-center gap-1">
                ⟳ Restart
              </button>
            </div>
          </div>
        </div>

        {/* Exchange Data Grid */}
        <div className="grid grid-cols-[auto_1fr_1fr] gap-x-2 gap-y-1 text-xs mt-2">
          {/* Headers */}
          <div></div>
          <div className="font-bold text-white uppercase">
            {config.short_exchange}
          </div>
          <div className="font-bold text-white uppercase text-right">
            {config.long_exchange}
          </div>

          <div className="text-gray-400">Funding rate:</div>
          <div className="text-green-500">0.005%</div>
          <div className="text-red-500 text-right">0.005%</div>

          <div className="text-gray-400 whitespace-nowrap">Next Funding</div>
          <div className="col-span-2 flex justify-between">
            <div className="text-gray-300">
              15:00:00
              <br />
              (01:56:02) | 4h
            </div>
            <div className="text-gray-300 text-right">
              15:00:00
              <br />
              (01:56:02) | 4h
            </div>
          </div>

          <div className="text-gray-400">Ask</div>
          <div className="text-gray-300">0.69929</div>
          <div className="text-gray-300 text-right">0.56054</div>

          <div className="text-gray-400">Bid</div>
          <div className="text-gray-300">0.69087</div>
          <div className="text-gray-300 text-right">0.54913</div>

          <div className="text-gray-400">Size</div>
          <div className="text-gray-300">-</div>
          <div className="text-gray-300 text-right">-</div>

          <div className="text-gray-400">Leverage</div>
          <div className="text-gray-400 flex items-center gap-1">
            10x (cross) <span className="text-yellow-600">✎</span>
          </div>
          <div className="text-gray-400 text-right">10x (cross)</div>

          <div className="text-gray-400 col-span-3 mt-1">
            Adjustment notification:
          </div>
          <div className="col-span-3 flex border border-gray-600 rounded overflow-hidden w-fit mb-1">
            <button className="bg-gray-700 text-gray-200 px-3 py-1 text-xs">
              Notify only
            </button>
            <button className="bg-transparent text-gray-400 px-3 py-1 text-xs hover:bg-gray-800 border-l border-gray-600">
              Adjust
            </button>
          </div>

          <div className="text-gray-400">Max size</div>
          <div className="text-gray-300">300000</div>
          <div className="text-gray-300 text-right">4000</div>

          <div className="text-gray-400">Price</div>
          <div className="text-gray-500">-</div>
          <div className="text-gray-500 text-right">-</div>

          <div className="text-gray-400">P/L</div>
          <div className="text-gray-500">-</div>
          <div className="text-gray-500 text-right">-</div>

          <div className="text-gray-400">Realized PNL</div>
          <div className="text-gray-500">-</div>
          <div className="text-gray-500 text-right">-</div>

          <div className="text-gray-400">Enter spread</div>
          <div className="text-gray-500">-%</div>
          <div className="text-gray-500 text-right">-%</div>

          <div className="text-gray-400">Orders</div>
          <div className="text-gray-300">0</div>
          <div className="text-gray-300 text-right">0</div>
        </div>

        {/* Spread Tracking */}
        <div className="flex flex-col gap-2 pt-2 border-t border-gray-700 mt-2">
          <div className="flex justify-between items-center text-xs">
            <span className="text-gray-400 w-16">
              Open
              <br />
              spread:
            </span>
            <span className="text-green-500 font-bold text-base">23.249</span>
            <span className="text-teal-500">Min: -21.824 Max: 23.531</span>
          </div>
          <div className="flex justify-between items-center text-xs">
            <span className="text-gray-400 w-16">
              Close
              <br />
              spread:
            </span>
            <span className="text-red-500 font-bold text-base">27.344</span>
            <span className="text-teal-500">Min: -19.013 Max: 28.003</span>
          </div>

          <button className="bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs py-1 px-3 rounded w-fit mt-1">
            Spread history
          </button>

          {/* Mini Chart Mock */}
          <div className="h-16 border-b border-gray-700 relative mt-2 text-[10px] text-gray-600">
            <div className="absolute w-full border-t border-dashed border-red-900/50 top-2"></div>
            <div className="absolute w-full border-t border-dashed border-teal-900/50 top-6"></div>
            <div className="absolute w-full border-t border-dashed border-blue-900/50 top-10"></div>

            {/* Y-axis labels mock */}
            <div className="absolute right-0 top-0 flex flex-col justify-between h-full text-right items-end leading-none">
              <span>30</span>
              <span>25</span>
              <span>20</span>
              <span>15</span>
              <span>10</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};