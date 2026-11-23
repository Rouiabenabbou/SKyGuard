import { useEffect, useMemo, useState } from "react";
import { Box, Plus, Search, X } from "lucide-react";
import DeviceCard from "../components/DeviceCard.jsx";
import AddDeviceForm from "../components/AddDeviceForm.jsx";
import { SourceBadge } from "./AlertCenter.jsx";
import { openDeviceViewer } from "../components/DeviceViewer.jsx";
import { alertLabel } from "../components/AlertsPanel.jsx";

const SEC_TONE = { normal: "ok", suspicious: "warn", quarantined: "bad" };
const seen = (iso, now) => {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3600)} h`;
};

// v2.0 IoT Asset Management: the device inventory with filters; select a device to see
// its live card (configure, quarantine, 3D model) and its recent alerts.
export default function IotAssets({ devices, history, network, alerts, quarantine, now, subId, onNavigate }) {
  const [q, setQ] = useState("");
  const [sec, setSec] = useState("");
  const [conn, setConn] = useState("");
  const [adding, setAdding] = useState(false);
  const selected = subId && devices[subId] ? subId : null;
  const list = useMemo(() => Object.values(devices).sort((a, b) => a.device_id.localeCompare(b.device_id)), [devices]);
  const openByDevice = useMemo(() => {
    const m = {};
    alerts.filter((a) => a.status === "open" && a.device_id).forEach((a) => { m[a.device_id] = (m[a.device_id] ?? 0) + 1; });
    return m;
  }, [alerts]);
  const n = q.trim().toLowerCase();
  const shown = list.filter((d) =>
    (!n || `${d.device_id} ${d.device_name} ${d.device_type} ${d.location} ${d.company_name ?? ""}`.toLowerCase().includes(n)) &&
    (!sec || d.security_status === sec) && (!conn || d.connection_type === conn));
  const counts = { online: list.filter((d) => d.status === "online").length, suspicious: list.filter((d) => d.security_status === "suspicious").length,
    quarantined: list.filter((d) => d.security_status === "quarantined").length, lab: list.filter((d) => d.simulated === false).length };
  const dev = selected ? devices[selected] : null;
  useEffect(() => setAdding(false), [selected]);

  return (
    <div className={selected || adding ? "grid-main-side" : ""}>
      <section className="panel">
        <div className="panel-head">
          <h2>Device inventory <span className="muted small">{list.length} devices · {counts.online} online · {counts.suspicious} suspicious · {counts.quarantined} quarantined · {counts.lab} lab</span></h2>
          <button className="btn btn-small btn-primary need-admin" onClick={() => { setAdding(true); onNavigate("devices"); }}><Plus size={13} /> Add device</button>
        </div>
        <div className="filter-bar">
          <div className="global-search" style={{ width: "auto", flex: 1, maxWidth: 340 }}>
            <Search size={14} />
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID, name, type, place…" />
          </div>
          <select value={sec} onChange={(e) => setSec(e.target.value)} aria-label="Security state">
            <option value="">Any security state</option><option value="normal">normal</option><option value="suspicious">suspicious</option><option value="quarantined">quarantined</option>
          </select>
          <select value={conn} onChange={(e) => setConn(e.target.value)} aria-label="Connection">
            <option value="">Satellite + 5G</option><option value="satellite">satellite</option><option value="5g">5G</option>
          </select>
        </div>
        <div className="table-wrap" style={{ maxHeight: 640 }}>
          <table className="data-table">
            <thead><tr><th>Device</th><th>Type</th><th>Access</th><th>Status</th><th>Security</th><th>Alerts</th><th>Battery</th><th>Last seen</th><th>Src</th></tr></thead>
            <tbody>
              {shown.map((d) => {
                const route = network?.routes?.[d.device_id];
                return (
                  <tr key={d.device_id} className={`clickable ${selected === d.device_id ? "on" : ""}`} onClick={() => onNavigate(`devices/${d.device_id}`)}>
                    <td><div className="mono">{d.device_id}</div><div className="small muted">{d.device_name}</div></td>
                    <td className="small">{d.device_type}</td>
                    <td className="small">{d.connection_type} · {route?.path?.[1] ?? "—"}{route?.mode === "backup" ? " (backup)" : ""}</td>
                    <td className={d.status === "online" ? "tone-ok" : "tone-bad"}>{d.status}</td>
                    <td className={`tone-${SEC_TONE[d.security_status] ?? "neutral"}`}>{d.security_status}</td>
                    <td>{openByDevice[d.device_id] ? <span className="tone-bad">{openByDevice[d.device_id]} open</span> : <span className="muted">0</span>}</td>
                    <td>{d.battery != null ? `${Math.round(d.battery)}%` : "—"}</td>
                    <td className="small">{seen(d.last_seen, now)}</td>
                    <td><SourceBadge source={d.simulated === false ? "lab" : "simulation"} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {shown.length === 0 && <div className="empty">No device matches.</div>}
        </div>
      </section>

      {adding && !selected && (
        <section className="panel">
          <div className="panel-head"><h2>Add device</h2><button className="icon-btn" aria-label="Close" onClick={() => setAdding(false)}><X size={16} /></button></div>
          <AddDeviceForm network={network} onClose={() => setAdding(false)} />
        </section>
      )}

      {dev && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
          <div className="button-row" style={{ justifyContent: "space-between" }}>
            <button className="btn btn-small" onClick={() => openDeviceViewer(dev.device_id)}><Box size={13} /> 3D model</button>
            <button className="icon-btn" aria-label="Close" onClick={() => onNavigate("devices")}><X size={16} /></button>
          </div>
          <DeviceCard device={dev} history={history[dev.device_id] ?? []} now={now}
                      quarantineRecord={quarantine.active.find((r) => r.device_id === dev.device_id)} />
          <section className="panel">
            <h2>Recent alerts</h2>
            <ul className="mini-list">
              {alerts.filter((a) => a.device_id === dev.device_id).slice(0, 10).map((a) => (
                <li key={a.id}><span className={`sev sev-${a.severity}`}>{a.severity}</span><a href={`#alerts/${a.id}`}>#{a.id} {alertLabel(a.alert_type)}</a>
                  <span className="muted small push-right">{a.status}</span></li>
              ))}
            </ul>
            {!alerts.some((a) => a.device_id === dev.device_id) && <div className="empty">No alerts.</div>}
          </section>
        </div>
      )}
    </div>
  );
}
