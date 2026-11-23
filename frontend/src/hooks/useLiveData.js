import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api.js";
import { useBackendSocket } from "./useBackendSocket.js";
import { playAlarm } from "../services/alarm.js";

const HISTORY_POINTS = 40; // readings kept per device for the mini charts
const RECENT_READINGS = 15; // rows in the live telemetry table
const RECENT_EVENTS = 30;
const RECENT_ALERTS = 50;

// Loads the current state from the REST API once, then keeps it up to date
// from WebSocket messages. Components just read the returned values.
export function useLiveData() {
  const [devices, setDevices] = useState({}); // device_id -> device
  const [history, setHistory] = useState({}); // device_id -> [reading, ...] oldest first
  const [readings, setReadings] = useState([]); // newest first, all devices
  const [events, setEvents] = useState([]); // newest first
  const [simulation, setSimulation] = useState(null);
  const [mqtt, setMqtt] = useState(null);
  const [network, setNetwork] = useState(null);
  const [alerts, setAlerts] = useState([]); // newest first
  const [toasts, setToasts] = useState([]);
  const [quarantine, setQuarantine] = useState({ active: [], history: [] });
  const [autoQuarantine, setAutoQuarantine] = useState(null);
  const [failover, setFailover] = useState(null); // { status, history }
  const [availability, setAvailability] = useState([]); // [{time, availability}] for the chart (Phase 10)

  const loadFailover = useCallback(() => {
    Promise.all([api.failoverStatus(), api.failoverHistory(20)])
      .then(([status, history]) => setFailover({ status, history: history.events }))
      .catch(() => {});
  }, []);

  const loadQuarantine = useCallback(() => {
    api.quarantineList().then(setQuarantine).catch(() => {});
    api.quarantineSettings().then((s) => setAutoQuarantine(s.auto_quarantine)).catch(() => {});
  }, []);

  const dismissToast = useCallback((id) => setToasts((prev) => prev.filter((t) => t.id !== id)), []);
  const [error, setError] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      const [d, t, e, s, m] = await Promise.all([
        api.devices(),
        api.telemetry(200),
        api.events(RECENT_EVENTS),
        api.simulationStatus(),
        api.mqttStatus(),
      ]);
      setMqtt(m);
      api.networkTopology().then(setNetwork).catch(() => {});
      api.networkStatus().then((n) => setAvailability(n.availability_history)).catch(() => {});
      api.alerts(RECENT_ALERTS).then((a) => setAlerts(a.alerts)).catch(() => {});
      loadQuarantine();
      loadFailover();
      setDevices(Object.fromEntries(d.devices.map((dev) => [dev.device_id, dev])));
      const byDevice = {};
      [...t.telemetry].reverse().forEach((r) => {
        (byDevice[r.device_id] ??= []).push(r);
      });
      Object.keys(byDevice).forEach((id) => {
        byDevice[id] = byDevice[id].slice(-HISTORY_POINTS);
      });
      setHistory(byDevice);
      setReadings(t.telemetry.slice(0, RECENT_READINGS));
      setEvents(e.events);
      setSimulation(s);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const handleMessage = useCallback(
    (message) => {
      const { type, data } = message;
      if (type === "telemetry") {
        const { device, reading } = data;
        setDevices((prev) => ({ ...prev, [device.device_id]: { ...prev[device.device_id], ...device } }));
        setHistory((prev) => ({
          ...prev,
          [device.device_id]: [...(prev[device.device_id] ?? []), reading].slice(-HISTORY_POINTS),
        }));
        setReadings((prev) => [reading, ...prev].slice(0, RECENT_READINGS));
      } else if (type === "device") {
        setDevices((prev) => ({ ...prev, [data.device_id]: { ...prev[data.device_id], ...data } }));
      } else if (type === "device_removed") {
        setDevices((prev) => {
          const next = { ...prev };
          delete next[data.device_id];
          return next;
        });
      } else if (type === "event") {
        setEvents((prev) => [data, ...prev].slice(0, RECENT_EVENTS));
      } else if (type === "simulation") {
        setSimulation(data);
      } else if (type === "mqtt") {
        setMqtt(data);
      } else if (type === "network") {
        setNetwork(data);
        setAvailability((prev) => [...prev, { time: Date.now(), availability: data.availability.current }].slice(-150));
      } else if (type === "alert") {
        setAlerts((prev) => [data, ...prev].slice(0, RECENT_ALERTS));
        const isAttack = !["link_failure", "node_failure", "malformed_message"].includes(data.alert_type);
        if (isAttack && data.severity !== "low") playAlarm(data.severity); // siren on every attack
        if (data.severity === "high" || data.severity === "critical") {
          setToasts((prev) => [...prev, data].slice(-4));
          setTimeout(() => dismissToast(data.id), 7000);
        }
      } else if (type === "quarantine") {
        if (data.action === "quarantined" || data.action === "released") {
          const toast = {
            id: `q-${data.record?.id}-${data.action}`,
            severity: data.action === "quarantined" ? "critical" : "low",
            alert_type: data.action === "quarantined" ? "Device quarantined" : "Device released",
            description:
              data.action === "quarantined"
                ? `${data.device.device_name} (${data.device.device_id}) isolated: ${data.record?.reason}`
                : `${data.device.device_name} (${data.device.device_id}) is back on the network`,
          };
          setToasts((prev) => [...prev, toast].slice(-4));
          setTimeout(() => dismissToast(toast.id), 7000);
        }
        loadQuarantine();
      } else if (type === "failover") {
        loadFailover();
      } else if (type === "alert_update") {
        setAlerts((prev) => prev.map((a) => (a.id === data.id ? data : a)));
      } else if (type === "reset") {
        setHistory({});
        setAvailability([]);
        setReadings([]);
        setEvents([]);
        setAlerts([]);
        setToasts([]);
        loadAll();
      } else if (type === "welcome" || type === "companies_changed") {
        // (re)connected, or (v1.2) a device moved to another company: reload what we may see
        loadAll();
      }
    },
    [loadAll, dismissToast, loadQuarantine, loadFailover]
  );

  const { connected, latencyMs } = useBackendSocket(handleMessage);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // MQTT message counters and failover counters change constantly, so refresh them every few seconds.
  useEffect(() => {
    const timer = setInterval(() => {
      api.mqttStatus().then(setMqtt).catch(() => setMqtt(null));
    }, 5000);
    const timer2 = setInterval(loadFailover, 3000);
    return () => {
      clearInterval(timer);
      clearInterval(timer2);
    };
  }, [loadFailover]);

  return {
    devices, history, readings, events, simulation, mqtt, network, alerts, toasts, dismissToast,
    quarantine, autoQuarantine, setAutoQuarantine, failover, availability, error, connected, latencyMs,
  };
}
