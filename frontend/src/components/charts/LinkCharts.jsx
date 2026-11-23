import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../services/api.js";
import { axis, grid, timeTick, tooltip } from "./theme.js";

function SmallLine({ data, dataKey, title, unit, color }) {
  return (
    <div className="chart-box">
      <div className="chart-title">{title} <span className="muted">({unit})</span></div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={timeTick} {...axis} minTickGap={40} />
          <YAxis {...axis} width={48} />
          <Tooltip {...tooltip} labelFormatter={timeTick} formatter={(v) => [`${v} ${unit}`, title]} />
          <Line dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} type="monotone" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// Latency and packet loss of one link, from the link_metrics history in the database.
// Two separate charts (never two y-axes on one chart).
export default function LinkCharts({ network }) {
  const links = network?.links ?? [];
  const [linkId, setLinkId] = useState("L-SAT-GS");
  const [data, setData] = useState([]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .linkHistory(linkId, 100)
        .then((h) => !cancelled && setData(h.history.map((r) => ({ ...r, t: Date.parse(r.timestamp) }))))
        .catch(() => {});
    load();
    const timer = setInterval(load, 6000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [linkId]);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Link performance history</h2>
        <label className="small muted">
          Link
          <select className="select" value={linkId} onChange={(e) => setLinkId(e.target.value)}>
            {links.map((l) => (
              <option key={l.link_id} value={l.link_id}>{l.link_id} ({l.link_type})</option>
            ))}
          </select>
        </label>
      </div>
      {data.length < 2 ? (
        <div className="chart-empty muted small">History is stored every ~6 s while the simulation runs. Collecting…</div>
      ) : (
        <div className="chart-grid">
          <SmallLine data={data} dataKey="latency_ms" title="Latency" unit="ms" color="#2a78d6" />
          <SmallLine data={data} dataKey="packet_loss" title="Packet loss" unit="%" color="#eb6834" />
        </div>
      )}
    </section>
  );
}
