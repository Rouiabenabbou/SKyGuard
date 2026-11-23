import { useCallback, useEffect, useState } from "react";
import { Cloud, Cpu, Download, FlaskConical, RefreshCw } from "lucide-react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";

const ago = (sec) => (sec ? `${Math.max(0, Math.round(Date.now() / 1000 - sec))} s ago` : "never");

// v2.2: Huawei Cloud IoTDA bridge, ModelArts / MindSpore anomaly model and the real-hardware lab report.
export default function HuaweiLab() {
  const { has } = useAuth();
  const [iotda, setIotda] = useState(null);
  const [ae, setAe] = useState(null);
  const [lab, setLab] = useState(null);
  const [hours, setHours] = useState(24);
  const [err, setErr] = useState(null);
  const load = useCallback(() => {
    Promise.all([api.iotdaStatus(), api.aeStatus(), api.labReport(hours)])
      .then(([i, a, l]) => { setIotda(i); setAe(a); setLab(l); setErr(null); })
      .catch((e) => setErr(e.message));
  }, [hours]);
  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);
  const reload = () => api.aeReload().then(setAe).catch((e) => setErr(e.message));

  return (
    <section className="panel">
      <div className="panel-head">
        <h2><Cloud size={16} /> Huawei Cloud and lab test</h2>
        <button className="btn btn-small" onClick={load}><RefreshCw size={13} /> Refresh</button>
      </div>
      {err && <div className="tone-bad small">{err}</div>}
      <div className="grid-2">
        <div>
          <h3 className="small"><Cloud size={13} /> IoTDA device access</h3>
          {iotda && (iotda.enabled
            ? <div className="small">On{iotda.region ? ` (${iotda.region})` : ""} · pushes received <b>{iotda.received}</b>, readings accepted <b>{iotda.accepted}</b>, rejected {iotda.rejected}
                · last {ago(iotda.last_at)}{iotda.last_device ? ` from ${iotda.last_device}` : ""}{iotda.last_error ? ` · last problem: ${iotda.last_error}` : ""}</div>
            : <div className="small muted">Off. Set IOTDA_PUSH_TOKEN in .env and add a data forwarding rule in IoTDA that pushes to {iotda.push_path}.</div>)}
          <h3 className="small" style={{ marginTop: 12 }}><Cpu size={13} /> Anomaly model (ModelArts / MindSpore)</h3>
          {ae && (ae.loaded
            ? <div className="small">Trained with <b>{ae.framework}</b> ({ae.trained_where}) on {ae.samples} readings, {ae.devices.length} devices, {new Date(ae.trained_at).toLocaleString()}
                {ae.validation && <> · false alarms {(ae.validation.false_alarm_rate * 100).toFixed(2)} %, sudden jumps caught {(ae.validation.detect_rate_4sd_jump * 100).toFixed(1)} %</>}
                <br />Checked {ae.readings_checked} readings, flagged {ae.readings_flagged}{ae.enabled ? "" : " · alerts off (AE_ENABLED=false)"}</div>
            : <div className="small muted">{ae.error}</div>)}
          {has("admin") && <button className="btn btn-small" style={{ marginTop: 6 }} onClick={reload}>Reload model file</button>}
        </div>
        <div>
          <div className="panel-head" style={{ marginBottom: 4 }}>
            <h3 className="small"><FlaskConical size={13} /> Lab test (real ESP32 only, one reading expected every {lab?.expected_interval_s ?? 5} s)</h3>
            <div className="filter-bar">
              <select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Period">
                {[1, 6, 24, 168].map((h) => <option key={h} value={h}>Last {h < 24 ? `${h} h` : `${h / 24} d`}</option>)}
              </select>
              <button className="btn btn-small" onClick={() => api.downloadLabReport(hours)}><Download size={13} /> Report</button>
            </div>
          </div>
          {lab?.note && <div className="small muted">{lab.note}</div>}
          {lab?.devices.map((d) => (
            <table key={d.device_id} className="data-table compact" style={{ marginBottom: 8 }}>
              <tbody>
                <tr><th colSpan={2}>{d.device_id} <span className="env-badge env-lab">LAB</span></th></tr>
                <tr><td>Delivery</td><td><b>{d.delivery_percent} %</b> ({d.readings} of {d.expected_readings} in {d.span_minutes} min)</td></tr>
                <tr><td>Interval mean / p95 / max</td><td>{d.interval_mean_s ?? "—"} / {d.interval_p95_s ?? "—"} / {d.interval_max_s ?? "—"} s</td></tr>
                <tr><td>Outages</td><td>{d.outages} ({d.outage_seconds} s)</td></tr>
                <tr><td>Transport</td><td>{Object.entries(d.transport).map(([k, v]) => `${k}: ${v}`).join(", ")}</td></tr>
                <tr><td>Temperature / humidity</td><td>{d.temperature.min}–{d.temperature.max} °C · {d.humidity.min}–{d.humidity.max} %</td></tr>
                <tr><td>Alerts</td><td>{Object.entries(d.alerts).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(", ") || "none"}</td></tr>
              </tbody>
            </table>
          ))}
        </div>
      </div>
    </section>
  );
}
