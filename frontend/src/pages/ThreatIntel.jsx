import { useCallback, useEffect, useState } from "react";
import { Crosshair, Plus, Search, Trash2 } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { hashParams } from "../components/shell/navigation.js";

const VERDICT_TONE = { malicious: "tone-bad", suspicious: "tone-warn", clean: "tone-ok", unknown: "muted" };

function Lookup({ initial }) {
  const [value, setValue] = useState(initial ?? "");
  const [res, setRes] = useState(null);
  const [sight, setSight] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = useCallback((v) => {
    if (!v.trim()) return;
    setBusy(true);
    setErr(null);
    Promise.all([api.intelLookup(v.trim()), api.sightings(v.trim())])
      .then(([r, s]) => { setRes(r); setSight(s); })
      .catch((e) => { setErr(e.message); setRes(null); })
      .finally(() => setBusy(false));
  }, []);
  useEffect(() => {
    if (initial) {
      setValue(initial);
      run(initial);
    }
  }, [initial, run]);

  return (
    <section className="panel">
      <h2>Look up an indicator</h2>
      <form className="filter-bar" onSubmit={(e) => { e.preventDefault(); run(value); }}>
        <div className="global-search" style={{ width: "auto", flex: 1 }}>
          <Search size={14} />
          <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="IP address, domain, URL or file hash" aria-label="Indicator" />
        </div>
        <button className="btn btn-small btn-primary" disabled={busy}>{busy ? "Looking up…" : "Look up"}</button>
      </form>
      {err && <div className="tone-bad small">{err}</div>}
      {res && (
        <>
          <div style={{ margin: "8px 0" }}>
            <span className="mono">{res.value}</span> <span className="muted small">({res.kind})</span> · verdict{" "}
            <b className={VERDICT_TONE[res.verdict]}>{res.verdict}</b>
          </div>
          <dl className="kv">
            <dt>Local IOC list</dt>
            <dd>{res.local.length ? res.local.map((l) => <div key={l.id}>{l.threat} · confidence {l.confidence}% · {l.origin}{l.active ? "" : " (inactive)"}</div>) : "not listed"}</dd>
            {res.external.map((x) => (
              <Fragmentless key={x.provider} x={x} />
            ))}
            {res.external_skipped && <><dt>External services</dt><dd className="muted">not asked: {res.external_skipped}</dd></>}
            {!res.external_skipped && res.external.length === 0 && <><dt>External services</dt><dd className="muted">no service configured for this kind (keys in .env)</dd></>}
          </dl>
          {sight && (
            <div className="small" style={{ marginTop: 8 }}>
              Seen in <b>{sight.events.length}</b> security events and <b>{sight.alerts.length}</b> alerts (7 days)
              {sight.devices.length > 0 && <> · devices {sight.devices.map((d) => <a key={d} href={`#devices/${d}`} className="mono"> {d}</a>)}</>}
              {sight.events.length > 0 && <> · <a href={`#hunting?q=${encodeURIComponent(`ip:${res.value}`)}`}><Crosshair size={11} /> hunt</a></>}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function Fragmentless({ x }) {
  return (
    <>
      <dt>{x.provider}{x.cached ? " (cached)" : ""}</dt>
      <dd>
        {x.error ? <span className="tone-bad">{x.error}</span> : x.found === false ? <span className="muted">unknown to this service</span> : (
          <>
            <b className={VERDICT_TONE[x.verdict]}>{x.verdict}</b>
            {x.malicious != null && ` · ${x.malicious} engines say malicious, ${x.suspicious} suspicious`}
            {x.abuse_score != null && ` · abuse score ${x.abuse_score}% from ${x.reports ?? 0} reports`}
            {x.pulses != null && ` · in ${x.pulses} OTX pulses`}
            {x.country && ` · ${x.country}`}{x.owner && ` · ${x.owner}`}{x.isp && ` · ${x.isp}`}
          </>
        )}
      </dd>
    </>
  );
}

// v2.1 Threat Intelligence: the local IOC list (matched against every security event by rule CS-018)
// and enrichment through VirusTotal / AbuseIPDB / OTX when their keys are set on the server.
export default function ThreatIntel() {
  const { has } = useAuth();
  const [iocs, setIocs] = useState([]);
  const [providers, setProviders] = useState([]);
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ value: "", threat: "", confidence: 70, tags: "", description: "", days: "" });
  const [msg, setMsg] = useState(null);
  const [focus, setFocus] = useState(() => hashParams().value);
  useEffect(() => {
    const on = () => setFocus(hashParams().value);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const load = useCallback(() => api.iocs(q).then((r) => setIocs(r.iocs)).catch((e) => setMsg({ ok: false, text: e.message })), [q]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.intelProviders().then((r) => setProviders(r.providers)).catch(() => {}); }, []);

  async function add(e) {
    e.preventDefault();
    try {
      await api.addIoc({ ...form, confidence: Number(form.confidence), days: form.days ? Number(form.days) : null });
      setForm({ ...form, value: "", threat: "", description: "" });
      setMsg({ ok: true, text: "Indicator added. Every new security event is checked against it." });
      load();
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    }
  }
  const act = (p, text) => p.then(() => { setMsg({ ok: true, text }); load(); }).catch((e) => setMsg({ ok: false, text: e.message }));

  return (
    <>
      <div className="grid-main-side">
        <Lookup initial={focus} />
        <section className="panel">
          <h2>Enrichment services</h2>
          <ul className="mini-list">
            {providers.map((p) => (
              <li key={p.id}>
                <span className={`status-dot ${p.configured ? "" : "off"}`} style={{ background: p.configured ? "var(--ok)" : "var(--muted)" }} />
                <a href={p.site} target="_blank" rel="noreferrer">{p.name}</a>
                <span className="small muted push-right">{p.configured ? `on · ${p.kinds.join(", ")}` : `off · set ${p.env} in .env`}</span>
              </li>
            ))}
          </ul>
          <p className="small muted">Keys stay on the server. Private addresses and the simulator's documentation addresses are never sent out.
            Answers are kept 24 h to save the free quota.</p>
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Indicators of compromise <span className="muted small">{iocs.length}</span></h2>
          <div className="global-search" style={{ width: 260 }}>
            <Search size={14} /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter value, threat, tag" />
          </div>
        </div>
        <div className="table-wrap" style={{ maxHeight: 460 }}>
          <table className="data-table">
            <thead><tr><th>Indicator</th><th>Kind</th><th>Threat</th><th>Confidence</th><th>Tags</th><th>Origin</th><th>Seen 24 h</th><th>Active</th><th /></tr></thead>
            <tbody>
              {iocs.map((i) => (
                <tr key={i.id}>
                  <td className="mono small"><a href={`#intel?value=${encodeURIComponent(i.value)}`}>{i.value}</a></td>
                  <td className="small">{i.kind}</td>
                  <td title={i.description}>{i.threat}</td>
                  <td>{i.confidence}%</td>
                  <td className="small">{i.tags.join(", ")}</td>
                  <td className="small muted">{i.origin} · {i.created_by}</td>
                  <td>{i.sightings_24h ? <a href={`#hunting?q=${encodeURIComponent(`ip:${i.value}`)}`} className="tone-bad">{i.sightings_24h}</a> : <span className="muted">0</span>}</td>
                  <td>
                    <button className={`toggle ${i.active ? "on" : ""}`} disabled={!has("intel")} aria-label={i.active ? "Deactivate" : "Activate"}
                            onClick={() => act(api.updateIoc(i.id, { active: !i.active }), `${i.value} ${i.active ? "deactivated" : "activated"}.`)} />
                  </td>
                  <td>{has("intel") && <button className="icon-btn" aria-label={`Delete ${i.value}`} onClick={() => act(api.deleteIoc(i.id), `${i.value} deleted.`)}><Trash2 size={13} /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {iocs.length === 0 && <div className="empty">No indicator.</div>}
        </div>
        {has("intel") && (
          <form className="filter-bar" onSubmit={add} style={{ marginTop: 10 }}>
            <input className="mono" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} placeholder="IP, domain, URL or hash" required style={{ flex: 1, minWidth: 160 }} />
            <input value={form.threat} onChange={(e) => setForm({ ...form, threat: e.target.value })} placeholder="Threat (e.g. C2 server)" maxLength={80} />
            <label className="small">Confidence <input type="number" min={0} max={100} value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} style={{ width: 60 }} /></label>
            <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="tags, comma separated" />
            <input type="number" min={1} value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} placeholder="expires (days)" style={{ width: 110 }} />
            <button className="btn btn-small btn-primary"><Plus size={13} /> Add IOC</button>
          </form>
        )}
        {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
        <p className="small muted">Demo indicators (origin “demo seed”) use documentation addresses (RFC 5737) and the reserved .example domain: they are not real threat data.</p>
      </section>
    </>
  );
}
