import { useEffect, useRef, useState } from "react";
import { getToken } from "../services/api.js";

// Opens a WebSocket to the backend, reconnects automatically if it drops,
// and measures round-trip latency with ping/pong every 3 seconds.
// Every message from the server is passed to `onMessage(message)`.
export function useBackendSocket(onMessage) {
  const [connected, setConnected] = useState(false);
  const [latencyMs, setLatencyMs] = useState(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    let socket = null;
    let reconnectTimer = null;
    let pingTimer = null;
    let closedByUs = false;

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const token = getToken();  // v1.1: the live channel needs the login token
      socket = new WebSocket(`${protocol}://${window.location.host}/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`);

      socket.onopen = () => {
        setConnected(true);
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "ping", sent_at: Date.now() }));
          }
        }, 3000);
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === "pong") setLatencyMs(Date.now() - message.data.sent_at);
        onMessageRef.current?.(message);
      };

      socket.onclose = () => {
        setConnected(false);
        clearInterval(pingTimer);
        if (!closedByUs) reconnectTimer = setTimeout(connect, 2000);
      };

      socket.onerror = () => socket.close();
    }

    // Connecting after a short delay avoids opening-and-closing a socket when
    // React (in development mode) mounts components twice.
    reconnectTimer = setTimeout(connect, 100);

    return () => {
      closedByUs = true;
      clearTimeout(reconnectTimer);
      clearInterval(pingTimer);
      socket?.close();
    };
  }, []);

  return { connected, latencyMs };
}
