import { useEffect, useRef, useState } from "react";
import { Bot, CircleCheck, CircleX, ExternalLink, FolderKanban, ShieldOff, Wrench } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { hashParams } from "../components/shell/navigation.js";
import Markdown from "../components/Markdown.jsx";
import AIAssistant from "../components/AIAssistant.jsx";

const KIND_LABEL = { alert: "Alert", security_event: "Event", device: "Device", intel: "Intel", rule: "Rule", connections: "Traffic",
  playbook: "Playbook", incident: "Incident" };

export function Investigation({ res, onDone }) {
  const { has } = useAuth();
  const [hl, setHl] = useState(null);
  const [acted, setActed] = useState({});
  const refs = useRef({});
  const cite = (id) => {
    setHl(id);
    refs.current[id]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };
  async function confirm(a) {
    try {
      let text;
      if (a.tool === "create_incident") {
        const r = await api.createIncident({ alert_id: a.args.alert_id });
        text = <>Incident <a href={`#incidents/${r.incident.id}`}>#{r.incident.id}</a> {r.existing ? "already existed" : "opened"}.</>;
      } else {
        const r = await api.requestApproval({ action: "isolate_device", target: a.args.device_id, reason: a.args.reason,
          alert_id: a.args.alert_id, incident_id: a.args.incident_id ?? undefined, via: "ai" });
        text = <>Approval <a href="#approvals">#{r.approval.id}</a> is waiting for a person with approval rights.</>;
      }
      setActed({ ...acted, [a.tool]: { ok: true, text } });
      onDone?.();
    } catch (e) {
      setActed({ ...acted, [a.tool]: { ok: false, text: e.message } });
    }
  }
  return (
    <div className="investigation">
      <div className="inv-grid">
        <div style={{ minWidth: 0 }}>
          <div className="small muted" style={{ marginBottom: 6 }}>
            {res.question} · answered by {res.source === "offline" ? "the built-in analyst" : res.source} · investigation #{res.id}
          </div>
          {res.note && <div className="small tone-warn" style={{ marginBottom: 6 }}>{res.note}</div>}
          <Markdown text={res.answer} onCite={cite} />
          {res.proposed_actions?.length > 0 && (
            <div className="proposed">
              <div className="small"><b>Proposed actions</b> <span className="muted">· the AI does not run them; you decide</span></div>
              {res.proposed_actions.map((a) => {
                const allowed = has(a.needs);
                const done = acted[a.tool];
                return (
                  <div key={a.tool} className="proposed-row">
                    {a.tool === "create_incident" ? <FolderKanban size={14} /> : <ShieldOff size={14} />}
                    <span style={{ flex: 1 }}>{a.label}</span>
                    {done ? <span className={`small ${done.ok ? "tone-ok" : "tone-bad"}`}>{done.ok ? <CircleCheck size={12} /> : <CircleX size={12} />} {done.text}</span>
                      : <button className="btn btn-small btn-primary" disabled={!allowed} title={allowed ? "" : `Needs the '${a.needs}' permission`}
                                onClick={() => confirm(a)}>Confirm</button>}
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div style={{ minWidth: 0 }}>
          <div className="small"><b>Evidence</b> <span className="muted">({res.evidence.length})</span></div>
          <ol className="evidence-list">
            {res.evidence.map((e) => (
              <li key={e.id} ref={(el) => { refs.current[e.id] = el; }} className={hl === e.id ? "hl" : ""}>
                <span className="cite static">{e.id}</span>
                <span className="ev-kind">{KIND_LABEL[e.kind] ?? e.kind}</span>
                <span className="small">{e.text}</span>
                {e.link && (e.link.startsWith("#") ? <a className="small" href={e.link}> open</a> : <a className="small" href={e.link} target="_blank" rel="noreferrer"> <ExternalLink size={10} /></a>)}
              </li>
            ))}
          </ol>
          <div className="small" style={{ marginTop: 10 }}><b>Tool calls</b></div>
          <ol className="tool-trace">
            {res.tool_calls.map((c, i) => (
              <li key={i}><Wrench size={11} /> <span className="mono">{c.tool}</span>
                <span className="muted small">({Object.entries(c.args).map(([k, v]) => `${k}=${v}`).join(", ")})</span>
                <div className={`small ${c.error ? "tone-bad" : "muted"}`}>{c.error ?? c.summary}</div></li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}

// v2.1 AI SOC Analyst: investigations with controlled tools and cited evidence, then the free chat.
export default function AiAnalyst({ alerts }) {
  const [target, setTarget] = useState(() => (hashParams().alert ? `a:${hashParams().alert}` : hashParams().incident ? `i:${hashParams().incident}` : ""));
  const [question, setQuestion] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [history, setHistory] = useState([]);
  const [tools, setTools] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const loadHistory = () => api.aiInvestigations({}).then((r) => setHistory(r.investigations)).catch(() => {});
  useEffect(() => {
    loadHistory();
    api.aiTools().then((r) => setTools(r.tools)).catch(() => {});
    api.incidents().then((r) => setIncidents(r.incidents.filter((i) => i.status !== "resolved"))).catch(() => {});
  }, []);
  useEffect(() => { if (target) run(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(e) {
    e?.preventDefault();
    const body = target.startsWith("a:") ? { alert_id: Number(target.slice(2)) } : target.startsWith("i:") ? { incident_id: Number(target.slice(2)) } : {};
    if (question.trim()) body.question = question.trim();
    if (!Object.keys(body).length) return;
    setBusy(true);
    setErr(null);
    try {
      setRes(await api.aiInvestigate(body));
      loadHistory();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }
  const open = alerts.filter((a) => a.status === "open").slice(0, 60);

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2><Bot size={16} /> Investigate</h2>
          <span className="small muted">The analyst only reads through its tools and must cite evidence. Actions wait for you.</span>
        </div>
        <form className="filter-bar" onSubmit={run}>
          <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Alert or incident" style={{ maxWidth: 360 }}>
            <option value="">Alert or incident…</option>
            <optgroup label="Open alerts">
              {open.map((a) => <option key={a.id} value={`a:${a.id}`}>#{a.id} {a.severity} · {a.alert_type.replace(/_/g, " ")} · {a.device_id ?? "network"}</option>)}
            </optgroup>
            <optgroup label="Open incidents">
              {incidents.map((i) => <option key={i.id} value={`i:${i.id}`}>Incident #{i.id} {i.title}</option>)}
            </optgroup>
          </select>
          <input style={{ flex: 1, minWidth: 200 }} value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000}
                 placeholder="…or a question: What did IOT-003 do? Who is 203.0.113.50?" />
          <button className="btn btn-small btn-primary" disabled={busy || (!target && !question.trim())}>{busy ? "Investigating…" : "Investigate"}</button>
        </form>
        {err && <div className="tone-bad small">{err}</div>}
        {res && <Investigation res={res} onDone={loadHistory} />}
      </section>

      <div className="grid-2">
        <section className="panel">
          <h2>Past investigations</h2>
          <ul className="mini-list">
            {history.slice(0, 12).map((h) => (
              <li key={h.id}><a href="#ai" onClick={(e) => { e.preventDefault(); setRes({ ...h, note: null }); window.scrollTo(0, 0); }}>#{h.id} {h.question}</a>
                <span className="small muted push-right">{h.source} · {h.created_by} · {new Date(h.created_at).toLocaleTimeString()}</span></li>
            ))}
            {history.length === 0 && <li className="muted small">None yet.</li>}
          </ul>
        </section>
        <section className="panel">
          <h2>Tools the analyst may use</h2>
          <ul className="mini-list">
            {tools.map((t) => (
              <li key={t.name}><span className={`tool-kind ${t.kind}`}>{t.kind}</span><span className="mono small">{t.name}</span>
                <span className="small muted push-right" style={{ textAlign: "right" }}>{t.description}</span></li>
            ))}
          </ul>
        </section>
      </div>

      <AIAssistant alerts={alerts} />
    </>
  );
}
