/** @type {WsClient | null} */
let _settingsClient = null;

/** @param {object} ex */
function renderExchangeField(ex) {
  const div = document.createElement("div");
  div.className = "field";
  div.dataset.exchangeId = ex.exchange_id;
  const configured = ex.configured ? " (налаштовано)" : "";
  div.innerHTML = `
    <label>${ex.exchange_id.toUpperCase()} API key${configured}</label>
    <input type="text" value="${ex.api_key_masked}" data-role="api-key" autocomplete="off">
    <input type="password" placeholder="API secret" data-role="api-secret" style="margin-top:6px;" autocomplete="off">
    ${ex.has_password ? '<input type="password" placeholder="API password" data-role="api-password" style="margin-top:6px;" autocomplete="off">' : ""}
    <button type="button" class="btn" style="margin-top:8px;" data-action="save">Зберегти</button>`;
  const btn = div.querySelector("[data-action='save']");
  btn.addEventListener("click", () => {
    if (!_settingsClient) return;
    const key = div.querySelector("[data-role='api-key']");
    const secret = div.querySelector("[data-role='api-secret']");
    const password = div.querySelector("[data-role='api-password']");
    _settingsClient.send("settings.save_exchange", {
      exchange_id: ex.exchange_id,
      api_key: key && key.value ? key.value : "",
      api_secret: secret && secret.value ? secret.value : "",
      api_password: password && password.value ? password.value : "",
    });
  });
  return div;
}

/** @param {object} payload */
function renderSettingsSnapshot(payload) {
  AppState.settingsSnapshot = payload;
  const root = Dom.settings.exchanges();
  if (!root) return;
  root.replaceChildren();
  const exchanges = payload.exchanges || [];
  if (!exchanges.length) {
    root.innerHTML = "<p class='muted'>Немає бірж</p>";
    return;
  }
  for (const ex of exchanges) {
    root.appendChild(renderExchangeField(ex));
  }
}

function initSettings() {
  registerDeltaHandler("settings.snapshot", renderSettingsSnapshot);
  _settingsClient = new WsClient("/ws/settings", {
    onMessage(data) {
      if (data.type === "settings.action_result" && data.payload && data.payload.success) {
        const note = Dom.settings.note();
        if (note) {
          note.textContent = `Збережено: ${data.payload.exchange_id || ""}`;
          note.className = "stream-note pos";
        }
      }
    },
  });
}

window.initSettings = initSettings;

// --- Strategy Settings UI ---

let currentStrategyConfig = {};

async function fetchStrategyConfig() {
  try {
    const res = await fetch("/api/config/strategy");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    currentStrategyConfig = data;
    renderStrategyConfig(data);
  } catch (err) {
    console.error("Failed to fetch strategy config", err);
    const note = document.getElementById("strategy-settings-note");
    if (note) {
      note.textContent = "Помилка завантаження налаштувань";
      note.className = "stream-note neg";
    }
  }
}


const STRATEGY_META = {
    // --- Live Auto-Trade ---
    live_auto_trade_enabled: { label: "Live Автоторгівля", desc: "Дозволити боту відкривати реальні ордери.", category: "Live Auto-Trade" },
    live_auto_trade_post_fill_min_spread_pct: { label: "Мін. спред після входу (%)", desc: "Якщо спред стає меншим - закрити позицію.", category: "Live Auto-Trade" },
    live_auto_trade_dca_spread_step_pct: { label: "Крок спреду усереднення (%)", desc: "Спред для DCA.", category: "Live Auto-Trade" },
    live_auto_trade_dca_max_layers: { label: "Макс. рівнів усереднення", desc: "Скільки разів бот може робити DCA.", category: "Live Auto-Trade" },
    live_auto_trade_dca_min_liq_distance_pct: { label: "Мін. відстань до ліквідації (%)", desc: "Заборона DCA близько до ліквідації.", category: "Live Auto-Trade" },
    live_auto_trade_dca_funding_skip_seconds: { label: "Ігнорувати перед фандінгом (сек)", desc: "Не робити DCA перед нарахуванням.", category: "Live Auto-Trade" },

    // --- Paper/Screener Auto-Trade ---
    screener_auto_trade_enabled: { label: "Paper Автоторгівля", desc: "Дозволити віртуальні (тестові) ордери.", category: "Paper Auto-Trade" },
    screener_auto_trade_max_positions: { label: "Макс. Paper позицій", desc: "Ліміт віртуальних позицій.", category: "Paper Auto-Trade" },
    screener_auto_trade_notional_usdt: { label: "Об'єм позиції (Paper)", desc: "Розмір віртуального ордера.", category: "Paper Auto-Trade" },
    screener_auto_trade_open_spread_pct: { label: "Спред відкриття (%)", desc: "Поріг входу.", category: "Paper Auto-Trade" },
    screener_auto_trade_close_spread_pct: { label: "Спред закриття (%)", desc: "Поріг виходу.", category: "Paper Auto-Trade" },
    screener_auto_trade_check_seconds: { label: "Інтервал перевірки (сек)", desc: "Частота сканування.", category: "Paper Auto-Trade" },
    screener_auto_trade_unhedged_timeout_seconds: { label: "Таймаут розхеджування (сек)", desc: "Очікування другої ноги.", category: "Paper Auto-Trade" },

    // --- Protections (Live) ---
    live_liq_guard_enabled: { label: "Live: Захист від ліквідації", desc: "Автозакриття при ризику ліквідації.", category: "Live Захисти" },
    live_liq_guard_check_interval_seconds: { label: "Інтервал перевірки (сек)", desc: "Частота перевірки маржі.", category: "Live Захисти" },
    live_liq_guard_warning_pct_to_liq: { label: "Поріг закриття (маржа %)", desc: "Закрити при використанні % маржі.", category: "Live Захисти" },
    live_funding_protect_enabled: { label: "Live: Захист фандінгу", desc: "Закривати перед збитковим фандінгом.", category: "Live Захисти" },
    live_funding_protect_check_interval_seconds: { label: "Інтервал перевірки (сек)", desc: "Частота пошуку фандінгів.", category: "Live Захисти" },
    live_funding_protect_act_window_seconds: { label: "Вікно дій до виплати (сек)", desc: "За скільки секунд закривати.", category: "Live Захисти" },
    live_funding_protect_skip_within_seconds: { label: "Блок перед виплатою (сек)", desc: "Блок дій в останні секунди.", category: "Live Захисти" },
    live_funding_protect_min_reopen_spread_pct: { label: "Мін. спред перевідкриття (%)", desc: "Спред для повернення в позицію.", category: "Live Захисти" },

    // --- Protections (Paper) ---
    liq_guard_enabled: { label: "Paper: Захист від ліквідації", desc: "Віртуальний захист маржі.", category: "Paper Захисти" },
    liq_guard_check_interval_seconds: { label: "Інтервал перевірки (сек)", desc: "", category: "Paper Захисти" },
    liq_guard_warning_pct_to_liq: { label: "Поріг закриття (маржа %)", desc: "", category: "Paper Захисти" },
    funding_reentry_enabled: { label: "Paper: Ре-ентер фандінгу", desc: "Віртуальний тест фандінгу.", category: "Paper Захисти" },
    funding_reentry_check_interval_seconds: { label: "Інтервал перевірки (сек)", desc: "", category: "Paper Захисти" },
    funding_reentry_act_window_seconds: { label: "Вікно дій (сек)", desc: "", category: "Paper Захисти" },
    funding_reentry_skip_within_seconds: { label: "Блок перед виплатою (сек)", desc: "", category: "Paper Захисти" },
    funding_reentry_min_spread_pct: { label: "Мін. спред перевідкриття (%)", desc: "", category: "Paper Захисти" },

    // --- Strategy Engine ---
    spot_enabled: { label: "Дозволити SPOT", desc: "Включати спотові ринки.", category: "Движок Стратегій" },
    quote_max_age_seconds: { label: "Макс. вік котирування (сек)", desc: "", category: "Движок Стратегій" },
    book_max_age_seconds: { label: "Макс. вік ордербука (сек)", desc: "", category: "Движок Стратегій" },
    funding_refresh_seconds: { label: "Оновлення фандінг-рейту (сек)", desc: "Як часто завантажувати свіжі ставки фандінгу.", category: "Движок Стратегій" },
    funding_entry_window_seconds: { label: "Вікно входу фандінгу (сек)", desc: "Обмеження для стратегій на основі фандінгу.", category: "Движок Стратегій" },
    anomaly_max_spread_pct: { label: "Аномальний спред (%)", desc: "Відкидати спреди більші за цей.", category: "Движок Стратегій" },
    slippage_max_pct: { label: "Максимальне проковзування (%)", desc: "Обмеження втрат при виконанні маркет-ордерів.", category: "Движок Стратегій" },
    ticker_max_inner_spread_pct: { label: "Макс. внутрішній спред (%)", desc: "Не торгувати монету, якщо на самій біржі спред між ask/bid занадто широкий.", category: "Движок Стратегій" },
    execution_rollback_enabled: { label: "Rollback виконання", desc: "Чи намагатися закрити першу ногу, якщо друга зависла.", category: "Движок Стратегій" },
    leg_imbalance_tolerance_pct: { label: "Толерантність дисбалансу ног (%)", desc: "Допустима різниця в об'ємах між шортом і лонгом.", category: "Движок Стратегій" },
    open_fail_cooldown_sec: { label: "Кулдаун помилки входу (сек)", desc: "Тимчасово блокувати токен, якщо ордер відхилено.", category: "Движок Стратегій" },

    // --- Historical / Monitor ---
    historical_screener_enabled: { label: "Історичний скрінер", desc: "Завантажувати і шукати історичні розбіжності.", category: "Історичний моніторинг" },
    historical_screener_lookback_minutes: { label: "Глибина історії (хв)", desc: "За скільки хвилин назад аналізувати.", category: "Історичний моніторинг" },
    historical_screener_spread_threshold_pct: { label: "Мін. істор. спред (%)", desc: "Шукати спреди не менші за цей.", category: "Історичний моніторинг" },
    historical_screener_scan_interval_seconds: { label: "Інтервал сканування (сек)", desc: "", category: "Історичний моніторинг" },
    historical_monitor_open_spread_pct: { label: "Open спред (Monitor) (%)", desc: "", category: "Історичний моніторинг" },
    historical_monitor_close_spread_pct: { label: "Close спред (Monitor) (%)", desc: "", category: "Історичний моніторинг" },
    historical_monitor_max_positions: { label: "Макс. позицій (Monitor)", desc: "", category: "Історичний моніторинг" },
    historical_monitor_notional_usdt: { label: "Об'єм (Monitor USDT)", desc: "", category: "Історичний моніторинг" },

    // --- Opportunities ---
    opp_default_accumulate_spread_pct: { label: "Opp: Accumulate Спред (%)", desc: "Цільовий спред для режиму ручного Opportunity.", category: "Модуль Opportunity" },
    opp_default_max_notional_usdt: { label: "Opp: Макс. об'єм (USDT)", desc: "", category: "Модуль Opportunity" },
    opp_default_leverage: { label: "Opp: Плече", desc: "", category: "Модуль Opportunity" },
    opp_position_imbalance_tolerance_pct: { label: "Opp: Дисбаланс (%)", desc: "", category: "Модуль Opportunity" },
    opp_accumulate_step_usdt: { label: "Opp: Крок об'єму (USDT)", desc: "Крок додавання об'єму при ручному наборі.", category: "Модуль Opportunity" }
};

function renderStrategyConfig(config) {
  const root = document.getElementById("settings-strategy");
  if (!root) return;

  while (root.firstChild) {
      root.removeChild(root.firstChild);
  }

  const groups = {};
  for (const [key, value] of Object.entries(config)) {
     if (key === "allowed_strategies" || key === "strategy_overrides") {
         groups["Advanced (JSON)"] = groups["Advanced (JSON)"] || [];
         groups["Advanced (JSON)"].push({key: key, value: value, meta: { label: key, desc: "JSON format" }});
         continue;
     }

     const meta = STRATEGY_META[key] || { label: key, desc: "", category: "Інші налаштування" };
     const cat = meta.category;
     if (!groups[cat]) groups[cat] = [];
     groups[cat].push({ key: key, value: value, meta: meta });
  }

  const catOrder = ["Live Auto-Trade", "Paper Auto-Trade", "Live Захисти", "Paper Захисти", "Движок Стратегій", "Модуль Opportunity", "Історичний моніторинг", "Інші налаштування", "Advanced (JSON)"];
  const sortedCats = Object.keys(groups).sort((a, b) => {
      const idxA = catOrder.indexOf(a);
      const idxB = catOrder.indexOf(b);
      return (idxA === -1 ? 99 : idxA) - (idxB === -1 ? 99 : idxB);
  });

  for (const catName of sortedCats) {
     const items = groups[catName];

     const header = document.createElement("h2");
     header.textContent = catName;
     header.style.marginTop = "24px";
     header.style.marginBottom = "12px";
     header.style.borderBottom = "1px solid var(--border)";
     header.style.paddingBottom = "8px";
     header.style.color = "var(--primary)";
     header.style.gridColumn = "1 / -1";
     root.appendChild(header);

     for (const item of items) {
        const div = document.createElement("div");
        div.className = "field";
        div.style.marginBottom = "16px";
        div.style.background = "var(--bg-card)";
        div.style.padding = "10px";
        div.style.borderRadius = "6px";

        const label = document.createElement("label");
        label.style.fontWeight = "600";
        label.style.display = "block";
        label.style.marginBottom = "4px";
        label.style.color = "var(--fg)";

        const desc = document.createElement("div");
        desc.className = "faint";
        desc.style.fontSize = "0.85em";
        desc.style.marginBottom = "8px";
        desc.style.lineHeight = "1.3";
        desc.textContent = item.meta.desc;

        if (item.key === "allowed_strategies" || item.key === "strategy_overrides") {
           label.textContent = item.meta.label;
           const textarea = document.createElement("textarea");
           textarea.id = "strat-" + item.key;
           textarea.rows = 3;
           textarea.style.width = "100%";
           textarea.style.boxSizing = "border-box";
           textarea.style.background = "var(--bg)";
           textarea.style.color = "var(--fg)";
           textarea.style.border = "1px solid var(--border)";
           textarea.value = JSON.stringify(item.value);

           div.appendChild(label);
           if (item.meta.desc) div.appendChild(desc);
           div.appendChild(textarea);
        } else if (typeof item.value === "boolean") {
          label.style.display = "flex";
          label.style.alignItems = "center";
          label.style.cursor = "pointer";

          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.id = "strat-" + item.key;
          checkbox.checked = item.value;
          checkbox.style.marginRight = "10px";
          checkbox.style.width = "auto";

          label.appendChild(checkbox);
          label.appendChild(document.createTextNode(item.meta.label));
          div.appendChild(label);

          if (item.meta.desc) {
              desc.style.marginLeft = "24px";
              div.appendChild(desc);
          }
        } else if (typeof item.value === "number") {
           label.textContent = item.meta.label;
           const input = document.createElement("input");
           input.type = "number";
           input.id = "strat-" + item.key;
           input.value = item.value;
           input.step = "any";
           input.style.width = "100%";
           input.style.boxSizing = "border-box";

           div.appendChild(label);
           if (item.meta.desc) div.appendChild(desc);
           div.appendChild(input);
        } else {
           label.textContent = item.meta.label;
           const input = document.createElement("input");
           input.type = "text";
           input.id = "strat-" + item.key;
           input.value = item.value;
           input.style.width = "100%";
           input.style.boxSizing = "border-box";

           div.appendChild(label);
           if (item.meta.desc) div.appendChild(desc);
           div.appendChild(input);
        }
        root.appendChild(div);
     }
  }
}
async function saveStrategyConfig() {
  const root = document.getElementById("settings-strategy");
  if (!root) return;

  const updates = {};
  for (const key of Object.keys(currentStrategyConfig)) {
    const el = document.getElementById(`strat-${key}`);
    if (!el) continue;

    if (el.type === "checkbox") {
       updates[key] = el.checked;
    } else if (el.tagName === "TEXTAREA") {
       try {
           updates[key] = JSON.parse(el.value);
       } catch (e) {
           console.warn(`Invalid JSON for ${key}`);
       }
    } else if (el.type === "number") {
       updates[key] = parseFloat(el.value);
    } else {
       updates[key] = el.value;
    }
  }

  try {
    const res = await fetch("/api/config/strategy", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates)
    });

    const note = document.getElementById("strategy-settings-note");
    if (!res.ok) {
       const errData = await res.json();
       throw new Error(errData.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    currentStrategyConfig = data.config;
    renderStrategyConfig(currentStrategyConfig);

    if (note) {
      note.textContent = "Налаштування стратегій збережено";
      note.className = "stream-note pos";
      setTimeout(() => { note.textContent = ""; }, 3000);
    }
  } catch (err) {
    console.error("Failed to save strategy config", err);
    const note = document.getElementById("strategy-settings-note");
    if (note) {
      note.textContent = `Помилка збереження: ${err.message}`;
      note.className = "stream-note neg";
    }
  }
}

// Hook into the existing initSettings
const _originalInitSettings = window.initSettings;
window.initSettings = function() {
   if (_originalInitSettings) _originalInitSettings();
   fetchStrategyConfig();
   const saveBtn = document.getElementById("save-strategy-btn");
   if (saveBtn) {
       saveBtn.addEventListener("click", saveStrategyConfig);
   }
};
