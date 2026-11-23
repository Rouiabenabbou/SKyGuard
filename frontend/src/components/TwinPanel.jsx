import { lazy, Suspense, useEffect, useState } from "react";
import { Box, LocateFixed, Maximize2, Minimize2, PenTool, RotateCcw, Tag, X } from "lucide-react";
import { StateButtons } from "./NetworkPanel.jsx";
import { api } from "../services/api.js";
import { NODE_LABELS } from "../three/layout.js";
import { openDeviceViewer } from "./DeviceViewer.jsx";
import DeviceConfigForm from "./DeviceConfigForm.jsx";
import NetworkBuilder from "./NetworkBuilder.jsx";
import { alertLabel } from "./AlertsPanel.jsx";

// Three.js is big, so the 3D scene is loaded only when this panel is shown.
const TwinScene = lazy(() => import("../three/TwinScene.jsx"));

const TONE = { online: "ok", degraded: "warn", offline: "bad", quarantined: "bad", suspicious: "warn", normal: "ok" };

function fmt(value, unit) {
  return value === null || value === undefined ? "—" : `${value}${unit}`;
}

function InspectorTabs({ tabs, active, onChange }) {
  return (
    <div className="seg inspector-tabs" role="tablist">
      {tabs.map(([id, label]) => (
        <button key={id} role="tab" aria-selected={active === id} className={`seg-btn ${active === id ? "on" : ""}`} onClick={() => onChange(id)}>{label}</button>
      ))}
    </div>
  );
}

// Connections of one node, plus (for a device) moving it to another satellite / tower.
function NetworkTab({ node, network, replay }) {
  const [access, setAccess] = useState("");
  const [backup, setBackup] = useState("");
  const [msg, setMsg] = useState(null);
  const links = network.links.filter((l) => l.source_node === node.node_id || l.target_node === node.node_id);
  const sats = network.nodes.filter((n) => n.node_type === "satellite");
  const towers = network.nodes.filter((n) => n.node_type === "base_station");
  const isDevice = node.node_type === "iot_device";

  async function rewire(e) {
    e.preventDefault();
    try {
      await api.rewireDevice(node.node_id, access, backup || undefined);
      setMsg({ ok: true, text: `${node.node_id} now connects through ${access}.` });
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    }
  }

  return (
    <>
      <table className="data-table compact">
        <thead><tr><th>Link</th><th>To</th><th>Role</th><th>Status</th><th>Latency</th></tr></thead>
        <tbody>
          {links.map((l) => (
            <tr key={l.link_id}>
              <td className="mono">{l.link_id}</td>
              <td>{l.source_node === node.node_id ? l.target_node : l.source_node}</td>
              <td>{l.is_active_path ? "primary" : "backup"}</td>
              <td className={`tone-${TONE[l.status] ?? "neutral"}`}>{l.status}</td>
              <td>{l.latency_ms} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!isDevice && !replay && (
        <StateButtons current={node.status === "online" ? null : node.status}
          onSet={(s) => api.setNodeState(node.node_id, s).then(() => setMsg(null)).catch((e) => setMsg({ ok: false, text: e.message }))} />
      )}
      {isDevice && !replay && (
        <form className="config-form need-admin need-platform" onSubmit={rewire}>
          <label><span>Connect through</span>
            <select value={access} onChange={(e) => setAccess(e.target.value)} required>
              <option value="">choose…</option>
              <optgroup label="Satellite">{sats.map((s) => <option key={s.node_id} value={s.node_id}>{s.node_id} · {s.name}</option>)}</optgroup>
              <optgroup label="5G base station">{towers.map((t) => <option key={t.node_id} value={t.node_id}>{t.node_id} · {t.name}</option>)}</optgroup>
            </select>
          </label>
          {sats.some((s) => s.node_id === access) && (
            <label><span>Backup 5G tower</span>
              <select value={backup} onChange={(e) => setBackup(e.target.value)}>
                <option value="">BS-5G (default)</option>
                {towers.map((t) => <option key={t.node_id} value={t.node_id}>{t.node_id}</option>)}
              </select>
            </label>
          )}
          <div className="config-actions"><button className="btn btn-small btn-primary" disabled={!access}>Re-wire device</button></div>
        </form>
      )}
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </>
  );
}

// Alerts and incidents of one device (only what this user may see).
function SecurityTab({ deviceId, alerts }) {
  const [incidents, setIncidents] = useState(null);
  useEffect(() => {
    api.incidents().then((r) => setIncidents(r.incidents.filter((i) => i.device_id === deviceId))).catch(() => setIncidents([]));
  }, [deviceId]);
  const mine = alerts.filter((a) => a.device_id === deviceId).slice(0, 8);
  return (
    <>
      <div className="section-label">Recent alerts</div>
      {mine.length === 0 ? <div className="muted small">No alerts for this device.</div> : (
        <ul className="mini-list">
          {mine.map((a) => (
            <li key={a.id}>
              <span className={`sev sev-${a.severity}`}>{a.severity}</span>
              <span>{alertLabel(a.alert_type)}</span>
              <span className="muted small push-right">{a.status} · {new Date(a.timestamp).toLocaleTimeString()}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="section-label">Incidents</div>
      {incidents == null ? <div className="muted small">Loading…</div> : incidents.length === 0 ? <div className="muted small">No incidents.</div> : (
        <ul className="mini-list">
          {incidents.map((i) => (
            <li key={i.id}><a href="#incidents">#{i.id} {i.title}</a><span className="muted small push-right">{i.status}</span></li>
          ))}
        </ul>
      )}
    </>
  );
}

function DeviceInspector({ node, device, route, replay, network, alerts, onFocus }) {
  const [tab, setTab] = useState("overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => setTab("overview"), [node.node_id]);
  const run = (promise) => {
    setBusy(true);
    promise.then(() => setError(null)).catch((e) => setError(e.message)).finally(() => setBusy(false));
  };
  const quarantined = device?.security_status === "quarantined";
  return (
    <div className="details">
      <h3>{device?.device_name ?? node.name}</h3>
      <div className="muted small">{node.node_id} · {device?.device_type ?? "IoT device"} · {device?.location}</div>
      <div className="button-row">
        <button className="btn btn-small" onClick={onFocus}><LocateFixed size={14} /> Zoom to</button>
        <button className="btn btn-small" onClick={() => openDeviceViewer(node.node_id)}><Box size={14} /> 3D model</button>
      </div>
      <InspectorTabs tabs={[["overview", "Overview"], ["security", "Security"], ["network", "Network"], ...(replay ? [] : [["config", "Configure"]])]} active={tab} onChange={setTab} />
      {tab === "overview" && (
        <>
          <dl>
            <dt>Status</dt><dd className={`tone-${TONE[node.status] ?? "neutral"}`}>{node.status}</dd>
            <dt>Security</dt><dd className={`tone-${TONE[device?.security_status] ?? "neutral"}`}>{device?.security_status ?? "—"}</dd>
            <dt>Temperature</dt><dd>{fmt(device?.temperature, " °C")}</dd>
            <dt>Humidity</dt><dd>{fmt(device?.humidity, " %")}</dd>
            <dt>Battery</dt><dd>{fmt(device?.battery, " %")}</dd>
            <dt>Messages</dt><dd>{device?.message_count ?? "—"}</dd>
            <dt>Route</dt>
            <dd>{route?.connected ? route.path.join(" → ") : route?.quarantined ? "blocked (quarantine)" : "no route to core"}</dd>
            {route?.connected && (
              <>
                <dt>Access</dt><dd>{route.access}{route.mode === "backup" ? " (backup path)" : ""}</dd>
                <dt>Path latency</dt><dd className={route.degraded ? "tone-warn" : ""}>{route.latency_ms} ms</dd>
              </>
            )}
          </dl>
          {!replay && (
            <div className="button-row">
              {quarantined || device?.security_status === "suspicious" ? (
                <button className="btn btn-small need-operator" disabled={busy} onClick={() => run(api.releaseDevice(node.node_id))}>
                  {quarantined ? "Release" : "Mark safe"}
                </button>
              ) : (
                <button className="btn btn-small btn-danger need-operator" disabled={busy} onClick={() => run(api.quarantineDevice(node.node_id, "manual quarantine from 3D twin"))}>
                  Quarantine
                </button>
              )}
              <button className="btn btn-small need-operator" disabled={busy} title="Blinks the LED of a real ESP32" onClick={() => run(api.deviceCommand(node.node_id, "identify"))}>
                Identify
              </button>
            </div>
          )}
        </>
      )}
      {tab === "security" && <SecurityTab deviceId={node.node_id} alerts={alerts} />}
      {tab === "network" && <NetworkTab node={node} network={network} replay={replay} />}
      {tab === "config" && (device
        ? <div className="need-admin"><DeviceConfigForm key={node.node_id} device={device} onClose={() => setTab("overview")} /></div>
        : <div className="muted small">No device data yet.</div>)}
      {tab === "config" && <div className="muted small only-below-admin">Only an admin can change the configuration.</div>}
      {error && <div className="tone-bad small">{error}</div>}
    </div>
  );
}

function InfraInspector({ node, network, replay, onFocus }) {
  const [tab, setTab] = useState("network");
  return (
    <div className="details">
      <h3>{node.name}</h3>
      <div className="muted small">{node.node_id} · {NODE_LABELS[node.node_type] ?? node.node_type} · <span className={`tone-${TONE[node.status] ?? "neutral"}`}>{node.status}</span></div>
      <div className="button-row">
        <button className="btn btn-small" onClick={onFocus}><LocateFixed size={14} /> Zoom to</button>
        <button className="btn btn-small" onClick={() => openDeviceViewer(node.node_id)}><Box size={14} /> 3D model</button>
      </div>
      <InspectorTabs tabs={[["network", "Links and state"], ["devices", "Devices served"]]} active={tab} onChange={setTab} />
      {tab === "network" && <NetworkTab node={node} network={network} replay={replay} />}
      {tab === "devices" && (
        <ul className="mini-list">
          {Object.entries(network.routes ?? {}).filter(([, r]) => (r.path ?? []).includes(node.node_id)).map(([id, r]) => (
            <li key={id}><span className="mono">{id}</span><span className="muted small push-right">{r.mode} · {r.latency_ms} ms</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Legend() {
  return (
    <div className="legend small">
      <span><i className="sw sw-traffic" /> traffic flowing</span>
      <span><i className="sw sw-degraded" /> degraded link</span>
      <span><i className="sw sw-offline" /> link down</span>
      <span><i className="sw sw-backup" /> standby / backup link</span>
      <span>red cage = quarantined device</span>
      <span className="muted">Scroll to zoom where the mouse points · right-drag to move · click a node to inspect it</span>
    </div>
  );
}

// The 3D digital twin panel: scene on the left, inspector on the right.
export default function TwinPanel({ network, devices, alerts = [], replay = false, title = "3D digital twin", children }) {
  const [selectedId, setSelectedId] = useState(null);
  const [showLabels, setShowLabels] = useState(true);
  const [viewKey, setViewKey] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [designing, setDesigning] = useState(false);
  const [focus, setFocus] = useState(null);
  const node = network?.nodes.find((n) => n.node_id === selectedId);
  const zoomTo = (id) => setFocus({ id, t: Date.now() });

  useEffect(() => {
    if (!expanded) return undefined;
    const onKey = (e) => e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  return (
    <section className={`panel twin-panel ${expanded ? "twin-expanded" : ""}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        <div className="button-row">
          <label className="switch small">
            <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /> <Tag size={13} /> Labels
          </label>
          <button className="btn btn-small" onClick={() => { setViewKey((k) => k + 1); setFocus(null); }}><RotateCcw size={14} /> Reset view</button>
          {!replay && (
            <button className={`btn btn-small need-admin need-platform ${designing ? "btn-primary" : ""}`} onClick={() => setDesigning((d) => !d)}>
              <PenTool size={14} /> Design network
            </button>
          )}
          <button className="btn btn-small" onClick={() => setExpanded((x) => !x)} title={expanded ? "Exit full screen (Esc)" : "Full screen"}>
            {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />} {expanded ? "Exit" : "Full screen"}
          </button>
        </div>
      </div>
      <div className="twin-layout">
        <div className="twin-canvas">
          {network ? (
            <Suspense fallback={<div className="twin-fallback">Loading 3D scene…</div>}>
              <TwinScene key={viewKey} network={network} devices={devices} selectedId={selectedId} onSelect={setSelectedId} showLabels={showLabels} focus={focus} />
            </Suspense>
          ) : (
            <div className="twin-fallback">Waiting for network data…</div>
          )}
          {replay && <div className="twin-badge">REPLAY</div>}
        </div>
        <div className="network-side">
          {node ? (
            <>
              <button className="icon-btn inspector-close" aria-label="Close" onClick={() => setSelectedId(null)}><X size={16} /></button>
              {node.node_type === "iot_device" ? (
                <DeviceInspector node={node} device={devices[node.node_id]} route={network.routes[node.node_id]} replay={replay}
                                 network={network} alerts={alerts} onFocus={() => zoomTo(node.node_id)} />
              ) : (
                <InfraInspector node={node} network={network} replay={replay} onFocus={() => zoomTo(node.node_id)} />
              )}
            </>
          ) : (
            <Legend />
          )}
        </div>
      </div>
      {designing && !replay && (
        <div className="twin-design">
          <div className="small muted">
            Changes appear in the twin at once. For a drag-and-drop editor use <a href="#topology">Network Topology</a>.
          </div>
          <NetworkBuilder network={network} />
        </div>
      )}
      {children}
    </section>
  );
}
