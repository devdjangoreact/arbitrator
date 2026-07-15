import { useState, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { Card, CardContent } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";

interface ExchangeSetting {
  exchange_id: string;
  api_key_masked: string;
  configured: boolean;
  has_secret: boolean;
  has_password: boolean;
}

interface SettingsSnapshot {
  exchanges: ExchangeSetting[];
}

const STRATEGY_META: Record<
  string,
  { label: string; desc: string; category: string }
> = {
  live_auto_trade_enabled: {
    label: "Live Автоторгівля",
    desc: "Дозволити боту відкривати реальні ордери.",
    category: "Live Auto-Trade",
  },
  live_auto_trade_post_fill_min_spread_pct: {
    label: "Мін. спред після входу (%)",
    desc: "Якщо спред стає меншим - закрити позицію.",
    category: "Live Auto-Trade",
  },
  live_auto_trade_dca_spread_step_pct: {
    label: "Крок спреду усереднення (%)",
    desc: "Спред для DCA.",
    category: "Live Auto-Trade",
  },
  live_auto_trade_dca_max_layers: {
    label: "Макс. рівнів усереднення",
    desc: "Скільки разів бот може робити DCA.",
    category: "Live Auto-Trade",
  },
  live_auto_trade_dca_min_liq_distance_pct: {
    label: "Мін. відстань до ліквідації (%)",
    desc: "Заборона DCA близько до ліквідації.",
    category: "Live Auto-Trade",
  },
  live_auto_trade_dca_funding_skip_seconds: {
    label: "Ігнорувати перед фандінгом (сек)",
    desc: "Не робити DCA перед нарахуванням.",
    category: "Live Auto-Trade",
  },

  screener_auto_trade_enabled: {
    label: "Paper Автоторгівля",
    desc: "Дозволити віртуальні (тестові) ордери.",
    category: "Paper Auto-Trade",
  },
  screener_auto_trade_max_positions: {
    label: "Макс. Paper позицій",
    desc: "Ліміт віртуальних позицій.",
    category: "Paper Auto-Trade",
  },
  screener_auto_trade_notional_usdt: {
    label: "Об'єм позиції (Paper)",
    desc: "Розмір віртуального ордера.",
    category: "Paper Auto-Trade",
  },
  screener_auto_trade_open_spread_pct: {
    label: "Спред відкриття (%)",
    desc: "Поріг входу.",
    category: "Paper Auto-Trade",
  },
  screener_auto_trade_close_spread_pct: {
    label: "Спред закриття (%)",
    desc: "Поріг виходу.",
    category: "Paper Auto-Trade",
  },
  screener_auto_trade_check_seconds: {
    label: "Інтервал перевірки (сек)",
    desc: "Частота сканування.",
    category: "Paper Auto-Trade",
  },
  screener_auto_trade_unhedged_timeout_seconds: {
    label: "Таймаут розхеджування (сек)",
    desc: "Очікування другої ноги.",
    category: "Paper Auto-Trade",
  },

  live_liq_guard_enabled: {
    label: "Live: Захист від ліквідації",
    desc: "Автозакриття при ризику ліквідації.",
    category: "Live Захисти",
  },
  live_liq_guard_check_interval_seconds: {
    label: "Інтервал перевірки (сек)",
    desc: "Частота перевірки маржі.",
    category: "Live Захисти",
  },
  live_liq_guard_warning_pct_to_liq: {
    label: "Поріг закриття (маржа %)",
    desc: "Закрити при використанні % маржі.",
    category: "Live Захисти",
  },
  live_funding_protect_enabled: {
    label: "Live: Захист фандінгу",
    desc: "Закривати перед збитковим фандінгом.",
    category: "Live Захисти",
  },
  live_funding_protect_check_interval_seconds: {
    label: "Інтервал перевірки (сек)",
    desc: "Частота пошуку фандінгів.",
    category: "Live Захисти",
  },
  live_funding_protect_act_window_seconds: {
    label: "Вікно дій до виплати (сек)",
    desc: "За скільки секунд закривати.",
    category: "Live Захисти",
  },
  live_funding_protect_skip_within_seconds: {
    label: "Блок перед виплатою (сек)",
    desc: "Блок дій в останні секунди.",
    category: "Live Захисти",
  },
  live_funding_protect_min_reopen_spread_pct: {
    label: "Мін. спред перевідкриття (%)",
    desc: "Спред для повернення в позицію.",
    category: "Live Захисти",
  },

  liq_guard_enabled: {
    label: "Paper: Захист від ліквідації",
    desc: "Віртуальний захист маржі.",
    category: "Paper Захисти",
  },
  liq_guard_check_interval_seconds: {
    label: "Інтервал перевірки (сек)",
    desc: "",
    category: "Paper Захисти",
  },
  liq_guard_warning_pct_to_liq: {
    label: "Поріг закриття (маржа %)",
    desc: "",
    category: "Paper Захисти",
  },
  funding_reentry_enabled: {
    label: "Paper: Ре-ентер фандінгу",
    desc: "Віртуальний тест фандінгу.",
    category: "Paper Захисти",
  },
  funding_reentry_check_interval_seconds: {
    label: "Інтервал перевірки (сек)",
    desc: "",
    category: "Paper Захисти",
  },
  funding_reentry_act_window_seconds: {
    label: "Вікно дій (сек)",
    desc: "",
    category: "Paper Захисти",
  },
  funding_reentry_skip_within_seconds: {
    label: "Блок перед виплатою (сек)",
    desc: "",
    category: "Paper Захисти",
  },
  funding_reentry_min_spread_pct: {
    label: "Мін. спред перевідкриття (%)",
    desc: "",
    category: "Paper Захисти",
  },

  spot_enabled: {
    label: "Дозволити SPOT",
    desc: "Включати спотові ринки.",
    category: "Движок Стратегій",
  },
  quote_max_age_seconds: {
    label: "Макс. вік котирування (сек)",
    desc: "",
    category: "Движок Стратегій",
  },

  opp_default_leverage: {
    label: "Opp: Плече",
    desc: "",
    category: "Модуль Opportunity",
  },
  opp_position_imbalance_tolerance_pct: {
    label: "Opp: Дисбаланс (%)",
    desc: "",
    category: "Модуль Opportunity",
  },
  opp_accumulate_step_usdt: {
    label: "Opp: Крок об'єму (USDT)",
    desc: "Крок додавання об'єму при ручному наборі.",
    category: "Модуль Opportunity",
  },
  opp_default_max_notional_usdt: {
    label: "Opp: Макс об'єм (USDT)",
    desc: "",
    category: "Модуль Opportunity",
  },
  opp_default_accumulate_spread_pct: {
    label: "Opp: Спред для набору (%)",
    desc: "",
    category: "Модуль Opportunity",
  },

  historical_screener_enabled: {
    label: "Включити моніторинг",
    desc: "",
    category: "Історичний моніторинг",
  },
  historical_screener_lookback_minutes: {
    label: "Період моніторингу (хв)",
    desc: "",
    category: "Історичний моніторинг",
  },
  historical_screener_scan_interval_seconds: {
    label: "Інтервал сканування (сек)",
    desc: "",
    category: "Історичний моніторинг",
  },
  historical_screener_spread_threshold_pct: {
    label: "Поріг спреду (%)",
    desc: "",
    category: "Історичний моніторинг",
  },
  historical_monitor_open_spread_pct: {
    label: "Відкрити Paper ордер (%)",
    desc: "",
    category: "Історичний моніторинг",
  },
  historical_monitor_close_spread_pct: {
    label: "Закрити Paper ордер (%)",
    desc: "",
    category: "Історичний моніторинг",
  },
  historical_monitor_max_positions: {
    label: "Макс. позицій (Paper)",
    desc: "",
    category: "Історичний моніторинг",
  },
  historical_monitor_notional_usdt: {
    label: "Об'єм позиції (Paper)",
    desc: "",
    category: "Історичний моніторинг",
  },
};

const CATEGORY_ORDER = [
  "Біржі",
  "Live Auto-Trade",
  "Paper Auto-Trade",
  "Live Захисти",
  "Paper Захисти",
  "Движок Стратегій",
  "Модуль Opportunity",
  "Історичний моніторинг",
  "Інші налаштування",
  "Advanced (JSON)",
];

function formatLabel(key: string) {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function ExchangeForm({
  ex,
  onSave,
}: {
  ex: ExchangeSetting;
  onSave: (exId: string, k: string, s: string, p: string) => void;
}) {
  const [apiKey, setApiKey] = useState(ex.api_key_masked);
  const [secret, setSecret] = useState("");
  const [password, setPassword] = useState("");

  return (
    <div className="py-4 border-b border-gray-200 dark:border-gray-700 last:border-0">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-lg font-medium text-gray-900 dark:text-gray-100 uppercase">
          {ex.exchange_id}
        </h4>
        <Badge variant={ex.configured ? "long" : "short"}>
          {ex.configured ? "Configured" : "Missing"}
        </Badge>
      </div>
      <div className="flex flex-wrap gap-4 items-end">
        <div className="w-64">
          <Input
            label="API Key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="API Key"
          />
        </div>
        <div className="w-64">
          <Input
            type="password"
            label="API Secret"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="API Secret"
          />
        </div>
        {ex.has_password && (
          <div className="w-64">
            <Input
              type="password"
              label="API Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="API Password"
            />
          </div>
        )}
        <Button
          variant="primary"
          onClick={() => onSave(ex.exchange_id, apiKey, secret, password)}
        >
          Зберегти
        </Button>
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { data, status, sendMessage } =
    useWebSocket<SettingsSnapshot>("/ws/settings");

  const [strategyData, setStrategyData] = useState<Record<string, any>>({});
  const [strategyEdits, setStrategyEdits] = useState<
    Record<string, string | boolean>
  >({});
  const [, setLoadingStrategy] = useState(true);
  const [activeTab, setActiveTab] = useState("Біржі");

  useEffect(() => {
    const fetchStrategy = async () => {
      try {
        const protocol = window.location.protocol;
        const backendHost = window.location.port.startsWith("51")
          ? "localhost:8000"
          : window.location.host;
        const res = await fetch(
          `${protocol}//${backendHost}/api/config/strategy`,
        );
        if (res.ok) {
          const result = await res.json();
          const configObj = result.config ? result.config : result;
          setStrategyData(configObj);
        }
      } catch (err) {
        console.error("Failed to fetch strategy config", err);
      } finally {
        setLoadingStrategy(false);
      }
    };
    fetchStrategy();
  }, []);

  const handleSaveExchange = (
    exchange_id: string,
    api_key: string,
    api_secret: string,
    api_password: string,
  ) => {
    sendMessage("settings.save_exchange", {
      exchange_id,
      api_key,
      api_secret,
      api_password,
    });
  };

  const handleStrategyChange = (key: string, value: string | boolean) => {
    setStrategyEdits((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveStrategy = async () => {
    const mergedStrategy = { ...strategyData, ...strategyEdits };
    try {
      const protocol = window.location.protocol;
      const backendHost = window.location.port.startsWith("51")
        ? "localhost:8000"
        : window.location.host;
      await fetch(`${protocol}//${backendHost}/api/config/strategy`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: mergedStrategy }),
      });
      setStrategyData(mergedStrategy);
      setStrategyEdits({});
    } catch (err) {
      console.error("Failed to save strategy config", err);
    }
  };

  const mergedStrategy = { ...strategyData, ...strategyEdits };
  const strategyGroups: Record<
    string,
    { key: string; value: any; meta: any }[]
  > = {};

  Object.keys(strategyData).forEach((key) => {
    if (key === "allowed_strategies" || key === "strategy_overrides") {
      if (!strategyGroups["Advanced (JSON)"])
        strategyGroups["Advanced (JSON)"] = [];
      strategyGroups["Advanced (JSON)"].push({
        key,
        value:
          typeof mergedStrategy[key] === "object"
            ? JSON.stringify(mergedStrategy[key], null, 2)
            : mergedStrategy[key],
        meta: {
          label: formatLabel(key),
          desc: "JSON format",
          category: "Advanced (JSON)",
        },
      });
      return;
    }

    if (typeof strategyData[key] === "object" && strategyData[key] !== null)
      return;

    const meta = STRATEGY_META[key] || {
      label: formatLabel(key),
      desc: "",
      category: "Інші налаштування",
    };
    const cat = meta.category;
    if (!strategyGroups[cat]) strategyGroups[cat] = [];

    strategyGroups[cat].push({
      key,
      value:
        mergedStrategy[key] !== undefined
          ? mergedStrategy[key]
          : strategyData[key],
      meta,
    });
  });

  const sortedCats = CATEGORY_ORDER.filter(
    (cat) => cat === "Біржі" || strategyGroups[cat],
  );

  return (
    <div className="p-6 w-full flex flex-col space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white m-0">
          Settings
        </h1>
        {Object.keys(strategyEdits).length > 0 && activeTab !== "Біржі" && (
          <Button variant="primary" size="sm" onClick={handleSaveStrategy}>
            Зберегти зміни
          </Button>
        )}
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav
          className="-mb-px flex space-x-6 overflow-x-auto"
          aria-label="Tabs"
        >
          {sortedCats.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveTab(cat)}
              className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === cat
                  ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300"
              }`}
            >
              {cat}
            </button>
          ))}
        </nav>
      </div>

      <div className="mt-6">
        {activeTab === "Біржі" && (
          <Card>
            <CardContent>
              {status !== "open" || !data || !data.exchanges ? (
                <p className="text-gray-500 text-sm">Loading exchanges...</p>
              ) : data.exchanges.length === 0 ? (
                <p className="text-gray-500 text-sm">Немає бірж</p>
              ) : (
                data.exchanges.map((ex) => (
                  <ExchangeForm
                    key={ex.exchange_id}
                    ex={ex}
                    onSave={handleSaveExchange}
                  />
                ))
              )}
            </CardContent>
          </Card>
        )}

        {activeTab !== "Біржі" && strategyGroups[activeTab] && (
          <Card>
            <CardContent className="pt-6">
              <div className="space-y-6">
                {strategyGroups[activeTab].map((item) => (
                  <div
                    key={item.key}
                    className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-gray-100 dark:border-gray-800 pb-4 last:border-0 last:pb-0"
                  >
                    <div className="mb-2 sm:mb-0 sm:mr-4 flex-1">
                      <label className="block text-sm font-medium text-gray-900 dark:text-gray-100">
                        {item.meta.label}
                      </label>
                      {item.meta.desc && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          {item.meta.desc}
                        </p>
                      )}
                    </div>

                    <div className="w-full sm:w-64 shrink-0">
                      {activeTab === "Advanced (JSON)" ? (
                        <textarea
                          className="w-full text-sm font-mono p-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700"
                          rows={4}
                          value={item.value as string}
                          onChange={(e) => {
                            try {
                              const parsed = JSON.parse(e.target.value);
                              handleStrategyChange(item.key, parsed);
                            } catch (err) {
                              handleStrategyChange(item.key, e.target.value);
                            }
                          }}
                        />
                      ) : typeof strategyData[item.key] === "boolean" ? (
                        <div className="flex items-center h-10">
                          <input
                            type="checkbox"
                            className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                            checked={!!item.value}
                            onChange={(e) =>
                              handleStrategyChange(item.key, e.target.checked)
                            }
                          />
                          <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                            {item.value ? "Enabled" : "Disabled"}
                          </span>
                        </div>
                      ) : (
                        <Input
                          value={item.value?.toString() || ""}
                          onChange={(e) =>
                            handleStrategyChange(item.key, e.target.value)
                          }
                        />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
