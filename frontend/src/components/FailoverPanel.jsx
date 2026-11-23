import { useAuth } from "../auth.jsx";
import { useState } from "react";
import { api } from "../services/api.js";
import { MODE_LABELS } from "./NetworkPanel.jsx";

const KIND_TONE = { failover: "warn", failback: "ok", outage: "bad" };

function secs(ms) {
  return ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1)} s`;
}

// Satellite -> 5G failover: on/off switch, outage drill, each device's path and statistics.
export default function FailoverPanel({ failover, network }) {
  const { has, isPlatform } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const status = failover?.status;
  const history = failover?.history ?? [];

  const run = (promise) => {
    setBusy(true);
    promise.then(() => setError(null)).catch((e) => setError(e.message)).finally(() => setBusy(false));
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Satellite → 5G failover</h2>
        <label className="switch small">
          <input
            type="checkbox"
            className="switch-ok"
            checked={!!status?.enabled}
            disabled={!status || busy || !has("respond") || !isPlatform}
            onChange={(e) => run(api.setFailover(e.target.checked))}
          />
          Automatic failover
        </label>
      </div>

      <div className="button-row">
        <button className="btn btn-warn need-operator need-platform" disabled={busy || status?.drill_active} onClick={() => run(api.failoverDrill(30))}>
          {status?.drill_active ? `Drill running… ${status.drill_seconds_left}s` : "Satellite outage drill (30 s)"}
        </button>
      </div>
      {error && <div className="tone-bad small">{error}</div>}

      <div className="fo-stats">
        <div><span className="fo-num">{status?.stats.failovers ?? 0}</span><span className="muted small">failovers</span></div>
        <div><span className="fo-num">{secs(status?.stats.avg_handover_ms)}</span><span className="muted small">avg handover</span></div>
        <div><span className="fo-num">{secs(status?.stats.avg_interruption_ms)}</span><span className="muted small">avg interruption</span></div>
        <div>
          <span className={`fo-num ${status?.stats.readings_lost ? "tone-warn" : ""}`}>{status?.stats.readings_lost ?? 0}</span>
          <span className="muted small">readings lost</span>
        </div>
      </div>

      <div className="fo-devices">
        {Object.entries(network?.routes ?? {}).map(([id, r]) => (
          <div key={id} className="fo-device">
            <span className="route-id">{id}</span>
            <span className={`mode-badge mode-${r.mode}`}>{r.mode === "quarantined" ? "quarantined" : MODE_LABELS[r.mode] ?? r.mode}</span>
            <span className="muted small">{r.connected ? `${r.access} · ${r.latency_ms} ms` : r.mode === "switching" ? "handover…" : "no path"}</span>
            <span className="muted small">{status?.devices[id]?.lost_readings ?? 0} lost</span>
          </div>
        ))}
      </div>

      <h3 className="small muted fo-h">Recent failover events</h3>
      {history.length === 0 ? (
        <div className="muted small">No failovers yet.</div>
      ) : (
        <ul className="fo-list">
          {history.slice(0, 8).map((e) => (
            <li key={e.id}>
              <span className={`tone-${KIND_TONE[e.kind]}`}>{e.kind}</span>
              <span>{e.device_id}</span>
              <span className="muted">{e.reason}</span>
              <span className="muted">
                {e.completed_at
                  ? `handover ${secs(e.handover_ms)} · cut ${secs(e.interruption_ms)} · ${e.readings_lost} lost`
                  : "in progress…"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
