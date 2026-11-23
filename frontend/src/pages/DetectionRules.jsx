import { Fragment, useCallback, useEffect, useState } from "react";
import { ExternalLink, FlaskConical } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { Confidence } from "./AlertCenter.jsx";

const KIND_LABEL = { threshold: "Threshold", signature: "Signature", rule: "Rule", availability: "Availability", ml: "Machine learning" };
const ago = (iso) => (iso ? new Date(iso).toLocaleString() : "never");

// v2.0 Detection Rules: every rule the engine runs, its logic, MITRE technique and
// confidence, hits in the last 24 h, an on/off switch (platform admin) and a
// one-click simulated test that must produce the rule's alert.
export default function DetectionRules({ onNavigate }) {
  const { has, isPlatform } = useAuth();
  const [rules, setRules] = useState(null);
  const [open, setOpen] = useState(null);
  const [msg, setMsg] = useState(null);
  const load = useCallback(() => api.socRules().then((r) => setRules(r.rules)).catch((e) => setMsg({ ok: false, text: e.message })), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  async function toggle(r) {
    try {
      await api.setRule(r.id, !r.enabled);
      setMsg({ ok: true, text: `${r.id} ${r.enabled ? "switched off" : "switched on"}.` });
      load();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  }

  async function test(r) {
    try {
      const res = await api.testRule(r.id);
      setMsg({ ok: true, text: `${res.message} It will appear in the Alert Center within a few seconds.` });
      setTimeout(load, 4000);
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  }

  if (!rules) return <section className="panel"><div className="muted">{msg?.text ?? "Loading rules…"}</div></section>;
  const enabled = rules.filter((r) => r.enabled).length;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Detection rules <span className="muted small">{enabled}/{rules.length} enabled</span></h2>
        <span className="small muted">CS-001…010 read telemetry, CS-011…021 the security event store · Suricata, Zeek, Wazuh, Sigma: not connected in this build</span>
      </div>
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`} style={{ marginBottom: 8 }}>{msg.text}</div>}
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>On</th><th>ID</th><th>Rule</th><th>Type</th><th>Severity</th><th>MITRE ATT&amp;CK</th><th>Confidence</th><th>Hits 24 h</th><th>Last hit</th><th /></tr></thead>
          <tbody>
            {rules.map((r) => (
              <Fragment key={r.id}>
                <tr className={`clickable ${open === r.id ? "on" : ""}`} onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button className={`toggle ${r.enabled ? "on" : ""}`} aria-label={`${r.enabled ? "Disable" : "Enable"} ${r.id}`}
                            disabled={!(has("rules") && isPlatform)} title={has("rules") && isPlatform ? "" : "Platform admins and the SOC manager only"} onClick={() => toggle(r)} />
                  </td>
                  <td className="mono">{r.id}</td>
                  <td>{r.name}</td>
                  <td>{KIND_LABEL[r.kind] ?? r.kind}</td>
                  <td className="small">{r.severity}</td>
                  <td>{r.mitre ? <a className="mitre" href={r.mitre.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{r.mitre.id}</a> : <span className="muted small">—</span>}</td>
                  <td><Confidence value={r.confidence} /></td>
                  <td>{r.hits_24h ? <a href={`#alerts`} onClick={(e) => { e.preventDefault(); e.stopPropagation(); onNavigate("alerts"); }}>{r.hits_24h}</a> : 0}</td>
                  <td className="small">{ago(r.last_hit)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {r.test_attack && has("simulate") && isPlatform && (
                      <button className="btn btn-small" disabled={!r.enabled} onClick={() => test(r)} title="Runs a simulated attack that this rule must detect">
                        <FlaskConical size={13} /> Test
                      </button>
                    )}
                  </td>
                </tr>
                {open === r.id && (
                  <tr>
                    <td colSpan={10} style={{ background: "var(--bg-2)" }}>
                      <dl className="kv">
                        <dt>Logic</dt><dd className="mono">{r.logic}</dd>
                        <dt>Explanation</dt><dd>{r.explanation}</dd>
                        <dt>Data source</dt><dd>{r.data_source}</dd>
                        <dt>MITRE</dt><dd>{r.mitre ? <a href={r.mitre.url} target="_blank" rel="noreferrer">{r.mitre.id} {r.mitre.name} · {r.mitre.tactic} <ExternalLink size={11} /></a> : "No ATT&CK technique: this rule reports an availability or physical event."}</dd>
                        <dt>Test</dt><dd>{r.test_attack ? `Simulated "${r.test_attack}" attack (inside this project only).` : "No simulated test: it fires on real network faults, sensors or the ML model."}</dd>
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
