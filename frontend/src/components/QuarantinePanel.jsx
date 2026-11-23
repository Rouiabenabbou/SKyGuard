import { useAuth } from "../auth.jsx";
import { api } from "../services/api.js";

// Active quarantines, recent history, and the auto-quarantine switch.
export default function QuarantinePanel({ quarantine, autoQuarantine, setAutoQuarantine }) {
  async function toggle() {
    const res = await api.setAutoQuarantine(!autoQuarantine);
    setAutoQuarantine(res.auto_quarantine);
  }

  const { can, isPlatform } = useAuth();
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Quarantine</h2>
        <label className="switch small">
          <input type="checkbox" checked={!!autoQuarantine} onChange={toggle} disabled={!can("admin") || !isPlatform}
                 title={can("admin") && isPlatform ? "" : "Only a platform admin can change this"} />
          <span>Auto-quarantine</span>
        </label>
      </div>
      {quarantine.active.length === 0 ? (
        <p className="muted small">No device is quarantined.</p>
      ) : (
        <ul className="q-list">
          {quarantine.active.map((r) => (
            <li key={r.id}>
              <span>🔒 <strong>{r.device_id}</strong> <span className="muted small">{r.triggered_by} · {r.reason}</span></span>
              <span className="small tone-bad">{r.blocked_messages} blocked</span>
              <button className="btn btn-small btn-primary need-operator" onClick={() => api.releaseDevice(r.device_id)}>Release</button>
            </li>
          ))}
        </ul>
      )}
      {quarantine.history.some((r) => !r.active) && (
        <details className="small">
          <summary className="muted">History ({quarantine.history.filter((r) => !r.active).length} released)</summary>
          <ul className="q-history">
            {quarantine.history.filter((r) => !r.active).map((r) => (
              <li key={r.id} className="muted">
                {r.device_id}: {new Date(r.started_at).toLocaleTimeString()} → {new Date(r.released_at).toLocaleTimeString()} · {r.blocked_messages} blocked · {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
