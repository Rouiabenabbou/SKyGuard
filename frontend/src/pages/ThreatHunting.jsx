import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bookmark, Download, Minus, Plus, Play, Radar, Trash2, X } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { sourceParam, useEnvironment } from "../services/environment.js";
import { hashParams } from "../components/shell/navigation.js";
import { axis, tooltip } from "../components/charts/theme.js";
import { SourceBadge } from "./AlertCenter.jsx";

const RANGES = [[0.25, "15 min"], [1, "1 h"], [24, "24 h"], [168, "7 days"], [720, "30 days"]];
const FACET_FIELD = { event_type: "type", src_ip: "src", dst_ip: "dst", device_id: "device", dst_port: "dport", protocol: "proto", source: "source" };
const FACET_LABEL = { event_type: "Event type", src_ip: "Source address", dst_ip: "Destination address", device_id: "Device", dst_port: "Destination port", protocol: "Protocol", source: "Source" };
const OUTCOME_TONE = { failure: "tone-bad", denied: "tone-bad", success: "tone-ok", observed: "" };
const time = (iso) => new Date(iso).toLocaleTimeString();

export function ProductionNotice() {
  return (
    <section className="panel notice">
      <b>Production selected.</b> No production data source is connected: this project has no authorised real
      infrastructure, so there is nothing to show. Choose Simulation, Lab or All sources in the top bar.
    </section>
  );
}

function EventDetail({ ev, onClose, onPivot }) {
  const [incidents, setIncidents] = useState([]);
  const [inc, setInc] = useState("");
  const [msg, setMsg] = useState(null);
  const { has } = useAuth();
  useEffect(() => { api.incidents().then((r) => setIncidents(r.incidents.filter((i) => i.status !== "resolved"))).catch(() => {}); }, []);
  const attach = () => api.addEvidence(Number(inc), { kind: "security_event", ref: String(ev.id) })
    .then(() => setMsg({ ok: true, text: `Attached to incident #${inc}.` })).catch((e) => setMsg({ ok: false, text: e.message }));
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Event #{ev.id} <span className="muted small">{ev.event_type}</span></h2>
        <button className="icon-btn" aria-label="Close" onClick={onClose}><X size={16} /></button>
      </div>
      <dl className="kv">
        <dt>Time</dt><dd>{new Date(ev.timestamp).toLocaleString()} <SourceBadge source={ev.source} /></dd>
        <dt>Category</dt><dd>{ev.category} · {ev.severity}</dd>
        <dt>Device</dt><dd>{ev.device_id ? <a href={`#devices/${ev.device_id}`}>{ev.device_id}</a> : "—"}</dd>
        <dt>Source</dt><dd className="mono">{ev.src_ip ?? "—"}{ev.src_port ? `:${ev.src_port}` : ""}</dd>
        <dt>Destination</dt><dd className="mono">{ev.dst_ip ?? "—"}{ev.dst_port ? `:${ev.dst_port}` : ""} {ev.protocol}</dd>
        {ev.mqtt_client && <><dt>MQTT client</dt><dd className="mono">{ev.mqtt_client}</dd></>}
        {ev.mqtt_topic && <><dt>Topic</dt><dd className="mono">{ev.mqtt_topic}</dd></>}
        {ev.username && <><dt>Account</dt><dd className="mono">{ev.username}</dd></>}
        <dt>Outcome</dt><dd className={OUTCOME_TONE[ev.outcome]}>{ev.outcome}</dd>
        <dt>Bytes</dt><dd>{ev.bytes.toLocaleString()}</dd>
        <dt>Message</dt><dd>{ev.message}</dd>
      </dl>
      <pre className="json-box">{JSON.stringify(ev.details, null, 2)}</pre>
      <div className="button-row" style={{ flexWrap: "wrap" }}>
        {ev.src_ip && <button className="btn btn-small" onClick={() => onPivot(`ip:${ev.src_ip}`)}>Hunt {ev.src_ip}</button>}
        {ev.dst_ip && <button className="btn btn-small" onClick={() => onPivot(`ip:${ev.dst_ip}`)}>Hunt {ev.dst_ip}</button>}
        {ev.device_id && <button className="btn btn-small" onClick={() => onPivot(`device:${ev.device_id}`)}>All of {ev.device_id}</button>}
        {(ev.src_ip || ev.dst_ip) && <a className="btn btn-small" href={`#intel?value=${encodeURIComponent(ev.src_ip?.startsWith("10.") ? ev.dst_ip : ev.src_ip ?? ev.dst_ip)}`}><Radar size={13} /> Threat intel</a>}
      </div>
      {has("incident") && incidents.length > 0 && (
        <div className="button-row" style={{ marginTop: 8 }}>
          <select value={inc} onChange={(e) => setInc(e.target.value)} aria-label="Incident">
            <option value="">Attach to incident…</option>
            {incidents.map((i) => <option key={i.id} value={i.id}>#{i.id} {i.title}</option>)}
          </select>
          <button className="btn btn-small" disabled={!inc} onClick={attach}>Attach as evidence</button>
        </div>
      )}
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </section>
  );
}

// v2.1 Threat Hunting: search the security event store with a small query language,
// see the time histogram and the top values, pivot, save queries and export.
export default function ThreatHunting() {
  const env = useEnvironment();
  const { has, user } = useAuth();
  const [q, setQ] = useState(() => hashParams().q ?? "-category:flow");
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState({ queries: [], templates: [] });
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const [sel, setSel] = useState(null);
  const [offset, setOffset] = useState(0);
  const params = { q, hours, source: sourceParam(env) };

  const runQuery = useCallback((query = q, h = hours, off = 0) => {
    setBusy(true);
    setOffset(off);
    api.hunt({ q: query, hours: h, source: sourceParam(env), limit: 100, offset: off })
      .then((r) => { setData(r); setErr(null); })
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false));
  }, [q, hours, env]);
  const loadSaved = () => api.huntQueries().then(setSaved).catch(() => {});
  useEffect(() => { runQuery(); loadSaved(); }, [env]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // a link such as #hunting?q=src:1.2.3.4 while this page is open
    const on = () => { const p = hashParams(); if (p.q) { setQ(p.q); setSel(null); runQuery(p.q, hours); } };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, [runQuery, hours]);

  const apply = (query, h = hours) => {
    setQ(query);
    setHours(h);
    setSel(null);
    runQuery(query, h);
  };
  const addTerm = (term) => apply(`${q.split(" ").filter((t) => t && t !== term && t !== term.replace(/^-/, "")).join(" ")} ${term}`.trim());

  async function save() {
    try {
      await api.saveHuntQuery({ name: name.trim(), query: q, hours: Math.max(1, Math.round(hours)), shared });
      setName("");
      loadSaved();
    } catch (e) {
      setErr(e.message);
    }
  }

  if (env === "production") return <ProductionNotice />;

  return (
    <div className="hunt-layout">
      <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
        <section className="panel">
          <form className="filter-bar" onSubmit={(e) => { e.preventDefault(); apply(q); }}>
            <input className="mono hunt-input" value={q} onChange={(e) => setQ(e.target.value)} spellCheck={false}
                   placeholder='type:mqtt_auth_failure src:203.0.113.*   device:IOT-003 -dst:10.*   bytes:>1000000   "refused"' aria-label="Hunting query" />
            <select value={hours} onChange={(e) => apply(q, Number(e.target.value))} aria-label="Time range">
              {RANGES.map(([h, l]) => <option key={h} value={h}>Last {l}</option>)}
            </select>
            <button className="btn btn-small btn-primary" disabled={busy}><Play size={13} /> Run</button>
            <button type="button" className="btn btn-small" disabled={!data?.total} onClick={() => api.huntExport(params, "csv").catch((e) => setErr(e.message))}><Download size={13} /> CSV</button>
            <button type="button" className="btn btn-small" disabled={!data?.total} onClick={() => api.huntExport(params, "json").catch((e) => setErr(e.message))}><Download size={13} /> JSON</button>
          </form>
          <div className="small muted">
            Fields: type category severity source device src dst ip sport dport port proto client topic user outcome bytes id ·
            <span className="mono"> a,b</span> any of · <span className="mono">*</span> wildcard · <span className="mono">-field:x</span> not ·
            <span className="mono"> bytes:&gt;N</span> · <span className="mono">"text"</span> in the message
          </div>
          {err && <div className="tone-bad small" style={{ marginTop: 6 }}>{err}</div>}
          {data && (
            <>
              <div className="small" style={{ margin: "8px 0 4px" }}>
                <b>{data.total.toLocaleString()}</b> events · {new Date(data.from).toLocaleString()} → {new Date(data.to).toLocaleString()}
                {data.sampled && <span className="muted"> · histogram and top values from the newest 20 000</span>}
              </div>
              <div style={{ height: 110 }}>
                <ResponsiveContainer>
                  <BarChart data={data.histogram} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                    <XAxis dataKey="t" {...axis} tickFormatter={(t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} minTickGap={40} />
                    <YAxis {...axis} allowDecimals={false} />
                    <Tooltip {...tooltip} cursor={{ fill: "rgba(148,163,184,0.12)" }} labelFormatter={(t) => new Date(t).toLocaleString()} formatter={(v) => [v, "events"]} />
                    <Bar dataKey="count" fill="#2a78d6" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </section>

        {sel && <EventDetail ev={sel} onClose={() => setSel(null)} onPivot={(t) => apply(t)} />}

        <section className="panel">
          <div className="table-wrap" style={{ maxHeight: 560 }}>
            <table className="data-table compact">
              <thead><tr><th>Time</th><th>Src</th><th>Event</th><th>Device</th><th>Source → destination</th><th>Proto</th><th>Client / account</th><th>Outcome</th><th>Bytes</th><th>Message</th></tr></thead>
              <tbody>
                {data?.events.map((e) => (
                  <tr key={e.id} className={`clickable ${sel?.id === e.id ? "on" : ""}`} onClick={() => setSel(e)}>
                    <td className="small nowrap" title={new Date(e.timestamp).toLocaleString()}>{time(e.timestamp)}</td>
                    <td><SourceBadge source={e.source} /></td>
                    <td className="mono small">{e.event_type}</td>
                    <td className="mono small">{e.device_id ?? "—"}</td>
                    <td className="mono small nowrap">{e.src_ip ?? "—"}{e.src_port ? `:${e.src_port}` : ""} → {e.dst_ip ?? "—"}{e.dst_port ? `:${e.dst_port}` : ""}</td>
                    <td className="small">{e.protocol}</td>
                    <td className="mono small">{e.mqtt_client || e.username || "—"}</td>
                    <td className={`small ${OUTCOME_TONE[e.outcome]}`}>{e.outcome}</td>
                    <td className="small">{e.bytes ? e.bytes.toLocaleString() : ""}</td>
                    <td className="small hunt-msg">{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && data.events.length === 0 && (
              <div className="empty">No event matches. Security events appear when devices send data (one flow record per device per minute)
                and when a simulated attack runs (Attack Simulation).</div>
            )}
          </div>
          {data && data.total > 100 && (
            <div className="button-row" style={{ justifyContent: "flex-end", marginTop: 8 }}>
              <button className="btn btn-small" disabled={offset === 0} onClick={() => runQuery(q, hours, Math.max(0, offset - 100))}>Newer</button>
              <span className="small muted">{offset + 1}–{Math.min(offset + 100, data.total)} of {data.total}</span>
              <button className="btn btn-small" disabled={offset + 100 >= data.total} onClick={() => runQuery(q, hours, offset + 100)}>Older</button>
            </div>
          )}
        </section>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
        <section className="panel">
          <h2>Top values</h2>
          {data && Object.entries(data.facets).filter(([, v]) => v.length).map(([k, vals]) => (
            <div key={k} className="facet">
              <div className="small muted">{FACET_LABEL[k]}</div>
              {vals.map((v) => (
                <div key={String(v.value)} className="facet-row">
                  <span className="mono small facet-val" title={String(v.value)}>{String(v.value)}</span>
                  <span className="small muted">{v.count}</span>
                  <button className="icon-btn" title="Only this" aria-label={`Only ${v.value}`} onClick={() => addTerm(`${FACET_FIELD[k]}:${v.value}`)}><Plus size={12} /></button>
                  <button className="icon-btn" title="Exclude" aria-label={`Exclude ${v.value}`} onClick={() => addTerm(`-${FACET_FIELD[k]}:${v.value}`)}><Minus size={12} /></button>
                </div>
              ))}
            </div>
          ))}
          {data && !Object.values(data.facets).some((v) => v.length) && <div className="empty">Nothing yet.</div>}
        </section>

        <section className="panel">
          <h2>Saved queries</h2>
          <ul className="mini-list">
            {saved.queries.map((s) => (
              <li key={s.id}>
                <a href="#hunting" onClick={(e) => { e.preventDefault(); apply(s.query, s.hours); }}><Bookmark size={12} /> {s.name}</a>
                <span className="muted small push-right">{s.shared ? `shared · ${s.owner}` : "mine"}</span>
                {(s.owner === user?.username || user?.role === "admin") && has("hunt") && (
                  <button className="icon-btn" aria-label={`Delete ${s.name}`} onClick={() => api.deleteHuntQuery(s.id).then(loadSaved)}><Trash2 size={12} /></button>
                )}
              </li>
            ))}
            {saved.queries.length === 0 && <li className="muted small">None yet.</li>}
          </ul>
          {has("hunt") && (
            <div className="filter-bar" style={{ marginTop: 8 }}>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name of this query" maxLength={80} style={{ flex: 1 }} />
              <label className="small"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} /> share</label>
              <button className="btn btn-small" disabled={!name.trim()} onClick={save}>Save</button>
            </div>
          )}
          <h3 className="small muted" style={{ marginTop: 12 }}>Ready-made hunts</h3>
          <ul className="mini-list">
            {saved.templates.map((t) => (
              <li key={t.name}><a href="#hunting" onClick={(e) => { e.preventDefault(); apply(t.query, t.hours); }}>{t.name}</a>
                <span className="mono small muted push-right" style={{ minWidth: 0, overflowWrap: "anywhere" }}>{t.query}</span></li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
