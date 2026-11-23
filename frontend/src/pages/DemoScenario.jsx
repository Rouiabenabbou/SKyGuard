import { useCallback, useEffect, useState } from "react";
import { Check, CircleX, Hourglass, Loader, Play } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { ApprovalRow } from "./Approvals.jsx";

const ICON = { done: Check, failed: CircleX, waiting: Hourglass, running: Loader };

// v2.1 end-to-end demo: simulated MQTT attack -> ingestion -> detection -> incident -> AI analysis
// -> human approval -> containment -> eradication -> recovery -> closure + report.
export default function DemoScenario() {
  const { has, isPlatform } = useAuth();
  const [data, setData] = useState(null);
  const [approval, setApproval] = useState(null);
  const [err, setErr] = useState(null);
  const load = useCallback(() => api.demo().then((r) => { setData(r); setErr(null); }).catch((e) => setErr(e.message)), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [load]);
  const run = data?.run;
  useEffect(() => {
    if (run?.status === "waiting" && run.approval_id) {
      api.approvals("pending").then((r) => setApproval(r.approvals.find((a) => a.id === run.approval_id) ?? null)).catch(() => {});
    } else setApproval(null);
  }, [run?.status, run?.approval_id]);

  const start = () => api.startDemo().then(load).catch((e) => setErr(e.message));
  const active = run && (run.status === "running" || run.status === "waiting");
  const steps = run?.steps ?? data?.steps?.map((s) => ({ ...s, state: "pending" })) ?? [];

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>End-to-end demo scenario <span className="muted small">target {data?.target ?? "IOT-002"} · everything simulated</span></h2>
        <button className="btn btn-primary" disabled={active || !has("simulate") || !isPlatform} onClick={start}><Play size={14} /> {run ? "Run again" : "Start demo"}</button>
      </div>
      <p className="small muted" style={{ marginTop: 0 }}>
        A brute-force attack takes over a device's MQTT account and sends rogue commands. The rules detect it, an incident is
        opened, the AI analyst investigates with its tools, and the isolation <b>waits for your approval</b>. After you approve,
        the rest (containment, eradication, recovery, closure, report) runs by itself.
      </p>
      {err && <div className="tone-bad small">{err}</div>}
      <ol className="demo-steps">
        {steps.map((s, i) => {
          const Icon = ICON[s.state];
          return (
            <li key={s.id} className={`st-${s.state}`}>
              <span className="num">{Icon ? <Icon size={14} className={s.state === "running" ? "spin" : ""} /> : i + 1}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div><b>{s.label}</b> <span className="small muted">{s.state}{s.at ? ` · ${new Date(s.at).toLocaleTimeString()}` : ""}</span></div>
                {s.text && <div className="small">{s.text} {s.link && (s.link.startsWith("/api/")
                  ? <button className="link-btn" onClick={() => api.downloadReport(run.incident_id)}>download report</button>
                  : <a href={s.link}>open</a>)}</div>}
                {s.id === "approval" && s.state === "waiting" && approval && <ApprovalRow a={approval} onChanged={load} />}
              </div>
            </li>
          );
        })}
      </ol>
      {run && <div className="small muted">Run #{run.id} by {run.started_by} · {run.status}{run.finished_at ? ` · finished ${new Date(run.finished_at).toLocaleTimeString()}` : ""}
        {run.incident_id && <> · <a href={`#incidents/${run.incident_id}`}>incident #{run.incident_id}</a></>}</div>}
    </section>
  );
}
