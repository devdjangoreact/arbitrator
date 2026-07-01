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
