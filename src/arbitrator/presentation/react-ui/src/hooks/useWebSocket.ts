// ponytail: minimalist websocket hook with basic reconnect. Unwraps WsEnvelope {type, payload}.
import { useState, useEffect, useRef, useCallback } from "react";
import { useAppStore } from "../store";

type ConnectionStatus = "connecting" | "open" | "closed" | "error";

export function useWebSocket<T>(urlPath: string) {
  const [data, setData] = useState<T | null>(null);
  const [type, setType] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const setGlobalWsConnected = useAppStore((state) => state.setWsConnected);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    // Handle Vite dev server port vs backend port
    const backendHost = window.location.port.startsWith("51")
      ? "localhost:8000"
      : window.location.host;
    const wsUrl = `${protocol}//${backendHost}${urlPath}`;

    wsRef.current = new WebSocket(wsUrl);
    setStatus("connecting");

    wsRef.current.onopen = () => {
      setStatus("open");
      setGlobalWsConnected(true);
      if (reconnectTimeoutRef.current)
        clearTimeout(reconnectTimeoutRef.current);
    };

    wsRef.current.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        // Unwrap the backend's WsEnvelope pattern { type, payload }
        if (parsed && typeof parsed === "object" && "payload" in parsed) {
          setType(parsed.type);
          setData(parsed.payload);
        } else {
          // Fallback if not enveloped
          setData(parsed);
        }
      } catch (e) {
        console.error("Failed to parse WS message:", e);
      }
    };

    wsRef.current.onclose = () => {
      setStatus("closed");
      setGlobalWsConnected(false);
      reconnectTimeoutRef.current = window.setTimeout(connect, 3000);
    };

    wsRef.current.onerror = () => {
      setStatus("error");
    };
  }, [urlPath, setGlobalWsConnected]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current)
        clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  const sendMessage = useCallback((type: string, payload: object) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload }));
    }
  }, []);

  return { data, type, status, sendMessage };
}
