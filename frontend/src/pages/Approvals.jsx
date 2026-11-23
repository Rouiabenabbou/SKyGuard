import { useCallback, useEffect, useState } from "react";
import { CircleCheck, CircleX, Hourglass, ShieldCheck } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";

const STATUS_TONE = { pending: "tone-warn", executed: "tone-ok", approved: "tone-ok", rejected: "muted", failed: "tone-bad" };
const when = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

// One containment request with approve / reject (two-factor code when the approver has it on).
export function ApprovalRow({ a, actions, onChanged }) {
  const { has, user } = useAuth();
  const [note, setNote] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const decide = async (ok) => {
    setBusy(true);
    try {
      await (ok ? api.approve(a.id, note, code || undefined) : api.reject(a.id, note));
      setErr(null);
      onChanged?.();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  const Icon = a.status === "pending" ? Hourglass : a.status === "executed" ? CircleCheck : CircleX;
  return (
    <div className={`approval ${a.status}`}>
      <div className="approval-head">
        <Icon size={15} className={STATUS_TONE[a.status]} />
        <b>#{a.id} {actions?.[a.action] ?? a.action} <span className="mono">{a.target}</span></b>
        <span className={`small ${STATUS_TONE[a.status]}`}>{a.status}</span>
        <span className="small muted push-right">{when(a.created_at)}</span>
      </div>
      <div className="small">{a.reason}</div>
      <div className="small muted">
        Requested by <b>{a.requested_by}</b> via {a.requested_via}
        {a.incident_id && <> · incident <a href={`#incidents/${a.incident_id}`}>#{a.incident_id}</a></>}
        {a.alert_id && <> · alert <a href={`#alerts/${a.alert_id}`}>#{a.alert_id}</a></>}
        {a.decided_by && <> · {a.status} by <b>{a.decided_by}</b> {when(a.decided_at)}</>}
        {a.result && <> · {a.result}</>}
        {a.decision_note && <> · “{a.decision_note}”</>}
      </div>
      {a.status === "pending" && has("contain_approve") && (
        <div className="filter-bar" style={{ marginTop: 6 }}>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Decision note (optional)" style={{ flex: 1, minWidth: 140 }} maxLength={2000} />
          {user?.mfa_enabled && <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="2FA code" inputMode="numeric" maxLength={7} style={{ width: 90 }} />}
          <button className="btn btn-small btn-primary" disabled={busy} onClick={() => decide(true)}><ShieldCheck size={13} /> Approve</button>
          <button className="btn btn-small" disabled={busy} onClick={() => decide(false)}>Reject</button>
        </div>
      )}
      {a.status === "pending" && !has("contain_approve") && <div className="small muted">Waiting for an L3 analyst, the SOC manager, an operator or an admin.</div>}
      {err && <div className="small tone-bad">{err}</div>}
    </div>
  );
}

// v2.1 Approvals: sensitive response actions (device isolation / release) wait here for a human decision.
export default function Approvals() {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("pending");
  const [err, setErr] = useState(null);
  const load = useCallback(() => api.approvals(filter === "all" ? undefined : filter).then((r) => { setData(r); setErr(null); })
    .catch((e) => setErr(e.message)), [filter]);
  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Containment approvals {data && <span className="muted small">{data.pending} pending</span>}</h2>
        <div className="seg">
          {["pending", "executed", "rejected", "failed", "all"].map((s) => (
            <button key={s} className={`seg-btn ${filter === s ? "on" : ""}`} onClick={() => setFilter(s)}>{s}</button>
          ))}
        </div>
      </div>
      <p className="small muted" style={{ marginTop: 0 }}>
        Isolating or releasing a device on request (L2 analyst, playbook, AI analyst, demo) waits here. Approving runs the
        simulated quarantine. {data?.two_person_rule ? "Two-person rule is on: nobody approves their own request." : "Two-person rule is off (APPROVAL_TWO_PERSON=true switches it on)."}
      </p>
      {err && <div className="tone-bad small">{err}</div>}
      {data?.approvals.map((a) => <ApprovalRow key={a.id} a={a} actions={data.actions} onChanged={load} />)}
      {data && data.approvals.length === 0 && <div className="empty">Nothing here.</div>}
    </section>
  );
}
