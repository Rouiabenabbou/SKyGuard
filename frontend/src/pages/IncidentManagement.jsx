import { useCallback, useEffect, useState } from "react";
import { Bot, Check, ChevronLeft, ChevronRight, CircleCheck, CircleX, Download, Hourglass, Play, Plus, ShieldOff, SkipForward, Square, X } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { alertLabel } from "../components/AlertsPanel.jsx";
import { openDeviceViewer } from "../components/DeviceViewer.jsx";
import Markdown from "../components/Markdown.jsx";
import { Confidence, SourceBadge } from "./AlertCenter.jsx";
import { ApprovalRow } from "./Approvals.jsx";
import { Investigation } from "./AiAnalyst.jsx";

const STATUSES = ["open", "investigating", "resolved"];
const STATUS_TONE = { open: "tone-bad", investigating: "tone-warn", resolved: "tone-ok" };
const SEV = ["low", "medium", "high", "critical"];
const when = (iso) => (iso ? new Date(iso).toLocaleString() : "—");
const STEP_ICON = { done: CircleCheck, skipped: SkipForward, failed: CircleX, waiting: Hourglass, pending: Square };
const EV_LABEL = { alert: "Alert", security_event: "Security event", ioc: "IOC", ai_analysis: "AI analysis", approval: "Approval", note: "Note", intel: "Threat intel" };

function NewIncident({ alerts, onCreated }) {
  const [alertId, setAlertId] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState(null);
  const open = alerts.filter((a) => a.status === "open");
  async function create(e) {
    e.preventDefault();
    try {
      const r = await api.createIncident(alertId ? { alert_id: Number(alertId) } : { title, severity: "medium" });
      setAlertId("");
      setTitle("");
      setError(null);
      onCreated(r.incident.id);
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <form className="incident-new" onSubmit={create}>
      <select value={alertId} onChange={(e) => setAlertId(e.target.value)}>
        <option value="">New incident (no alert)</option>
        {open.map((a) => <option key={a.id} value={a.id}>#{a.id} {alertLabel(a.alert_type)} · {a.device_id ?? "network"}</option>)}
      </select>
      {!alertId && <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" required minLength={3} />}
      <button className="btn btn-small btn-primary">Open incident</button>
      {error && <span className="small tone-bad">{error}</span>}
    </form>
  );
}

function Stepper({ w, canEdit, onPhase }) {
  const [note, setNote] = useState("");
  const i = w.phases.findIndex((p) => p.current);
  const next = w.phases[i + 1];
  const prev = w.phases[i - 1];
  const needsNote = next && (next.id === "closure" || (w.phase === "containment" && !w.containment_executed));
  return (
    <div className="phase-box">
      <ol className="stepper">
        {w.phases.map((p) => (
          <li key={p.id} className={p.done ? "done" : p.current ? "current" : ""} title={p.help}>
            <span className="dot">{p.done ? <Check size={11} /> : null}</span>
            <span className="lbl">{p.label}</span>
            <span className="at">{p.at ? new Date(p.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}</span>
          </li>
        ))}
      </ol>
      <div className="small muted">{w.phases[i]?.help}</div>
      {canEdit && (
        <div className="filter-bar" style={{ marginTop: 6 }}>
          {prev && <button className="btn btn-small" onClick={() => onPhase(prev.id, note).then(() => setNote(""))}><ChevronLeft size={13} /> {prev.label}</button>}
          {next && (
            <>
              <input value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: 1, minWidth: 160 }} maxLength={2000}
                     placeholder={next.id === "closure" ? "Resolution summary (required)" : needsNote ? "No containment executed: say why (required)" : "Note (optional)"} />
              <button className="btn btn-small btn-primary" disabled={needsNote && !note.trim()} onClick={() => onPhase(next.id, note).then(() => setNote(""))}>
                {next.label} <ChevronRight size={13} /></button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function PlaybookRun({ incidentId, run, onChanged, canRun }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const step = async (s, skip = false) => {
    setBusy(true);
    try {
      await api.runStep(incidentId, run.id, s.id, { note, skip });
      setNote("");
      setErr(null);
      onChanged();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="pb-run">
      <div className="small"><b>{run.playbook_id} {run.name}</b> · {run.status} · started by {run.started_by}</div>
      <ol className="pb-steps">
        {run.steps.map((s) => {
          const Icon = STEP_ICON[s.state] ?? Square;
          const isNext = run.next === s.id && run.status === "running";
          return (
            <li key={s.id} className={`st-${s.state} ${isNext ? "next" : ""}`}>
              <Icon size={14} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div>{s.title} <span className={`step-kind k-${s.kind}`}>{s.kind}</span> <span className="small muted">{s.phase}</span></div>
                {s.help && isNext && <div className="small muted">{s.help}</div>}
                {s.note && <div className="small muted">{s.note}{s.by ? ` · ${s.by}` : ""}</div>}
                {isNext && canRun && s.state !== "waiting" && (
                  <div className="filter-bar" style={{ marginTop: 4 }}>
                    {(s.kind === "manual" || s.kind === "approval") && (
                      <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} style={{ flex: 1, minWidth: 140 }}
                             placeholder={s.kind === "manual" ? (s.action === "close" ? "Resolution summary" : "What was done") : "Reason (optional)"} />
                    )}
                    <button className="btn btn-small btn-primary" disabled={busy} onClick={() => step(s)}><Play size={12} /> {s.kind === "manual" ? "Confirm" : s.kind === "approval" ? "Request" : "Run"}</button>
                    <button className="btn btn-small" disabled={busy || !note.trim()} title="Write why first" onClick={() => step(s, true)}>Skip</button>
                  </div>
                )}
                {isNext && s.state === "waiting" && <div className="small tone-warn">Waiting for approval #{s.approval_id} (below or in Approvals).</div>}
              </div>
            </li>
          );
        })}
      </ol>
      {err && <div className="small tone-bad">{err}</div>}
    </div>
  );
}

function Detail({ id, onChanged }) {
  const { user, has } = useAuth();
  const [inc, setInc] = useState(null);
  const [w, setW] = useState(null);
  const [tab, setTab] = useState("evidence");
  const [note, setNote] = useState("");
  const [evText, setEvText] = useState("");
  const [tech, setTech] = useState("");
  const [report, setReport] = useState(null);
  const [ai, setAi] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const canEdit = has("incident");

  const load = useCallback(() => Promise.all([api.incident(id), api.workflow(id)])
    .then(([a, b]) => { setInc(a.incident); setW(b); setError(null); }).catch((e) => setError(e.message)), [id]);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);
  useEffect(() => { if (tab === "report") api.incidentReport(id).then((r) => setReport(r.markdown)).catch((e) => setError(e.message)); }, [tab, id, w?.phase]);

  const wrap = (p) => p.then(() => { setError(null); load(); onChanged(); }).catch((e) => setError(e.message));
  const update = (body) => wrap(api.updateIncident(id, body));
  const onPhase = (phase, text) => wrap(api.setPhase(id, phase, text));
  const runAi = async () => {
    setBusy(true);
    try {
      setAi(await api.aiInvestigate({ incident_id: id }));
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!inc || !w) return <div className="muted small">{error ?? "Loading…"}</div>;
  const manual = w.mitre.filter((m) => m.manual).map((m) => m.id);
  return (
    <div className="incident-detail">
      <div className="panel-head" style={{ marginBottom: 4 }}>
        <h3 style={{ margin: 0 }}><span className={`sev sev-${inc.severity}`}>{inc.severity}</span> #{inc.id} {inc.title}</h3>
        <span className={`small ${STATUS_TONE[inc.status]}`}>{inc.status}</span>
      </div>
      <div className="small muted">
        Opened by {inc.created_by || "—"} · {when(inc.created_at)}{inc.alert_id ? <> · from alert <a href={`#alerts/${inc.alert_id}`}>#{inc.alert_id}</a></> : ""}
        {inc.device_id && <> · <button className="link-btn" onClick={() => openDeviceViewer(inc.device_id)}>{inc.device_id}</button></>}
      </div>
      <div className="incident-fields">
        <label><span>Severity</span>
          <select value={inc.severity} disabled={!canEdit} onChange={(e) => update({ severity: e.target.value })}>
            {SEV.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></label>
        <label><span>Assigned to</span>
          <div className="button-row">
            <b>{inc.assignee || "nobody"}</b>
            {canEdit && user && inc.assignee !== user.username && <button className="btn btn-small" onClick={() => update({ assignee: user.username })}>Take it</button>}
            {canEdit && inc.assignee && <button className="btn btn-small" onClick={() => update({ assignee: "" })}>Unassign</button>}
          </div>
        </label>
      </div>

      <Stepper w={w} canEdit={canEdit} onPhase={onPhase} />

      <div className="grid-2" style={{ marginTop: 10 }}>
        <div>
          <div className="small"><b>Detections</b></div>
          <ul className="mini-list">
            {w.alerts.map((a) => (
              <li key={a.id}><span className={`sev sev-${a.severity}`}>{a.severity}</span><a href={`#alerts/${a.id}`}>#{a.id} {a.rule_id} {a.rule_name}</a>
                <span className="push-right"><Confidence value={a.confidence} /> <SourceBadge source={a.source} /></span></li>
            ))}
            {w.alerts.length === 0 && <li className="muted small">No alert linked.</li>}
          </ul>
        </div>
        <div>
          <div className="small"><b>MITRE ATT&amp;CK</b></div>
          <div className="mitre-chips">
            {w.mitre.map((m) => (
              <a key={m.id} className="mitre-chip" href={m.url} target="_blank" rel="noreferrer" title={`${m.name} · ${m.tactic} · ${m.from.join(", ") || "analyst"}`}>
                <b>{m.id}</b> {m.name}{m.manual && canEdit && (
                  <button className="chip-x" aria-label={`Remove ${m.id}`} onClick={(e) => { e.preventDefault(); wrap(api.setMitre(id, manual.filter((x) => x !== m.id))); }}><X size={10} /></button>)}
              </a>
            ))}
            {w.mitre.length === 0 && <span className="muted small">No technique yet.</span>}
          </div>
          {canEdit && (
            <div className="button-row" style={{ marginTop: 4 }}>
              <select value={tech} onChange={(e) => setTech(e.target.value)} aria-label="Add technique" style={{ maxWidth: 260 }}>
                <option value="">Add a technique…</option>
                {w.techniques.filter((t) => !w.mitre.some((m) => m.id === t.id)).map((t) => <option key={t.id} value={t.id}>{t.id} {t.name}</option>)}
              </select>
              <button className="btn btn-small" disabled={!tech} onClick={() => { wrap(api.setMitre(id, [...manual, tech])); setTech(""); }}><Plus size={12} /></button>
            </div>
          )}
        </div>
      </div>

      <div className="tabs" style={{ marginTop: 12 }}>
        {[["evidence", `Evidence (${w.evidence.length})`], ["response", `Response (${w.approvals.length + w.playbook_runs.length})`],
          ["ai", `AI analyst (${w.ai.length})`], ["timeline", `Timeline (${inc.notes.length})`], ["report", "Report"]].map(([k, l]) => (
          <button key={k} className={`tab ${tab === k ? "tab-active" : ""}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {tab === "evidence" && (
        <div>
          <ol className="evidence-list">
            {w.evidence.map((e) => (
              <li key={e.id}>
                <span className="cite static">E{e.id}</span><span className="ev-kind">{EV_LABEL[e.kind] ?? e.kind}</span>
                <span className="small">{e.summary}</span>
                <span className="small muted"> · {e.added_by} · {new Date(e.added_at).toLocaleTimeString()}</span>
                {e.kind === "alert" && <a className="small" href={`#alerts/${e.ref}`}> open</a>}
                {e.kind === "security_event" && <a className="small" href={`#hunting?q=id:${e.ref}`}> open</a>}
                {(e.kind === "intel" || e.kind === "ioc") && <a className="small" href={`#intel?value=${encodeURIComponent(e.ref)}`}> open</a>}
              </li>
            ))}
            {w.evidence.length === 0 && <li className="muted small">No evidence yet. Run a playbook's first step, attach events from Threat Hunting, or add a note.</li>}
          </ol>
          {canEdit && (
            <div className="filter-bar">
              <input value={evText} onChange={(e) => setEvText(e.target.value)} placeholder="Add evidence as text (what you saw, where)" style={{ flex: 1 }} maxLength={2000} />
              <button className="btn btn-small" disabled={!evText.trim()} onClick={() => wrap(api.addEvidence(id, { kind: "note", summary: evText })).then(() => setEvText(""))}>Add</button>
            </div>
          )}
        </div>
      )}

      {tab === "response" && (
        <div>
          {inc.device_id && has("contain_request") && !w.approvals.some((a) => a.status === "pending" && a.action === "isolate_device") && (
            <div className="button-row" style={{ marginBottom: 8 }}>
              <button className="btn btn-small btn-danger" onClick={() => wrap(api.requestApproval({ action: "isolate_device", target: inc.device_id,
                reason: `incident #${inc.id}: ${inc.title}`, incident_id: inc.id, alert_id: inc.alert_id ?? undefined }))}>
                <ShieldOff size={13} /> Request isolation of {inc.device_id}</button>
              <button className="btn btn-small" onClick={() => wrap(api.requestApproval({ action: "release_device", target: inc.device_id,
                reason: `incident #${inc.id}: recovery`, incident_id: inc.id }))}>Request release</button>
            </div>
          )}
          {w.approvals.map((a) => <ApprovalRow key={a.id} a={a} onChanged={load} />)}
          <div className="small" style={{ marginTop: 10 }}><b>Playbooks</b> <span className="muted">· suggested: {w.suggested_playbooks.join(", ")}</span></div>
          {has("playbook") && (
            <div className="button-row" style={{ margin: "6px 0" }}>
              {w.suggested_playbooks.filter((p) => !w.playbook_runs.some((r) => r.playbook_id === p && r.status === "running")).map((p) => (
                <button key={p} className="btn btn-small" onClick={() => wrap(api.startPlaybook(id, p))}><Play size={12} /> Start {p}</button>
              ))}
            </div>
          )}
          {w.playbook_runs.map((r) => <PlaybookRun key={r.id} incidentId={id} run={r} onChanged={() => { load(); onChanged(); }} canRun={has("playbook")} />)}
        </div>
      )}

      {tab === "ai" && (
        <div>
          <button className="btn btn-small btn-primary" disabled={busy} onClick={runAi}><Bot size={13} /> {busy ? "Investigating…" : "Investigate this incident"}</button>
          <span className="small muted"> The result is attached as evidence; proposed actions still need you.</span>
          {ai && <Investigation res={ai} onDone={load} />}
          {!ai && w.ai.slice(-1).map((x) => (
            <div key={x.id} style={{ marginTop: 8 }}>
              <div className="small muted">Last investigation #{x.id} · {x.provider} · {x.created_by} · {when(x.created_at)}</div>
              <Markdown text={x.answer} />
            </div>
          ))}
        </div>
      )}

      {tab === "timeline" && (
        <>
          <ol className="incident-timeline">
            {inc.notes.map((n) => (
              <li key={n.id} className={`kind-${n.kind}`}>
                <div className="small muted">{when(n.created_at)} · <b>{n.username || "system"}</b> · {n.kind}</div>
                <div>{n.text}</div>
              </li>
            ))}
          </ol>
          {canEdit && (
            <form className="incident-note" onSubmit={(e) => { e.preventDefault(); wrap(api.addIncidentNote(id, note)).then(() => setNote("")); }}>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What did you check or do?" rows={2} required />
              <button className="btn btn-small btn-primary">Add note</button>
            </form>
          )}
        </>
      )}

      {tab === "report" && (
        <div>
          <button className="btn btn-small" onClick={() => api.downloadReport(id).catch((e) => setError(e.message))}><Download size={13} /> Download .md</button>
          <div className="report-box">{report ? <Markdown text={report} /> : <span className="muted small">Loading…</span>}</div>
        </div>
      )}
      {error && <div className="small tone-bad">{error}</div>}
    </div>
  );
}

// v2.1 Incident Management: case list + the 7-phase workflow (detection → closure), MITRE mapping,
// evidence, approvals, playbooks, AI analysis, timeline and the report.
export default function IncidentManagement({ alerts = [], initialId = null }) {
  const { has } = useAuth();
  const [data, setData] = useState({ incidents: [], counts: {} });
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(initialId);
  const [tick, setTick] = useState(0);
  const load = useCallback(() => api.incidents(status).then(setData).catch(() => {}), [status]);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load, tick]);
  const changed = () => setTick((t) => t + 1);
  const pick = (iid) => {
    setSelected(iid);
    window.history.replaceState(null, "", `#incidents/${iid}`);
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Incidents</h2>
        <div className="seg">
          {[["", "All"], ...STATUSES.map((s) => [s, s])].map(([k, label]) => (
            <button key={k || "all"} className={`seg-btn ${status === k ? "on" : ""}`} onClick={() => setStatus(k)}>
              {label}{k && data.counts[k] != null ? ` ${data.counts[k]}` : ""}
            </button>
          ))}
        </div>
      </div>
      {has("incident") && <NewIncident alerts={alerts} onCreated={(iid) => { pick(iid); changed(); }} />}
      <div className="incident-layout">
        <ul className="incident-list">
          {data.incidents.length === 0 && <li className="muted small">No incidents.</li>}
          {data.incidents.map((i) => (
            <li key={i.id} className={selected === i.id ? "on" : ""} onClick={() => pick(i.id)}>
              <div className="incident-row"><span className={`sev sev-${i.severity}`}>{i.severity}</span><b>#{i.id} {i.title}</b></div>
              <div className="small muted"><span className={STATUS_TONE[i.status]}>{i.status}</span> · {i.assignee || "unassigned"} · {when(i.updated_at)}</div>
            </li>
          ))}
        </ul>
        <div style={{ minWidth: 0 }}>{selected ? <Detail key={selected} id={selected} onChanged={changed} /> : <div className="muted small">Choose an incident.</div>}</div>
      </div>
    </section>
  );
}
