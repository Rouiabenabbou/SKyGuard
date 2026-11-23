import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, grid, timeTick, tooltip } from "./theme.js";

// Network availability (% of non-quarantined devices that reach the core) over time.
export default function AvailabilityChart({ points, height = 180 }) {
  return (
    <div className="chart-box">
      <div className="chart-title">Network availability <span className="muted">(%)</span></div>
      {points.length < 2 ? (
        <div className="chart-empty muted small">Collecting data…</div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} tickFormatter={timeTick} {...axis} minTickGap={40} />
            <YAxis domain={[0, 100]} {...axis} width={48} />
            <Tooltip {...tooltip} labelFormatter={timeTick} formatter={(v) => [`${v}%`, "availability"]} />
            <Area type="stepAfter" dataKey="availability" stroke="#2a78d6" strokeWidth={2} fill="#2a78d6" fillOpacity={0.15} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
