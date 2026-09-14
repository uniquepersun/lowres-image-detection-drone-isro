import { useEffect, useRef, useState } from "react";
import { Telemetry, DEFAULT_TELEMETRY, telemetryWsUrl } from "../config";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState<Telemetry>(DEFAULT_TELEMETRY);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number>(0);

  useEffect(() => {
    let cancelled = false;
    let retryTimeout: ReturnType<typeof setTimeout>;

    function connect() {
      if (cancelled) return;
      setStatus("connecting");
      const ws = new WebSocket(telemetryWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        retryRef.current = 0;
        setStatus("connected");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as Telemetry;
          setTelemetry(data);
        } catch {
          // ignore malformed packet
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setStatus("disconnected");
        const delay = Math.min(1000 * 2 ** retryRef.current, 5000);
        retryRef.current += 1;
        retryTimeout = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimeout);
      wsRef.current?.close();
    };
  }, []);

  return { telemetry, status };
}
