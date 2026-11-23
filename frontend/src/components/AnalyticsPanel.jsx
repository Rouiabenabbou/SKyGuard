import { useCallback, useEffect, useMemo, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { alertLabel } from "./AlertsPanel.jsx";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { axis, deviceColor, grid, legend, SEVERITY_COLORS, tooltip } from "./charts/theme.js";

// v1.3: long-term data ("big data") - months of hourly summaries, trends, an attack
// heatmap and a 24 h forecast. A company user only sees its own devices.
const METRICS = {
  temp_avg: { label: "Temperature", unit: "°C" },
  hum_avg: { label: "Humidity", unit: "%" },
  battery_avg: { label: "Battery", unit: "%" },
};
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const fmtInt = (n) => (n ?? 0).toLocaleString();
const fmtBytes = (b) => (b == null ? "—" : b > 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${(b / 1e6).toFixed(1)} MB`);
const dayTick = (ms) => new Date(ms).toLocaleDateString([], { month: "short", day: "numeric" });
const hourTick = (ms) => new Date(ms).toLocaleString([], { weekday: "short", hour: "2-digit" });

function Kpi({ label, value, hint }) {
  return (
    <div className="card">
      <div className="card-label">{label}</div>
      <div className="card-value">{value}</div>
      {hint && <div className="card-hint">{hint}</div>}
    </div>
  );
}

function HistoryControls({ job, onChange }) {
  const [days, setDays] = useState(90);
  const [interval, setInterval_] = useState(5);
  const [msg, setMsg] = useState(null);
  const estimate = days * 24 * Math.floor(60 / interval);

  const run = async (promise, ok) => {
    try {
      await promise;
      setMsg({ ok: true, text: ok });
      onChange();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  };

  return (
    <section className="panel need-admin need-platform">
      <div className="panel-head">
        <h2>Long-term history</h2>
      </div>
      <div className="assign-row">
        <label className="small">Days&nbsp;
          <select value={days} onChange={(e) => setDays(+e.target.value)}>
            {[7, 30, 90, 180, 365].map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <label className="small">One reading every&nbsp;
          <select value={interval} onChange={(e) => setInterval_(+e.target.value)}>
            {[1, 5, 10, 30].map((m) => <option key={m} value={m}>{m} min</option>)}
          </select>
        </label>
        <span className="small muted">≈ {fmtInt(estimate)} readings per device</span>
        <button className="btn btn-small btn-primary" disabled={job?.running}
                onClick={() => run(api.generateHistory(days, interval), "Generating… this takes a few seconds.")}>
          Generate history</button>
        <button className="btn btn-small" onClick={() => run(api.rollupNow(), "Live readings summarised.")}>Summarise live data now</button>
        <button className="btn btn-small btn-danger" disabled={job?.running}
                onClick={() => window.confirm("Delete the whole long-term history?") && run(api.deleteHistory(), "History deleted.")}>
          Delete history</button>
      </div>
      {job && (job.running || job.message !== "idle") && (
        <div className="small" style={{ marginTop: 8 }}>
          <div className="progress"><div style={{ width: `${Math.round((job.progress ?? 0) * 100)}%` }} /></div>
          {job.running ? `${Math.round(job.progress * 100)} % · ${job.message} · ${fmtInt(job.rows)} readings` : `${job.message}${job.seconds ? ` in ${job.seconds} s` : ""}`}
        </div>
      )}
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </section>
  );
}

function Heatmap({ data }) {
  const max = Math.max(1, ...data.heatmap.flat());
  return (
    <div className="heatmap-wrap">
      <table className="heatmap">
        <thead><tr><th />{Array.from({ length: 24 }, (_, h) => <th key={h}>{h % 3 === 0 ? h : ""}</th>)}</tr></thead>
        <tbody>
          {data.heatmap.map((row, d) => (
            <tr key={d}>
              <th>{DAYS[d]}</th>
              {row.map((n, h) => (
                <td key={h} title={`${DAYS[d]} ${h}:00 UTC: ${n} alerts`}
                    style={{ background: n ? `rgba(220, 38, 38, ${0.12 + 0.88 * (n / max)})` : undefined }} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AnalyticsPanel({ devices }) {
  const { can, isPlatform } = useAuth();
  const [days, setDays] = useState(30);
  const [metric, setMetric] = useState("temp_avg");
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [fcDevice, setFcDevice] = useState("");
  const [fc, setFc] = useState(null);
  const [error, setError] = useState(null);

  const deviceIds = useMemo(() => Object.keys(devices).sort(), [devices]);
  const device = fcDevice || deviceIds[0] || "";

  const load = useCallback(async () => {
    try {
      const [s, t, a] = await Promise.all([api.analyticsSummary(), api.analyticsTrends(days, days <= 7 ? "hour" : "day"), api.analyticsAlerts(days)]);
      setSummary(s);
      setTrends(t);
      setAlerts(a);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  // while history is generated, poll the progress and reload when done
  useEffect(() => {
    if (!summary?.job?.running) return undefined;
    const id = setInterval(async () => {
      const job = await api.historyStatus().catch(() => null);
      if (job && !job.running) load();
      else if (job) setSummary((s) => ({ ...s, job }));
    }, 1000);
    return () => clearInterval(id);
  }, [summary?.job?.running, load]);

  useEffect(() => {
    if (device) api.analyticsForecast(device).then(setFc).catch(() => setFc(null));
  }, [device, summary?.hourly_rows]);

  const seriesIds = Object.keys(trends?.series ?? {}).sort();
  const m = METRICS[metric];
  const fcData = fc?.enough_data
    ? [...(fc.history ?? []).map((p) => ({ t: Date.parse(p.t), actual: metric === "hum_avg" ? p.hum : p.temp })),
      ...fc.points.map((p) => {
        const key = metric === "hum_avg" ? "hum" : "temp";
        return { t: Date.parse(p.t), forecast: p[key], band: [p[`${key}_low`], p[`${key}_high`]] };
      })]
    : [];

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>Analytics (long-term data)</h2>
          <div className="assign-row" style={{ marginTop: 0 }}>
            <select value={days} onChange={(e) => setDays(+e.target.value)}>
              {[7, 30, 90, 180, 365].map((d) => <option key={d} value={d}>last {d} days</option>)}
            </select>
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              {Object.entries(METRICS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>
        {error && <div className="small tone-bad">{error}</div>}
        {summary && (
          <div className="card-grid">
            <Kpi label="Raw readings" value={fmtInt(summary.raw_readings.total)} hint={`${fmtInt(summary.raw_readings.archive)} history · ${fmtInt(summary.raw_readings.live)} live`} />
            <Kpi label="Days of data" value={summary.days_covered} hint={summary.first_hour ? `since ${new Date(summary.first_hour).toLocaleDateString()}` : "no history yet"} />
            <Kpi label="Hourly summaries" value={fmtInt(summary.hourly_rows)} hint="what Analytics reads (fast)" />
            <Kpi label="Alerts in history" value={fmtInt(summary.alerts_total)} />
            <Kpi label="Database" value={summary.database} hint={isPlatform ? fmtBytes(summary.database_bytes) : "your company's data only"} />
          </div>
        )}
        {summary && summary.hourly_rows === 0 && (
          <p className="muted small">No long-term data yet. {can("admin") && isPlatform ? "Use “Generate history” below, or let the simulation run (live readings are summarised every 5 minutes)." : "Live readings are summarised every 5 minutes."}</p>
        )}
      </section>

      {can("admin") && <HistoryControls job={summary?.job} onChange={load} />}

      <div className="two-col">
        <section className="panel">
          <div className="chart-title">{m.label} per {days <= 7 ? "hour" : "day"} <span className="muted">({m.unit}, average)</span></div>
          {seriesIds.length === 0 ? <div className="chart-empty muted small">No data for this period.</div> : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={days <= 7 ? hourTick : dayTick} {...axis} minTickGap={40} />
                <YAxis {...axis} width={48} domain={["auto", "auto"]} />
                <Tooltip {...tooltip} labelFormatter={(v) => new Date(v).toLocaleString()} formatter={(v, n) => [`${v} ${m.unit}`, n]} />
                <Legend {...legend} />
                {seriesIds.map((id) => (
                  <Line key={id} name={id} data={trends.series[id].map((p) => ({ t: Date.parse(p.t), v: p[metric] }))} dataKey="v"
                        stroke={deviceColor(id, seriesIds)} strokeWidth={2} dot={false} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="panel">
          <div className="chart-title">Alerts per day <span className="muted">(by severity)</span></div>
          {!alerts?.per_day?.length ? <div className="chart-empty muted small">No alerts in this period.</div> : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={alerts.per_day.map((d) => ({ ...d, t: Date.parse(d.day) }))} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={dayTick} {...axis} minTickGap={40} />
                <YAxis {...axis} width={40} allowDecimals={false} />
                <Tooltip {...tooltip} labelFormatter={(v) => new Date(v).toLocaleDateString()} cursor={{ fill: "rgba(148,163,184,0.15)" }} />
                <Legend {...legend} iconType="square" />
                {["low", "medium", "high", "critical"].map((s) => <Bar key={s} dataKey={s} stackId="a" fill={SEVERITY_COLORS[s]} isAnimationActive={false} />)}
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>
      </div>

      <div className="two-col">
        <section className="panel">
          <div className="chart-title">When do attacks happen? <span className="muted">(alerts by weekday and hour, UTC)</span></div>
          {alerts && alerts.total > 0 ? (
            <>
              <Heatmap data={alerts} />
              {alerts.peak && <p className="small">Busiest time: <b>{DAYS[alerts.peak.weekday]} {alerts.peak.hour}:00–{alerts.peak.hour + 1}:00 UTC</b> ({alerts.peak.count} alerts). Plan extra monitoring then.</p>}
              <ul className="small analytics-types">
                {alerts.by_type.slice(0, 6).map((t) => <li key={t.alert_type}><span>{alertLabel(t.alert_type)}</span><b>{t.count}</b></li>)}
              </ul>
            </>
          ) : <div className="chart-empty muted small">No alerts in this period.</div>}
        </section>

        <section className="panel">
          <div className="panel-head" style={{ marginBottom: 4 }}>
            <div className="chart-title">Forecast: next 24 h <span className="muted">({metric === "hum_avg" ? "humidity, %" : "temperature, °C"})</span></div>
            <select value={device} onChange={(e) => setFcDevice(e.target.value)}>
              {deviceIds.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </div>
          {!fc ? <div className="chart-empty muted small">Loading…</div> : !fc.enough_data ? <div className="chart-empty muted small">{fc.message}</div> : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={fcData} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid {...grid} />
                  <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={hourTick} {...axis} minTickGap={40} />
                  <YAxis {...axis} width={48} domain={["auto", "auto"]} />
                  <Tooltip {...tooltip} labelFormatter={(v) => new Date(v).toLocaleString()}
                           formatter={(v, n) => [Array.isArray(v) ? `${v[0]} – ${v[1]}` : v, n]} />
                  <Legend {...legend} />
                  <Area dataKey="band" name="95 % range" stroke="none" fill="#2a78d6" fillOpacity={0.15} isAnimationActive={false} />
                  <Line dataKey="actual" name="last 48 h" stroke="#64748b" strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Line dataKey="forecast" name="forecast" stroke="#2a78d6" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
              <p className="muted small">Trend: {fc.trend_per_day.temp > 0 ? "+" : ""}{fc.trend_per_day.temp} °C/day · {fc.method}.</p>
              {fc.warnings.length > 0 && <ul className="small tone-warn">{fc.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
            </>
          )}
        </section>
      </div>
    </>
  );
}
