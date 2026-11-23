import { useEffect, useState } from "react";
import { Activity, Database, Radar, Satellite, ShieldAlert, Target } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../services/api.js";
import { alertLabel } from "../components/AlertsPanel.jsx";
import { axis, grid, SEVERITY_COLORS, tooltip } from "../components/charts/theme.js";
import AvailabilityChart from "../components/charts/AvailabilityChart.jsx";
import EventLog from "../components/EventLog.jsx";

const SEV = ["critical", "high", "medium", "low"];
const dash = (v, unit = "") => (v == null ? "—" : `${v}${unit}`);
const ago = (iso) => {
  if (!iso) return "never";
  const s = Math.round((Date.now() - Date.parse(iso)) / 1000);
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
};
const fmtDur = (min) => (min == null ? "—" : min < 1 ? `${Math.round(min * 60)} s` : min < 120 ? `${min} min` : `${(min / 60).toFixed(1)} h`);

function Kpi({ label, value, sub, tone }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${tone ? `tone-${tone}` : ""}`}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

function SevBar({ counts }) {
  const total = SEV.reduce((s, k) => s + (counts?.[k] ?? 0), 0);
  return (
    <div className="sev-bar" title={SEV.map((k) => `${k}: ${counts?.[k] ?? 0}`).join(" · ")}>
      {total > 0 && SEV.map((k) => <span key={k} style={{ width: `${((counts[k] ?? 0) / total) * 100}%`, background: SEVERITY_COLORS[k] }} />)}
    </div>
  );
}

function Segment({ name, s }) {
  if (!s || !s.total) return <div className="health-row"><span>{name}</span><span className="muted">no links</span></div>;
  const tone = s.offline ? "bad" : s.degraded ? "warn" : "ok";
  return (
    <div className="health-row">
      <span>{name}</span>
      <span className={`tone-${tone}`}>{s.online}/{s.total} up{s.degraded ? ` · ${s.degraded} degraded` : ""}{s.offline ? ` · ${s.offline} down` : ""}</span>
    </div>
  );
}

function BarList({ rows, label, onPick }) {
  const max = Math.max(1, ...rows.map((r) => r[1]));
  if (!rows.length) return <div className="empty">No alerts in the last 24 h.</div>;
  return (
    <ul className="mini-list bar-list">
      {rows.map(([k, v]) => (
        <li key={k} onClick={() => onPick?.(k)} style={{ cursor: onPick ? "pointer" : "default" }}>
          <span className="mono" title={k}>{label ? label(k) : k}</span><i style={{ width: `${(v / max) * 100}%` }} /><b>{v}</b>
        </li>
      ))}
    </ul>
  );
}

// v2.0 SOC Overview. Every number comes from /api/soc/overview (stored alerts, incidents,
// telemetry and the live network snapshot); "—" means there is no data yet.
export default function SocOverview({ events, availability, onNavigate }) {
  const [o, setO] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    const load = () => api.socOverview().then((r) => { setO(r); setErr(null); }).catch((e) => setErr(e.message));
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);
  if (!o) return <section className="panel"><div className="muted">{err ?? "Loading SOC metrics…"}</div></section>;

  const timeline = o.alerts.timeline.map((b) => ({ ...b, ms: Date.parse(b.t) }));
  const inc = o.incidents.by_severity;
  const ing = o.ingestion;
  const fresh = ing.last_reading && Date.now() - Date.parse(ing.last_reading) < 30000;

  return (
    <>
      <div className="kpi-strip">
        <Kpi label="Open incidents" value={o.incidents.open} tone={inc.critical || inc.high ? "bad" : o.incidents.open ? "warn" : "ok"}
             sub={`${inc.critical} critical · ${inc.high} high · ${inc.medium} med · ${inc.low} low`} />
        <Kpi label="Active alerts" value={o.alerts.open} tone={o.alerts.open_by_severity.critical || o.alerts.open_by_severity.high ? "bad" : o.alerts.open ? "warn" : "ok"}
             sub={`${o.alerts.open_by_severity.critical + o.alerts.open_by_severity.high} high or critical`} />
        <Kpi label="Alerts · 24 h" value={o.alerts.last_24h} sub={`${o.detection.alerts_last_hour} in the last hour`} />
        <Kpi label="MTTD" value={o.mttd_seconds == null ? "—" : `${o.mttd_seconds} s`} sub={o.mttd_samples ? `${o.mttd_samples} simulated attacks, 7 d` : "no attack measured yet"} />
        <Kpi label="MTTA" value={fmtDur(o.mtta_minutes)} sub="alert → first analyst action" />
        <Kpi label="MTTR" value={fmtDur(o.mttr_minutes)} sub="incident open → resolved, 7 d" />
        <Kpi label="Devices online" value={`${o.devices.online}/${o.devices.total}`} tone={o.devices.online === o.devices.total ? "ok" : "warn"}
             sub={`${o.devices.suspicious} suspicious · ${o.devices.quarantined} quarantined`} />
        <Kpi label="Availability" value={dash(o.network.availability, "%")} tone={o.network.availability === 100 ? "ok" : o.network.availability == null ? "" : "warn"}
             sub={o.network.nodes_down.length ? `down: ${o.network.nodes_down.join(", ")}` : "all infrastructure up"} />
        <Kpi label="Traffic" value={`${o.traffic.messages_per_min}/min`} sub={`${o.traffic.messages_last_hour} messages in 1 h`} />
      </div>

      <div className="grid-main-side">
        <section className="panel">
          <div className="panel-head">
            <h2><ShieldAlert size={16} /> Security events · last 24 h</h2>
            <button className="btn btn-small" onClick={() => onNavigate("alerts")}>Open Alert Center</button>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={timeline} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="ms" {...axis} tickFormatter={(ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit" })} minTickGap={28} />
              <YAxis {...axis} allowDecimals={false} width={40} />
              <Tooltip {...tooltip} cursor={{ fill: "rgba(148,163,184,0.1)" }} labelFormatter={(ms) => new Date(ms).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })} />
              {[...SEV].reverse().map((s) => <Bar key={s} dataKey={s} stackId="a" fill={SEVERITY_COLORS[s]} isAnimationActive={false} />)}
            </BarChart>
          </ResponsiveContainer>
          <div className="section-label">Open alerts by severity</div>
          <SevBar counts={o.alerts.open_by_severity} />
        </section>

        <section className="panel">
          <h2><Satellite size={16} /> Satellite and 5G status</h2>
          <Segment name="Satellite links" s={o.network.satellite} />
          <Segment name="5G radio links" s={o.network["5g"]} />
          <Segment name="Fibre backhaul" s={o.network.fiber} />
          <div className="health-row"><span>Nodes down</span><span className={o.network.nodes_down.length ? "tone-bad" : "tone-ok"}>{o.network.nodes_down.length ? o.network.nodes_down.join(", ") : "none"}</span></div>
          <h2 style={{ marginTop: 14 }}><Radar size={16} /> Detection engine</h2>
          <div className="health-row"><span>Rules enabled</span><span className={o.detection.rules_enabled < o.detection.rules_total ? "tone-warn" : "tone-ok"}>{o.detection.rules_enabled}/{o.detection.rules_total}</span></div>
          <div className="health-row"><span>Machine learning</span><span className={o.detection.ml.trained ? "tone-ok" : "muted"}>{!o.detection.ml.enabled ? "off" : o.detection.ml.trained ? "trained, scoring" : "learning normal behaviour"}</span></div>
          <div className="health-row"><span>Last alert</span><span>{ago(o.detection.last_alert)}</span></div>
          <h2 style={{ marginTop: 14 }}><Database size={16} /> Data ingestion</h2>
          <div className="health-row"><span>Last reading</span><span className={fresh ? "tone-ok" : "tone-warn"}>{ago(ing.last_reading)}</span></div>
          <div className="health-row"><span>Readings · 5 min</span><span>{ing.readings_last_5min}</span></div>
          <div className="health-row"><span>Sources · 1 h</span>
            <span>{Object.entries(ing.sources_last_hour).map(([k, v]) => <span key={k} className={`src-badge src-${k}`} style={{ marginLeft: 4 }}>{k.toUpperCase()} {v}</span>)}{!Object.keys(ing.sources_last_hour).length && "—"}</span></div>
          <div className="health-row"><span>MQTT broker</span><span className={ing.mqtt_connected ? "tone-ok" : "muted"}>{ing.mqtt_connected ? "connected" : "not used (simulator sends directly)"}</span></div>
          <div className="health-row"><span>Simulator</span><span className={ing.simulation_running ? "tone-ok" : "tone-warn"}>{ing.simulation_running ? "running" : "paused"}</span></div>
        </section>
      </div>

      <div className="grid-3">
        <section className="panel">
          <h2><Target size={16} /> Most targeted assets · 24 h</h2>
          <BarList rows={o.top_targets} onPick={(id) => onNavigate(`devices/${id}`)} />
        </section>
        <section className="panel">
          <h2><ShieldAlert size={16} /> Top detections · 24 h</h2>
          <BarList rows={o.top_types} label={alertLabel} />
        </section>
        <section className="panel">
          <h2><Activity size={16} /> Network availability</h2>
          <AvailabilityChart points={availability} />
        </section>
      </div>
      <EventLog events={events.slice(0, 10)} />
    </>
  );
}
