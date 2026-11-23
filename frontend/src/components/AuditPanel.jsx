import { useEffect, useState } from "react";
import { api } from "../services/api.js";

const timeOf = (iso) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString();

// Admin: the security audit log, who did what and when (refreshes every 5 s).
export default function AuditPanel() {
  const [entries, setEntries] = useState([]);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState(null);
  const [chain, setChain] = useState(null);
  const verify = () => api.auditVerify().then(setChain).catch((e) => setError(e.message));

  useEffect(() => {
    let alive = true;
    const load = () => api.audit(300).then((r) => alive && setEntries(r.entries)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const shown = filter === "all" ? entries : entries.filter((e) => e.outcome !== "ok");
  const problems = entries.filter((e) => e.outcome !== "ok").length;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Security audit log</h2>
        <div className="button-row">
          <button className={`tab ${filter === "all" ? "tab-active" : ""}`} onClick={() => setFilter("all")}>All ({entries.length})</button>
          <button className={`tab ${filter === "problems" ? "tab-active" : ""}`} onClick={() => setFilter("problems")}>
            Denied / failed ({problems})</button>
          <button className="btn btn-small" onClick={verify} title="Recompute the SHA-256 hash chain over every audit row">Verify integrity</button>
          <a className="btn btn-small" href={api.auditCsvUrl()} download>CSV</a>
        </div>
      </div>
      {chain && (
        <div className={`chain-result ${chain.ok ? "ok" : "bad"}`}>
          {chain.ok ? <>Hash chain intact: {chain.checked} of {chain.total} rows verified · last hash <span className="mono">{chain.last_hash.slice(0, 16)}…</span></>
            : <>Tampering detected at row #{chain.broken_at}: {chain.problem}. {chain.checked} rows before it are intact.</>}
          <span className="muted small"> · checked {new Date(chain.checked_at).toLocaleTimeString()}</span>
        </div>
      )}
      {error && <div className="config-error">{error}</div>}
      <div className="table-wrap audit-wrap">
        <table className="table">
          <thead><tr><th>Time</th><th>User</th><th>Role</th><th>Action</th><th>Result</th><th>Request</th><th>IP</th></tr></thead>
          <tbody>
            {shown.map((e) => (
              <tr key={e.id}>
                <td className="small nowrap">{timeOf(e.timestamp)}</td>
                <td><b>{e.username}</b></td>
                <td className="small">{e.role}</td>
                <td>{e.action}</td>
                <td className={e.outcome === "ok" ? "tone-ok" : "tone-bad"}>{e.outcome} <span className="muted small">{e.status_code}</span></td>
                <td className="small muted mono">{e.method} {e.path}</td>
                <td className="small muted">{e.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
