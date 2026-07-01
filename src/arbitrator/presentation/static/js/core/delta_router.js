/** @type {Record<string, (payload: object) => void>} */
const _deltaHandlers = {};

/** @param {string} type @param {(payload: object) => void} handler */
function registerDeltaHandler(type, handler) {
  _deltaHandlers[type] = handler;
}

/** @param {object} message */
function routeWsMessage(message) {
  if (!message || typeof message !== "object") return;
  const type = message.type;
  const payload = message.payload;
  if (typeof type !== "string") return;

  if (type.endsWith(".snapshot")) {
    const base = type.replace(".snapshot", "");
    const handler = _deltaHandlers[`${base}.snapshot`];
    if (handler && payload) handler(payload);
    return;
  }
  if (type.endsWith(".error")) {
    const base = type.replace(".error", "");
    const handler = _deltaHandlers[`${base}.error`];
    if (handler && payload) handler(payload);
    return;
  }
  if (type.endsWith(".delta")) {
    const base = type.replace(".delta", "");
    const handler = _deltaHandlers[`${base}.delta`];
    if (handler && payload) handler(payload);
  }
}

window.registerDeltaHandler = registerDeltaHandler;
window.routeWsMessage = routeWsMessage;
