import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { alertLabel } from "../AlertsPanel.jsx";
import { axis, grid, SEVERITY_COLORS, tooltip } from "./theme.js";

const SEVERITIES = ["low", "medium", "high", "critical"];
const pretty = (s) => alertLabel(s);

// Alert statistics from /api/report/summary: by type, by severity, and per minute.
export default function AlertCharts({ summary }) {
  if (!summary) return <div className="muted small">Loading statistics…</div>;
  const byType = Object.entries(summary.alerts_by_type)
    .map(([type, count]) => ({ type: pretty(type), count }))
    .sort((a, b) => b.count - a.count);
  const bySeverity = SEVERITIES.map((s) => ({ severity: s, count: summary.alerts_by_severity[s] ?? 0 }));
  const perMinute = summary.alerts_per_minute.map((p) => ({
    minute: new Date(p.minute).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    count: p.count,
  }));

  if (summary.totals.alerts === 0) {
    return <div className="chart-empty muted small">No alerts yet. Launch a simulated attack to see statistics.</div>;
  }

  return (
    <div className="chart-grid">
      <div className="chart-box">
        <div className="chart-title">Alerts by type</div>
        <ResponsiveContainer width="100%" height={Math.max(140, byType.length * 34 + 30)}>
          <BarChart data={byType} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid {...grid} horizontal={false} vertical />
            <XAxis type="number" allowDecimals={false} {...axis} />
            <YAxis type="category" dataKey="type" width={150} {...axis} />
            <Tooltip {...tooltip} cursor={{ fill: "rgba(100,116,139,0.08)" }} />
            <Bar dataKey="count" fill="#2a78d6" radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-box">
        <div className="chart-title">Alerts by severity</div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={bySeverity} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="severity" {...axis} />
            <YAxis allowDecimals={false} {...axis} />
            <Tooltip {...tooltip} cursor={{ fill: "rgba(100,116,139,0.08)" }} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} barSize={28} isAnimationActive={false}>
              {bySeverity.map((d) => (
                <Cell key={d.severity} fill={SEVERITY_COLORS[d.severity]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-box">
        <div className="chart-title">Alerts per minute</div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={perMinute} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="minute" {...axis} />
            <YAxis allowDecimals={false} {...axis} />
            <Tooltip {...tooltip} cursor={{ fill: "rgba(100,116,139,0.08)" }} />
            <Bar dataKey="count" fill="#eb6834" radius={[4, 4, 0, 0]} barSize={20} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
