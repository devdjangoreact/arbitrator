import { useState, useEffect, useRef, useCallback } from "react";
import type { MonitorLiveState } from "../types";

export function useMonitorWs(monitorId: string) {
  const [liveState, setLiveState] = useState<MonitorLiveState | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (!monitorId) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.port.startsWith("51") ? "localhost:8000" : window.location.host;
    const url = `${protocol}//${host}/ws/monitor/${encodeURIComponent(monitorId)}`;

    wsRef.current = new WebSocket(url);

    wsRef.current.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg?.type === "monitor_update" && msg.data) {
          setLiveState((prev) => ({ ...(prev ?? {}), ...msg.data } as MonitorLiveState));
        }
      } catch {
        // ignore parse errors
      }
    };

    wsRef.current.onclose = () => {
      reconnectRef.current = window.setTimeout(connect, 2000);
    };

    wsRef.current.onerror = () => {
      wsRef.current?.close();
    };
  }, [monitorId]);

  const reconnect = useCallback(() => {
    if (reconnectRef.current) clearTimeout(reconnectRef.current);
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setLiveState(null);
    connect();
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { state: liveState, reconnect };
}
