import { useEffect, useState } from "react";
import { api } from "../services/api.js";

const KIND_TIP = { auto: "the system does it", approval: "needs a human approval", check: "the system verifies it", manual: "a person does it and confirms" };

// v2.1: the response playbooks. They are started from an incident (Incident Management → Response).
export default function PlaybooksPanel() {
  const [pbs, setPbs] = useState([]);
  const [open, setOpen] = useState(null);
  useEffect(() => { api.playbooks().then((r) => setPbs(r.playbooks)).catch(() => {}); }, []);
  return (
    <section className="panel">
      <div className="panel-head"><h2>Response playbooks</h2><span className="small muted">Started from an incident (Response tab)</span></div>
      <ul className="mini-list">
        {pbs.map((p) => (
          <li key={p.id} style={{ display: "block" }}>
            <a href="#automation" onClick={(e) => { e.preventDefault(); setOpen(open === p.id ? null : p.id); }}><b>{p.id}</b> {p.name}</a>
            <span className="small muted"> · {p.description}</span>
            {open === p.id && (
              <ol className="pb-steps">
                {p.steps.map((s) => (
                  <li key={s.id}><span className={`step-kind k-${s.kind}`} title={KIND_TIP[s.kind]}>{s.kind}</span>
                    <span style={{ flex: 1 }}>{s.title}</span><span className="small muted">{s.phase}</span></li>
                ))}
                {p.applies_to.length > 0 && <li className="small muted">Suggested for: {p.applies_to.join(", ")}</li>}
              </ol>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
