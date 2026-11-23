import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, deviceColor, grid, legend, timeTick, tooltip } from "./theme.js";

const WINDOW_MS = 5 * 60 * 1000;

const METRICS = {
  temperature: { label: "Temperature", unit: "°C" },
  humidity: { label: "Humidity", unit: "%" },
  battery: { label: "Battery", unit: "%" },
};

// One line per device for one sensor metric (last readings kept in the browser).
const FEW = 6; // with many devices, show a few by default (v1.5)

export default function TelemetryChart({ history, metric = "temperature", height = 220 }) {
  const [show, setShow] = useState("few");
  const allIds = Object.keys(history).sort();
  const ids = show === "all" ? allIds : show === "few" ? allIds.slice(0, FEW) : allIds.filter((id) => id === show);
  const m = METRICS[metric];
  // only the last 5 minutes, so a device that went silent doesn't stretch the time axis
  const latest = Math.max(0, ...ids.flatMap((id) => (history[id] ?? []).map((r) => Date.parse(r.timestamp))));
  const series = ids.map((id) => ({
    id,
    data: (history[id] ?? [])
      .map((r) => ({ t: Date.parse(r.timestamp), v: r[metric] }))
      .filter((p) => p.t >= latest - WINDOW_MS),
  }));
  const empty = series.every((s) => s.data.length === 0);

  return (
    <div className="chart-box">
      <div className="chart-title chart-title-row">
        <span>{m.label} <span className="muted">({m.unit})</span></span>
        {allIds.length > FEW && (
          <select className="chart-pick" value={show} onChange={(e) => setShow(e.target.value)} aria-label={`${m.label} devices`}>
            <option value="few">First {FEW} devices</option>
            <option value="all">All {allIds.length} devices</option>
            {allIds.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        )}
      </div>
      {empty ? (
        <div className="chart-empty muted small">Waiting for readings…</div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={timeTick} {...axis} minTickGap={40} />
            <YAxis {...axis} width={48} domain={["auto", "auto"]} />
            <Tooltip {...tooltip} labelFormatter={timeTick} formatter={(v, name) => [`${v} ${m.unit}`, name]} />
            <Legend {...legend} />
            {series.map((s) => (
              <Line
                key={s.id}
                data={s.data}
                dataKey="v"
                name={s.id}
                type="monotone"
                stroke={deviceColor(s.id, allIds)}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
