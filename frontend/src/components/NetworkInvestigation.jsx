import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { alertLabel } from "./AlertsPanel.jsx";
import { openDeviceViewer } from "./DeviceViewer.jsx";
import { axis, SEVERITY_COLORS, tooltip } from "./charts/theme.js";

// v1.5: an investigation graph of the whole system, like a security investigation tool.
// Assets (network equipment, IoT devices, companies) and observables (alert types,
// unknown device IDs) are nodes; network links, ownership and alerts are edges.
// A platform admin can rebuild the network here (edit mode): add equipment, connect
// or remove links, and move a device to another satellite / tower. All simulated.

export const DISPOSITIONS = {
  malicious: { label: "Malicious", color: "#dc2626" },
  suspicious: { label: "Suspicious", color: "#d97706" },
  common: { label: "Common", color: "#7c3aed" },
  unknown: { label: "Unknown", color: "#94a3b8" },
  clean: { label: "Clean", color: "#16a34a" },
  asset: { label: "Asset", color: "#0284c7" },
};

const KINDS = {
  satellite: { label: "Satellites", icon: "🛰️", tier: 3 },
  base_station: { label: "5G base stations", icon: "🗼", tier: 3 },
  ground_station: { label: "Ground stations", icon: "📡", tier: 4 },
  core: { label: "Core network", icon: "🖧", tier: 5 },
  security_server: { label: "Security servers", icon: "🛡️", tier: 5 },
  iot_device: { label: "IoT devices", icon: "🔹", tier: 2 },
  company: { label: "Companies", icon: "🏢", tier: 0 },
  observable: { label: "Alert types", icon: "⚠️", tier: 1 },
  unknown_device: { label: "Unknown device IDs", icon: "❓", tier: 1 },
};
const KIND_ORDER = ["satellite", "ground_station", "base_station", "core", "security_server", "iot_device", "company", "observable", "unknown_device"];
const SOURCES = { all: "All sources", rules: "Detection rules", ml: "Machine learning", network: "Network faults" };
const NEW_NODE = { satellite: "Satellite", ground_station: "Ground station", base_station: "5G tower" };
const R = 17;
const COL = 210;
const ROW = 62;
const MAX_ROWS = 10;
const SUB_COL = 120;

// ----------------------------------------------------------------- layouts
function layered(nodes, edges) {
  const tiers = {};
  nodes.forEach((n) => (tiers[KINDS[n.kind]?.tier ?? 1] ??= []).push(n));
  const owner = Object.fromEntries(edges.filter((e) => e.kind === "owns").map((e) => [e.target, e.source]));
  const pos = {};
  let x = 0;
  Object.keys(tiers).map(Number).sort((a, b) => a - b).forEach((t) => {
    const list = tiers[t];
    list.sort((a, b) => (owner[a.id] ?? "~").localeCompare(owner[b.id] ?? "~") || a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id));
    // a long tier (e.g. 30 devices) is split into a few columns, so the graph stays readable
    const cols = Math.ceil(list.length / MAX_ROWS);
    const rows = Math.ceil(list.length / cols);
    list.forEach((n, i) => {
      const c = Math.floor(i / rows);
      const r = i % rows;
      pos[n.id] = { x: x + c * SUB_COL, y: (r - (rows - 1) / 2) * ROW + (c % 2) * (ROW / 2) };
    });
    x += (cols - 1) * SUB_COL + COL;
  });
  return pos;
}

function radial(nodes, edges) {
  const adj = {};
  edges.forEach((e) => {
    (adj[e.source] ??= []).push(e.target);
    (adj[e.target] ??= []).push(e.source);
  });
  const start = nodes.find((n) => n.kind === "core")?.id ?? nodes[0]?.id;
  const depth = { [start]: 0 };
  const queue = [start];
  while (queue.length) {
    const id = queue.shift();
    for (const nx of adj[id] ?? []) if (depth[nx] == null) { depth[nx] = depth[id] + 1; queue.push(nx); }
  }
  const rings = {};
  nodes.forEach((n) => (rings[depth[n.id] ?? 6] ??= []).push(n));
  const pos = {};
  Object.entries(rings).forEach(([d, list]) => {
    list.sort((a, b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id));
    const r = Number(d) * 150;
    list.forEach((n, i) => {
      const a = (i / list.length) * Math.PI * 2 + Number(d) * 0.4;
      pos[n.id] = { x: r * Math.cos(a), y: r * Math.sin(a) };
    });
  });
  return pos;
}

function force(nodes, edges) {
  const pos = layered(nodes, edges);
  const ids = nodes.map((n) => n.id);
  const P = ids.map((id) => ({ ...pos[id] }));
  const index = Object.fromEntries(ids.map((id, i) => [id, i]));
  const springs = edges.filter((e) => index[e.source] != null && index[e.target] != null).map((e) => [index[e.source], index[e.target]]);
  for (let it = 0; it < 260; it++) {
    const F = P.map(() => ({ x: 0, y: 0 }));
    for (let i = 0; i < P.length; i++) {
      for (let j = i + 1; j < P.length; j++) {
        let dx = P[i].x - P[j].x;
        let dy = P[i].y - P[j].y;
        const d2 = Math.max(dx * dx + dy * dy, 100);
        const f = 14000 / d2;
        const d = Math.sqrt(d2);
        dx /= d;
        dy /= d;
        F[i].x += dx * f; F[i].y += dy * f; F[j].x -= dx * f; F[j].y -= dy * f;
      }
    }
    for (const [a, b] of springs) {
      const dx = P[b].x - P[a].x;
      const dy = P[b].y - P[a].y;
      const d = Math.max(Math.hypot(dx, dy), 1);
      const f = (d - 125) * 0.04;
      F[a].x += (dx / d) * f; F[a].y += (dy / d) * f; F[b].x -= (dx / d) * f; F[b].y -= (dy / d) * f;
    }
    const cool = 1 - it / 260;
    P.forEach((p, i) => {
      p.x += Math.max(-30, Math.min(30, F[i].x - p.x * 0.004)) * cool;
      p.y += Math.max(-30, Math.min(30, F[i].y - p.y * 0.004)) * cool;
    });
  }
  return Object.fromEntries(ids.map((id, i) => [id, { x: Math.round(P[i].x), y: Math.round(P[i].y) }]));
}

const LAYOUTS = { force: "Force", layered: "Layered", radial: "Radial" };
const LAYOUT_FN = { layered, force, radial };

// ------------------------------------------------------------------- parts
function NodeShape({ n, selected, dim, onPointerDown }) {
  const color = DISPOSITIONS[n.disposition]?.color ?? "#94a3b8";
  const down = n.status === "offline" || n.status === "degraded";
  const label = (n.kind === "observable" ? alertLabel(n.alert_type) : n.kind === "iot_device" || n.kind === "unknown_device" ? n.id : n.label) ?? n.id;
  const short = label.length > 22 ? `${label.slice(0, 21)}…` : label;
  return (
    <g className={`ig-node ${dim ? "dim" : ""} ${selected ? "on" : ""}`} transform={`translate(${n.x},${n.y})`} onPointerDown={onPointerDown}>
      {selected && <circle r={R + 7} className="ig-select" />}
      {n.kind === "observable" || n.kind === "unknown_device" ? (
        <rect x={-R + 2} y={-R + 2} width={(R - 2) * 2} height={(R - 2) * 2} rx="4" transform="rotate(45)" fill={`${color}22`} stroke={color} strokeWidth="2" />
      ) : n.kind === "company" ? (
        <rect x={-R} y={-R} width={R * 2} height={R * 2} rx="7" fill={`${color}22`} stroke={color} strokeWidth="2" />
      ) : (
        <circle r={R} fill={`${color}22`} stroke={down ? "#dc2626" : color} strokeWidth="2" strokeDasharray={down ? "4 3" : undefined} />
      )}
      <text className="ig-icon" textAnchor="middle" dy="5">{KINDS[n.kind]?.icon ?? "●"}</text>
      {n.kind === "observable" && n.count > 0 && (
        <g transform={`translate(${R - 2},${-R + 2})`}>
          <circle r="8" fill={color} />
          <text className="ig-badge" textAnchor="middle" dy="3.5">{n.count > 99 ? "99+" : n.count}</text>
        </g>
      )}
      <text className="ig-label" textAnchor="middle" y={R + 14}>{short}</text>
    </g>
  );
}

function edgeClass(e) {
  if (e.kind === "owns") return "ig-edge owns";
  if (e.kind === "alert") return "ig-edge alert";
  if (e.status === "offline") return "ig-edge link off";
  return `ig-edge link ${e.primary ? "primary" : "backup"} ${e.in_use ? "use" : ""} ${e.status === "degraded" ? "deg" : ""}`;
}

function Legend() {
  return (
    <div className="ig-legend">
      {Object.entries(DISPOSITIONS).map(([k, d]) => (
        <span key={k}><i style={{ background: d.color }} />{d.label}</span>
      ))}
      <span className="muted">── primary · ‑ ‑ backup · ⟶ alert</span>
    </div>
  );
}

function AssetList({ nodes, selected, onPick }) {
  const groups = KIND_ORDER.map((k) => [k, nodes.filter((n) => n.kind === k)]).filter(([, l]) => l.length);
  return (
    <div className="ig-side">
      <h3>Assets and observables <span className="muted">{nodes.length}</span></h3>
      {groups.map(([k, list]) => (
        <details key={k} open={list.length <= 6}>
          <summary>{KINDS[k].icon} {KINDS[k].label} <b>{list.length}</b></summary>
          <ul>
            {list.map((n) => (
              <li key={n.id} className={selected === n.id ? "on" : ""} onClick={() => onPick(n.id)}>
                <i style={{ background: DISPOSITIONS[n.disposition]?.color }} />
                {n.kind === "observable" ? `${alertLabel(n.alert_type)} (${n.count})` : n.kind === "iot_device" ? `${n.id} · ${n.label}` : n.label}
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

function Details({ node, edge, data, editing, onPick, onChanged, setMsg }) {
  const [access, setAccess] = useState("");
  const [backup, setBackup] = useState("");
  useEffect(() => { setAccess(""); setBackup(""); }, [node?.id]);
  const nodesById = useMemo(() => Object.fromEntries(data.nodes.map((n) => [n.id, n])), [data.nodes]);

  const run = async (promise, text) => {
    try {
      await promise;
      setMsg({ ok: true, text });
      onChanged();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  };

  if (edge) {
    return (
      <div className="ig-side">
        <h3>Link {edge.id}</h3>
        <table className="spec-table"><tbody>
          <tr><td>From → to</td><td>{edge.source} → {edge.target}</td></tr>
          <tr><td>Type</td><td>{edge.link_type} · {edge.primary ? "primary" : "backup"}</td></tr>
          <tr><td>Status</td><td>{edge.status}{edge.in_use ? " · carrying traffic" : ""}</td></tr>
          <tr><td>Latency</td><td>{edge.latency_ms} ms</td></tr>
        </tbody></table>
        {editing && (edge.removable
          ? <button className="btn btn-small btn-danger" onClick={() => run(api.removeLink(edge.id), `Link ${edge.id} removed.`)}>Remove link</button>
          : <div className="small muted">Original link: it can't be removed, but you can set it offline in the Network tab.</div>)}
      </div>
    );
  }

  if (!node) {
    return (
      <div className="ig-side">
        <h3>Indicators <span className="muted">{data.indicators.length}</span></h3>
        {data.indicators.length === 0 && <div className="small muted">No alerts in this period.</div>}
        <ul className="ig-indicators">
          {data.indicators.map((i) => (
            <li key={i.alert_type} onClick={() => onPick(`OBS:${i.alert_type}`)}>
              <div><i style={{ background: DISPOSITIONS[i.disposition]?.color }} /><b>{alertLabel(i.alert_type)}</b></div>
              <div className="small muted">{SOURCES[i.source]} · {i.count} alerts{i.open ? `, ${i.open} open` : ""} · {i.devices.length} device(s)</div>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const neighbours = data.edges.filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => nodesById[e.source === node.id ? e.target : e.source]).filter(Boolean);
  const sats = data.nodes.filter((n) => n.kind === "satellite");
  const towers = data.nodes.filter((n) => n.kind === "base_station");
  const disp = DISPOSITIONS[node.disposition];
  return (
    <div className="ig-side">
      <h3>{KINDS[node.kind]?.icon} {node.kind === "observable" ? alertLabel(node.alert_type) : node.label}</h3>
      <span className="status-chip" style={{ "--chip": disp?.color }}>{disp?.label}</span>
      <table className="spec-table"><tbody>
        <tr><td>ID</td><td>{node.id}</td></tr>
        <tr><td>Type</td><td>{KINDS[node.kind]?.label.replace(/s$/, "")}{node.device_type ? ` · ${node.device_type}` : ""}</td></tr>
        {node.kind !== "observable" && node.kind !== "company" && <tr><td>Status</td><td>{node.status}{node.security && node.security !== "normal" ? ` · ${node.security}` : ""}</td></tr>}
        {node.place && <tr><td>Place</td><td>{node.place}</td></tr>}
        {node.kind === "iot_device" && <tr><td>Route</td><td>{node.route?.length ? node.route.join(" → ") : "no route"}{node.route_mode ? ` (${node.route_mode})` : ""}</td></tr>}
        {node.kind === "iot_device" && <tr><td>Open alerts</td><td>{node.open_alerts}</td></tr>}
        {node.temperature != null && <tr><td>Temperature</td><td>{node.temperature.toFixed?.(1)} °C</td></tr>}
        {node.kind === "observable" && <tr><td>Alerts</td><td>{node.count} ({node.open} open) · {SOURCES[node.source]}</td></tr>}
        {node.last_seen && <tr><td>Last seen</td><td>{new Date(node.last_seen).toLocaleString()}</td></tr>}
      </tbody></table>
      <div className="small muted">Connected to</div>
      <div className="ig-chips">
        {neighbours.map((n) => <button key={n.id} className="link-btn" onClick={() => onPick(n.id)}>{n.kind === "observable" ? alertLabel(n.alert_type) : n.id}</button>)}
      </div>
      <div className="button-row">
        {node.kind === "iot_device" && <button className="btn btn-small" onClick={() => openDeviceViewer(node.id)}>3D model</button>}
        {node.kind === "iot_device" && <a className="btn btn-small" href="#incidents">Incidents</a>}
        {editing && node.removable && (
          <button className="btn btn-small btn-danger" onClick={() => run(api.removeNode(node.id), `${node.id} removed with its links.`)}>Remove</button>
        )}
      </div>
      {editing && node.kind === "iot_device" && (
        <form className="ig-rewire" onSubmit={(e) => {
          e.preventDefault();
          run(api.rewireDevice(node.id, access, backup || undefined), `${node.id} now connects through ${access}.`);
        }}>
          <div className="small muted">Connect this device through</div>
          <select value={access} onChange={(e) => setAccess(e.target.value)} required>
            <option value="">choose…</option>
            <optgroup label="Satellite">{sats.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}</optgroup>
            <optgroup label="5G tower">{towers.map((t) => <option key={t.id} value={t.id}>{t.id}</option>)}</optgroup>
          </select>
          {sats.some((s) => s.id === access) && (
            <select value={backup} onChange={(e) => setBackup(e.target.value)}>
              <option value="">backup: BS-5G</option>
              {towers.map((t) => <option key={t.id} value={t.id}>backup: {t.id}</option>)}
            </select>
          )}
          <button className="btn btn-small btn-primary" disabled={!access}>Re-wire</button>
        </form>
      )}
    </div>
  );
}

function Timeline({ data }) {
  const rows = data.timeline.map((b) => ({ ...b, ms: Date.parse(b.t) }));
  return (
    <div className="ig-timeline">
      <div className="small muted">Timeline · alerts per hour, last {data.hours} h</div>
      <ResponsiveContainer width="100%" height={110}>
        <BarChart data={rows} margin={{ top: 6, right: 8, left: -24, bottom: 0 }}>
          <XAxis dataKey="ms" type="category" {...axis} tickFormatter={(ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit" })} interval="preserveStartEnd" minTickGap={24} />
          <YAxis {...axis} allowDecimals={false} width={44} />
          <Tooltip {...tooltip} cursor={{ fill: "rgba(148,163,184,0.12)" }} labelFormatter={(ms) => new Date(ms).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })} />
          {["low", "medium", "high", "critical"].map((s) => <Bar key={s} dataKey={s} stackId="a" fill={SEVERITY_COLORS[s]} isAnimationActive={false} />)}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// -------------------------------------------------------------------- main
export default function NetworkInvestigation() {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [hours, setHours] = useState(24);
  const [pos, setPos] = useState({});
  const [saved, setSaved] = useState(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 0.6 });
  const [selected, setSelected] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [layout, setLayout] = useState("force");
  const [search, setSearch] = useState("");
  const [disposition, setDisposition] = useState("all");
  const [source, setSource] = useState("all");
  const [affectedOnly, setAffectedOnly] = useState(false);
  const [hide, setHide] = useState({ company: false, observable: false, backup: false });
  const [editing, setEditing] = useState(false);
  const [connectFrom, setConnectFrom] = useState(null);
  const [pendingLink, setPendingLink] = useState(null);
  const [newNode, setNewNode] = useState(null);
  const [msg, setMsg] = useState(null);
  const box = useRef(null);
  const drag = useRef(null);
  const fitted = useRef(false);

  const load = useCallback(() => api.graph(hours).then(setData).catch((e) => setMsg({ ok: false, text: e.message })), [hours]);
  useEffect(() => {
    load();
    api.graphLayout().then((r) => setSaved(r.positions ?? {})).catch(() => setSaved({}));
  }, [load]);
  useEffect(() => {
    const t = setInterval(() => { if (!drag.current) load(); }, 10000);
    return () => clearInterval(t);
  }, [load]);

  // Positions: saved ones first, then the chosen layout for new nodes.
  useEffect(() => {
    if (!data || saved == null) return;
    setPos((old) => {
      const missing = data.nodes.filter((n) => !old[n.id]);
      if (!missing.length) return old;
      const computed = LAYOUT_FN[layout](data.nodes, data.edges);
      const out = { ...old };
      for (const n of missing) out[n.id] = saved[n.id] ? { x: saved[n.id][0], y: saved[n.id][1] } : computed[n.id];
      return out;
    });
  }, [data, saved, layout]);

  const editable = !!data?.can_edit && can("admin");

  // What is shown after the filters.
  const shown = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    let nodes = data.nodes.filter((n) => !hide[n.kind] && !(hide.observable && n.kind === "unknown_device"));
    if (source !== "all") nodes = nodes.filter((n) => n.kind !== "observable" || n.source === source);
    if (affectedOnly) {
      const bad = new Set(data.nodes.filter((n) => n.kind === "iot_device" && ["malicious", "suspicious"].includes(n.disposition)).map((n) => n.id));
      const keep = new Set(bad);
      data.nodes.forEach((n) => { if (bad.has(n.id)) (n.route ?? []).forEach((r) => keep.add(r)); });
      data.edges.forEach((e) => { if (e.kind !== "link" && (bad.has(e.source) || bad.has(e.target))) { keep.add(e.source); keep.add(e.target); } });
      nodes = nodes.filter((n) => keep.has(n.id));
    }
    const ids = new Set(nodes.map((n) => n.id));
    const edges = data.edges.filter((e) => ids.has(e.source) && ids.has(e.target) && !(hide.backup && e.kind === "link" && !e.primary && !e.in_use));
    return { nodes: nodes.filter((n) => pos[n.id]).map((n) => ({ ...n, ...pos[n.id] })), edges };
  }, [data, pos, hide, source, affectedOnly]);

  const q = search.trim().toLowerCase();
  const isDim = (n) =>
    (q && !`${n.id} ${n.label} ${n.alert_type ?? ""} ${n.device_type ?? ""}`.toLowerCase().includes(q)) ||
    (disposition !== "all" && n.disposition !== disposition);

  // --------------------------------------------------------- view helpers
  const fit = useCallback((nodes = shown.nodes) => {
    const el = box.current;
    if (!el || !nodes.length) return;
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const [x0, x1, y0, y1] = [Math.min(...xs) - 60, Math.max(...xs) + 60, Math.min(...ys) - 50, Math.max(...ys) + 50];
    const w = el.clientWidth;
    const h = el.clientHeight;
    const k = Math.min(1.6, Math.max(0.15, Math.min(w / (x1 - x0), h / (y1 - y0))));
    setView({ k, x: w / 2 - ((x0 + x1) / 2) * k, y: h / 2 - ((y0 + y1) / 2) * k });
  }, [shown.nodes]);

  useEffect(() => {
    if (!fitted.current && shown.nodes.length) {
      fitted.current = true;
      fit();
    }
  }, [shown.nodes, fit]);

  const zoom = (factor, cx, cy) => setView((v) => {
    const el = box.current;
    const px = cx ?? el.clientWidth / 2;
    const py = cy ?? el.clientHeight / 2;
    const k = Math.min(3, Math.max(0.12, v.k * factor));
    return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
  });

  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  const toGraph = (e) => {
    const r = box.current.getBoundingClientRect();
    return { x: (e.clientX - r.left - view.x) / view.k, y: (e.clientY - r.top - view.y) / view.k };
  };

  function pick(id) {
    setSelectedEdge(null);
    setSelected(id);
    const p = pos[id];
    const el = box.current;
    if (p && el) setView((v) => ({ ...v, x: el.clientWidth / 2 - p.x * v.k, y: el.clientHeight / 2 - p.y * v.k }));
  }

  function clickNode(id) {
    if (editing && connectFrom) {
      if (connectFrom !== id) setPendingLink({ source: connectFrom, target: id, link_type: "fiber", role: "primary" });
      setConnectFrom(null);
      return;
    }
    setSelectedEdge(null);
    setSelected((s) => (s === id ? null : id));
  }

  function onNodeDown(e, id) {
    e.stopPropagation();
    e.currentTarget.ownerSVGElement.setPointerCapture?.(e.pointerId);
    drag.current = { id, start: toGraph(e), origin: pos[id], moved: false };
  }

  function onBgDown(e) {
    drag.current = { pan: true, sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y, moved: false };
  }

  function onMove(e) {
    const d = drag.current;
    if (!d) return;
    if (d.pan) {
      const dx = e.clientX - d.sx;
      const dy = e.clientY - d.sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
      setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }));
      return;
    }
    const g = toGraph(e);
    const dx = g.x - d.start.x;
    const dy = g.y - d.start.y;
    if (Math.abs(dx) + Math.abs(dy) > 3 / view.k) d.moved = true;
    if (d.moved) setPos((p) => ({ ...p, [d.id]: { x: Math.round(d.origin.x + dx), y: Math.round(d.origin.y + dy) } }));
  }

  function onUp() {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (!d.moved) {
      if (d.pan) { setSelected(null); setSelectedEdge(null); setConnectFrom(null); }
      else clickNode(d.id);
    }
  }

  function applyLayout(name) {
    setLayout(name);
    if (!data) return;
    const computed = LAYOUT_FN[name](data.nodes, data.edges);
    setPos(computed);
    setTimeout(() => fit(shown.nodes.map((n) => ({ ...n, ...computed[n.id] }))), 0);
  }

  async function save() {
    const out = Object.fromEntries(Object.entries(pos).map(([id, p]) => [id, [p.x, p.y]]));
    try {
      const r = await api.saveGraphLayout(out);
      setSaved(out);
      setMsg({ ok: true, text: `Layout saved (${r.saved} nodes).` });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  }

  async function changed() {
    setSelected(null);
    setSelectedEdge(null);
    await load();
  }

  async function createNode(e) {
    e.preventDefault();
    try {
      const r = await api.addNode({ node_id: newNode.id.trim().toUpperCase(), name: newNode.name.trim(), node_type: newNode.type });
      const el = box.current;
      setPos((p) => ({ ...p, [r.node.node_id]: { x: Math.round((el.clientWidth / 2 - view.x) / view.k), y: Math.round((el.clientHeight / 2 - view.y) / view.k) } }));
      setMsg({ ok: true, text: `${r.node.node_id} added. Use Connect to link it.` });
      setNewNode(null);
      await load();
      setSelected(r.node.node_id);
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    }
  }

  async function createLink(e) {
    e.preventDefault();
    try {
      const r = await api.addLink({ source_node: pendingLink.source, target_node: pendingLink.target, link_type: pendingLink.link_type, role: pendingLink.role });
      setMsg({ ok: true, text: `Link ${r.link.link_id} added.` });
      setPendingLink(null);
      await load();
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    }
  }

  if (!data) return <section className="panel"><h2>Network investigation</h2><div className="muted small">{msg?.text ?? "Loading…"}</div></section>;

  const byId = Object.fromEntries(shown.nodes.map((n) => [n.id, n]));
  const node = data.nodes.find((n) => n.id === selected);
  const edge = data.edges.find((e) => e.id === selectedEdge);
  const sel = new Set(selected ? [selected, ...data.edges.filter((e) => e.source === selected || e.target === selected).flatMap((e) => [e.source, e.target])] : []);

  return (
    <section className="panel ig-panel">
      <div className="panel-head">
        <h2>Network investigation <span className="muted small">{shown.nodes.length} nodes</span></h2>
        <div className="ig-filters">
          <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Sources">
            {Object.entries(SOURCES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={disposition} onChange={(e) => setDisposition(e.target.value)} aria-label="Disposition">
            <option value="all">All dispositions</option>
            {Object.entries(DISPOSITIONS).map(([k, d]) => <option key={k} value={k}>{d.label}</option>)}
          </select>
          <select value={hours} onChange={(e) => setHours(+e.target.value)} aria-label="Period">
            {[1, 6, 24, 72, 168].map((h) => <option key={h} value={h}>last {h < 24 ? `${h} h` : `${h / 24} d`}</option>)}
          </select>
          <label className="check"><input type="checkbox" checked={affectedOnly} onChange={(e) => setAffectedOnly(e.target.checked)} /> Affected only</label>
        </div>
      </div>

      <div className="ig-toolbar">
        <div className="seg">
          <button className="seg-btn" title="Zoom in" onClick={() => zoom(1.25)}>＋</button>
          <button className="seg-btn" title="Zoom out" onClick={() => zoom(0.8)}>－</button>
          <button className="seg-btn" title="Fit to screen" onClick={() => fit()}>⤢ Fit</button>
          <button className="seg-btn" title="Reset layout" onClick={() => applyLayout(layout)}>↺ Reset</button>
        </div>
        <select value={layout} onChange={(e) => applyLayout(e.target.value)} aria-label="Layout">
          {Object.entries(LAYOUTS).map(([k, v]) => <option key={k} value={k}>Layout: {v}</option>)}
        </select>
        <input className="ig-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter: ID, name, alert…" />
        <details className="ig-hide">
          <summary className="btn btn-small">Hide ▾</summary>
          <div>
            {[["observable", "Alert types"], ["company", "Companies"], ["backup", "Unused backup links"]].map(([k, l]) => (
              <label key={k} className="check"><input type="checkbox" checked={hide[k]} onChange={(e) => setHide((h) => ({ ...h, [k]: e.target.checked }))} /> {l}</label>
            ))}
          </div>
        </details>
        <button className="btn btn-small" onClick={save}>Save layout</button>
        {editable && (
          <button className={`btn btn-small ${editing ? "btn-primary" : ""}`} onClick={() => { setEditing((v) => !v); setConnectFrom(null); setPendingLink(null); setNewNode(null); }}>
            {editing ? "Done editing" : "Edit network"}
          </button>
        )}
      </div>

      {editing && (
        <div className="ig-editbar">
          {Object.entries(NEW_NODE).map(([t, l]) => (
            <button key={t} className="btn btn-small" onClick={() => setNewNode({ type: t, id: "", name: "" })}>＋ {l}</button>
          ))}
          <button className={`btn btn-small ${connectFrom ? "btn-primary" : ""}`} onClick={() => setConnectFrom(connectFrom != null ? null : selected || "")}>
            {connectFrom ? `Connect ${connectFrom} → click a node` : connectFrom === "" ? "Click the first node" : "Connect"}
          </button>
          {connectFrom === "" && <span className="small muted">Click the first node, then the second.</span>}
          {newNode && (
            <form className="ig-inline" onSubmit={createNode}>
              <input value={newNode.id} onChange={(e) => setNewNode({ ...newNode, id: e.target.value })} placeholder={newNode.type === "satellite" ? "SAT-3" : newNode.type === "ground_station" ? "GS-3" : "BS-5G-AGA"} required />
              <input value={newNode.name} onChange={(e) => setNewNode({ ...newNode, name: e.target.value })} placeholder="Name (optional)" />
              <button className="btn btn-small btn-primary">Add {NEW_NODE[newNode.type]}</button>
              <button type="button" className="btn btn-small" onClick={() => setNewNode(null)}>Cancel</button>
            </form>
          )}
          {pendingLink && (
            <form className="ig-inline" onSubmit={createLink}>
              <b>{pendingLink.source} ↔ {pendingLink.target}</b>
              <select value={pendingLink.link_type} onChange={(e) => setPendingLink({ ...pendingLink, link_type: e.target.value })}>
                {["fiber", "satellite", "5g", "lan"].map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <select value={pendingLink.role} onChange={(e) => setPendingLink({ ...pendingLink, role: e.target.value })}>
                <option value="primary">primary</option><option value="backup">backup</option>
              </select>
              <button className="btn btn-small btn-primary">Add link</button>
              <button type="button" className="btn btn-small" onClick={() => setPendingLink(null)}>Cancel</button>
            </form>
          )}
        </div>
      )}
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}

      <div className="ig-layout">
        <AssetList nodes={shown.nodes} selected={selected} onPick={pick} />
        <div className={`ig-canvas ${editing ? "editing" : ""} ${connectFrom != null ? "connecting" : ""}`} ref={box}>
          <svg width="100%" height="100%" onPointerDown={onBgDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
            <defs>
              {[["alert", "#dc2626"], ["owns", "#a78bfa"]].map(([k, c]) => (
                <marker key={k} id={`ig-arrow-${k}`} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                  <path d="M0,0 L10,5 L0,10 z" fill={c} />
                </marker>
              ))}
            </defs>
            <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
              {shown.edges.map((e) => {
                const a = byId[e.source];
                const b = byId[e.target];
                if (!a || !b) return null;
                const d = Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1);
                const ux = (b.x - a.x) / d;
                const uy = (b.y - a.y) / d;
                const arrow = e.kind !== "link";
                const faded = selected && !(e.source === selected || e.target === selected);
                return (
                  <g key={e.id} className={faded ? "dim" : ""}>
                    <line className={`${edgeClass(e)} ${selectedEdge === e.id ? "on" : ""}`}
                          x1={a.x + ux * R} y1={a.y + uy * R} x2={b.x - ux * (R + 3)} y2={b.y - uy * (R + 3)}
                          markerEnd={arrow ? `url(#ig-arrow-${e.kind})` : undefined} />
                    {e.kind === "link" && (
                      <line className="ig-hit" x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                            onPointerDown={(ev) => { ev.stopPropagation(); setSelected(null); setSelectedEdge(e.id); }} />
                    )}
                  </g>
                );
              })}
              {shown.nodes.map((n) => (
                <NodeShape key={n.id} n={n} selected={selected === n.id || connectFrom === n.id}
                           dim={isDim(n) || (selected && !sel.has(n.id))}
                           onPointerDown={(e) => {
                             if (editing && connectFrom === "") { e.stopPropagation(); setConnectFrom(n.id); return; }
                             onNodeDown(e, n.id);
                           }} />
              ))}
            </g>
          </svg>
          <Legend />
        </div>
        <Details node={node} edge={edge} data={data} editing={editing} onPick={pick} onChanged={changed} setMsg={setMsg} />
      </div>
      <Timeline data={data} />
    </section>
  );
}
