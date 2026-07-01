/**
 * WebSocket client: connect, send, reconnect, message dispatch.
 */
class WsClient {
  /**
   * @param {string} url
   * @param {{ onMessage?: (data: object) => void, onOpen?: () => void, onClose?: () => void }} handlers
   */
  constructor(url, handlers = {}) {
    this._url = url;
    this._handlers = handlers;
    this._socket = null;
    this._reconnectDelayMs = 2000;
    this._shouldReconnect = true;
    this._connect();
  }

  _connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = this._url.startsWith("ws") ? this._url : `${protocol}//${window.location.host}${this._url}`;
    this._socket = new WebSocket(url);

    this._socket.addEventListener("open", () => {
      if (this._handlers.onOpen) this._handlers.onOpen();
    });

    this._socket.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        if (this._handlers.onMessage) this._handlers.onMessage(data);
        routeWsMessage(data);
      } catch (_err) {
        /* ignore malformed frames */
      }
    });

    this._socket.addEventListener("close", () => {
      if (this._handlers.onClose) this._handlers.onClose();
      if (this._shouldReconnect) {
        window.setTimeout(() => this._connect(), this._reconnectDelayMs);
      }
    });
  }

  /** @param {string} type @param {object} payload */
  send(type, payload = {}) {
    if (!this._socket || this._socket.readyState !== WebSocket.OPEN) return;
    this._socket.send(JSON.stringify({ type, payload }));
  }

  close() {
    this._shouldReconnect = false;
    if (this._socket) this._socket.close();
  }
}

window.WsClient = WsClient;
