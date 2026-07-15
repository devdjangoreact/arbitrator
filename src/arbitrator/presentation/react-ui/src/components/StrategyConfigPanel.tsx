import React, { useState } from "react";
import type { StrategyConfig } from "../types";

interface Meta {
  label: string;
  desc: string;
  category: string;
}

// Mocking STRATEGY_META which should ideally come from backend or shared constants
const STRATEGY_META: Record<string, Meta> = {
  // Placeholder, would be populated dynamically
  example_param: {
    label: "Example Parameter",
    desc: "This is an example",
    category: "Інші налаштування",
  },
};

interface Props {
  config: StrategyConfig;
  onSave: (config: StrategyConfig) => void;
}

export const StrategyConfigPanel: React.FC<Props> = ({ config, onSave }) => {
  const [localConfig, setLocalConfig] = useState<StrategyConfig>(config);
  const [hasChanges, setHasChanges] = useState(false);

  // Group config by categories based on meta
  const groups: Record<string, any[]> = {};

  Object.entries(localConfig).forEach(([key, value]) => {
    if (key === "strategy_overrides" || key === "allowed_strategies") {
      groups["Advanced (JSON)"] = groups["Advanced (JSON)"] || [];
      groups["Advanced (JSON)"].push({
        key,
        value,
        meta: { label: key, desc: "JSON format", category: "Advanced (JSON)" },
      });
      return;
    }

    const meta = STRATEGY_META[key] || {
      label: key,
      desc: "",
      category: "Інші налаштування",
    };
    const cat = meta.category;
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push({ key, value, meta });
  });

  const handleSave = () => {
    onSave(localConfig);
    setHasChanges(false);
  };

  const handleInputChange = (key: string, value: any) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  return (
    <div className="strategy-config-panel">
      {Object.entries(groups).map(([category, items]) => (
        <div key={category} className="mb-6 p-4 border border-gray-200 rounded">
          <h3 className="font-bold text-lg mb-4">{category}</h3>
          <div className="space-y-4">
            {items.map((item) => (
              <div key={item.key} className="flex flex-col">
                <label className="font-semibold text-sm">
                  {item.meta.label}
                  {item.meta.desc && (
                    <span className="text-xs text-gray-500 ml-2 block">
                      {item.meta.desc}
                    </span>
                  )}
                </label>

                {/* Very basic renderer - would be expanded for specific input types (checkbox, numbers, text) */}
                {typeof item.value === "boolean" ? (
                  <input
                    type="checkbox"
                    checked={item.value}
                    onChange={(e) =>
                      handleInputChange(item.key, e.target.checked)
                    }
                    className="mt-1"
                  />
                ) : category === "Advanced (JSON)" ? (
                  // Will be replaced by JsonEditorTextarea in integration
                  <textarea
                    value={
                      typeof item.value === "object"
                        ? JSON.stringify(item.value, null, 2)
                        : item.value
                    }
                    onChange={(e) => {
                      try {
                        const parsed = JSON.parse(e.target.value);
                        handleInputChange(item.key, parsed);
                      } catch (err) {
                        // Handle invalid JSON typing (temporarily store as string in real app until valid)
                      }
                    }}
                    className="border border-gray-300 rounded p-2 font-mono text-sm w-full h-32"
                  />
                ) : (
                  <input
                    type={typeof item.value === "number" ? "number" : "text"}
                    value={item.value}
                    onChange={(e) =>
                      handleInputChange(
                        item.key,
                        typeof item.value === "number"
                          ? Number(e.target.value)
                          : e.target.value,
                      )
                    }
                    className="border border-gray-300 rounded p-2 w-full max-w-md"
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {hasChanges && (
        <button
          className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded mt-4"
          onClick={handleSave}
        >
          Зберегти зміни
        </button>
      )}
    </div>
  );
};
