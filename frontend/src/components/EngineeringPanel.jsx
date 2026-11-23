import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { openDeviceViewer } from "./DeviceViewer.jsx";

const HEALTH = { ok: ["Healthy", "tone-ok"], warn: ["Check", "tone-warn"], bad: ["Problem", "tone-bad"] };

function bytes(n) {
  if (n == null) return "—";
  return n > 1e9 ? `${(n / 1e9).toFixed(2)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`;
}

function since(s) {
  if (s == null) return "never";
  if (s < 60) return `${Math.round(s)} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}

function uptime(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

// Platform engineers: where the system runs (PC or cloud container) and the database.
function SystemCard() {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    api.systemInfo().then(setInfo).catch(() => setInfo(null));
    const t = setInterval(() => api.systemInfo().then(setInfo).catch(() => {}), 10000);
    return () => clearInterval(t);
  }, []);
  if (!info) return null;
  const rows = info.database.rows;
  return (
    <section className="panel">
      <div className="panel-head"><h2>System and cloud</h2><span className="muted small">v{info.version}</span></div>
      <div className="kpi-grid">
        <div className="kpi"><span>Runs in</span><b>{info.runs_in}</b><small>{info.os} · Python {info.python}</small></div>
        <div className="kpi"><span>Database</span><b>{info.database.engine}</b><small>{bytes(info.database.size_bytes)}</small></div>
        <div className="kpi"><span>Stored readings</span><b>{(rows.live_readings + rows.archived_readings).toLocaleString()}</b>
          <small>{rows.hourly_summaries.toLocaleString()} hourly summaries</small></div>
        <div className="kpi"><span>Uptime</span><b>{uptime(info.uptime_seconds)}</b><small>{info.websocket_clients} dashboard(s) connected</small></div>
        <div className="kpi"><span>MQTT broker</span><b className={info.mqtt.connected ? "tone-ok" : "tone-warn"}>{info.mqtt.connected ? "Connected" : "Direct"}</b>
          <small>{info.mqtt.host}:{info.mqtt.port}</small></div>
        <div className="kpi"><span>Monitoring</span><b>{info.metrics_endpoint ? "/metrics on" : "/metrics off"}</b>
          <small>Prometheus · summary every {Math.round(info.rollup_every_s / 60)} min</small></div>
      </div>
    </section>
  );
}

// v1.4: device health for field engineers, with reboot, firmware update and maintenance mode.
export default function EngineeringPanel() {
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState(null);
  const [filter, setFilter] = useState("all");
  const { can, isPlatform } = useAuth();

  const load = useCallback(() => api.engineeringDevices().then(setData).catch((e) => setMsg({ ok: false, text: e.message })), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  async function run(promise, ok) {
    try {
      await promise;
      setMsg({ ok: true, text: ok });
      load();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  }

  async function updateAll() {
    const outdated = data.devices.filter((d) => d.firmware !== d.latest_firmware && d.simulated && !d.busy);
    for (const d of outdated) {
      try {
        await api.updateFirmware(d.device_id, d.latest_firmware);
      } catch {
        /* busy or not simulated: skipped */
      }
    }
    setMsg({ ok: true, text: `Updating ${outdated.length} device(s) to ${data.latest_firmware} (simulated, ~10 s each in parallel).` });
    load();
  }

  const devices = data?.devices ?? [];
  const shown = devices.filter((d) => filter === "all" || (filter === "problems" ? d.health !== "ok" : filter === "maintenance" ? d.maintenance : d.firmware !== d.latest_firmware));
  const count = (f) => devices.filter(f).length;

  return (
    <>
      {isPlatform && <SystemCard />}
      <section className="panel">
        <div className="panel-head">
          <h2>Device health</h2>
          <div className="button-row">
            <div className="seg">
              {[["all", `All ${devices.length}`], ["problems", `Need attention ${count((d) => d.health !== "ok")}`],
                ["updates", `Updates ${count((d) => d.firmware !== d.latest_firmware)}`], ["maintenance", `Maintenance ${count((d) => d.maintenance)}`]]
                .map(([k, label]) => <button key={k} className={`seg-btn ${filter === k ? "on" : ""}`} onClick={() => setFilter(k)}>{label}</button>)}
            </div>
            {can("admin") && count((d) => d.firmware !== d.latest_firmware) > 0 && (
              <button className="btn btn-small btn-primary" onClick={updateAll}>⬆ Update all to {data?.latest_firmware}</button>
            )}
          </div>
        </div>
        <div className="table-wrap">
          <table className="table eng-table">
            <thead>
              <tr><th>Device</th><th>Health</th><th>Signal</th><th>Latency</th><th>Loss</th><th>Battery</th><th>Last data</th><th>Firmware</th><th /></tr>
            </thead>
            <tbody>
              {shown.map((d) => {
                const [label, tone] = HEALTH[d.health];
                return (
                  <tr key={d.device_id}>
                    <td><b>{d.device_id}</b><div className="small muted">{d.device_name}</div></td>
                    <td>
                      <span className={tone}>● {label}</span>
                      {d.maintenance && <div className="small tone-warn">maintenance{d.maintenance_by ? ` · ${d.maintenance_by}` : ""}</div>}
                      {d.problems.length > 0 && <div className="small muted">{d.problems.join(", ")}</div>}
                    </td>
                    <td>{d.signal_dbm != null ? <span className={d.signal_dbm < -90 ? "tone-bad" : d.signal_dbm < -80 ? "tone-warn" : ""}>{d.signal_dbm} dBm</span> : "—"}
                      <div className="small muted">{d.access ?? "no link"}{d.mode === "backup" ? " (backup)" : ""}</div></td>
                    <td>{d.latency_ms != null ? `${d.latency_ms} ms` : "—"}</td>
                    <td>{d.packet_loss != null ? `${d.packet_loss} %` : "—"}</td>
                    <td className={d.battery != null && d.battery < 20 ? "tone-bad" : ""}>{d.battery != null ? `${Math.round(d.battery)} %` : "—"}</td>
                    <td>{since(d.last_seen_s)}</td>
                    <td>
                      {d.busy?.action === "firmware" ? <span className="tone-warn">flashing {d.busy.target}…</span> : d.firmware}
                      {d.firmware !== d.latest_firmware && !d.busy && <div className="small tone-warn">→ {d.latest_firmware} available</div>}
                    </td>
                    <td className="eng-actions">
                      <button className="btn btn-small" title="3D model" onClick={() => openDeviceViewer(d.device_id)}>🔍</button>
                      <button className="btn btn-small need-operator" disabled={!!d.busy} title="Reboot (simulated)"
                        onClick={() => run(api.rebootDevice(d.device_id), `${d.device_id} rebooting…`)}>{d.busy?.action === "reboot" ? "…" : "⟳"}</button>
                      {can("admin") && d.firmware !== d.latest_firmware && d.simulated && (
                        <button className="btn btn-small" disabled={!!d.busy} title={`Install ${d.latest_firmware}`}
                          onClick={() => run(api.updateFirmware(d.device_id, d.latest_firmware), `Updating ${d.device_id}…`)}>⬆</button>
                      )}
                      <button className={`btn btn-small need-operator ${d.maintenance ? "btn-primary" : ""}`} title="Maintenance mode: no phone alarm"
                        onClick={() => run(api.setMaintenance(d.device_id, !d.maintenance, d.maintenance ? "" : "Engineering work"),
                          d.maintenance ? `${d.device_id} back in service.` : `${d.device_id} in maintenance: no phone alarm.`)}>🔧</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
      </section>
    </>
  );
}
