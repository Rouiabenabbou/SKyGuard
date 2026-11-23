import { useState } from "react";
import { api } from "../services/api.js";

const EXPORTS = [
  { name: "telemetry", label: "Telemetry readings" },
  { name: "alerts", label: "Security alerts" },
  { name: "events", label: "Event log" },
  { name: "quarantine", label: "Quarantine records" },
  { name: "failover", label: "Failover records" },
  { name: "hourly", label: "Hourly summaries (big data)" },
];

function duration(s) {
  const m = Math.floor(s / 60);
  return m ? `${m} min ${s % 60} s` : `${s} s`;
}

const secs = (ms) => (ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1)} s`);

// Session report: key numbers of the current session, CSV downloads, and Print (save as PDF).
export default function ReportPanel({ summary }) {
  const [saved, setSaved] = useState(null);

  async function saveAll() {
    try {
      const res = await api.saveExport("all");
      setSaved({ ok: true, text: `Saved ${res.files.length} CSV files in ${res.folder}` });
    } catch (e) {
      setSaved({ ok: false, text: e.message });
    }
  }

  return (
    <section className="panel report">
      <div className="panel-head">
        <h2>Session report</h2>
        <div className="button-row no-print">
          <button className="btn btn-small btn-primary" onClick={() => window.print()}>Print / save as PDF</button>
        </div>
      </div>
      {!summary ? (
        <div className="muted small">Loading…</div>
      ) : (
        <>
          <p className="muted small">
            {summary.app.name} v{summary.app.version} · session #{summary.session.id ?? "—"} ({summary.session.status ?? "—"}) ·
            running for {duration(summary.session.duration_s)} · generated {new Date(summary.generated_at).toLocaleString()}
          </p>
          <div className="report-grid">
            <div><b>{summary.totals.readings}</b><span>readings stored</span></div>
            <div><b>{summary.totals.events}</b><span>events logged</span></div>
            <div><b>{summary.totals.alerts}</b><span>security alerts ({summary.totals.open_alerts} open)</span></div>
            <div><b>{summary.totals.quarantines}</b><span>quarantines</span></div>
            <div><b>{summary.totals.blocked_messages}</b><span>messages blocked</span></div>
            <div><b>{summary.network.availability_session ?? "—"}%</b><span>avg network availability</span></div>
            <div><b>{summary.failover.failovers}</b><span>failovers</span></div>
            <div><b>{secs(summary.failover.avg_interruption_ms)}</b><span>avg failover interruption</span></div>
          </div>

          <h3 className="small muted report-h">Devices</h3>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Device</th><th>Status</th><th>Security</th><th>Readings</th><th>Temp avg (min–max)</th><th>Alerts</th><th>Quarantines</th></tr>
              </thead>
              <tbody>
                {summary.devices.map((d) => (
                  <tr key={d.device_id}>
                    <td>{d.device_id} <span className="muted">{d.device_name}</span></td>
                    <td>{d.status}</td>
                    <td>{d.security_status}</td>
                    <td>{d.readings}</td>
                    <td>{d.temperature_avg ?? "—"} °C {d.temperature_min !== null && <span className="muted">({d.temperature_min}–{d.temperature_max})</span>}</td>
                    <td>{d.alerts}</td>
                    <td>{d.quarantines}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="small muted report-h">Alerts by type</h3>
          {Object.keys(summary.alerts_by_type).length === 0 ? (
            <div className="muted small">No alerts in this session.</div>
          ) : (
            <ul className="report-list small">
              {Object.entries(summary.alerts_by_type).map(([t, c]) => (
                <li key={t}>{t.replace(/_/g, " ")}: <b>{c}</b></li>
              ))}
            </ul>
          )}
          <p className="muted small">{summary.disclaimer}</p>
        </>
      )}

      <h3 className="small muted report-h no-print">Download data (CSV, opens in Excel)</h3>
      <div className="button-row no-print">
        {EXPORTS.map((e) => (
          <a key={e.name} className="btn btn-small" href={api.exportUrl(e.name)} download>
            ⬇ {e.label}
          </a>
        ))}
        <button className="btn btn-small btn-primary need-operator" onClick={saveAll}>Save all to project folder</button>
      </div>
      {saved && <div className={`small no-print ${saved.ok ? "tone-ok" : "tone-bad"}`}>{saved.text}</div>}
    </section>
  );
}
