// Every network link with its live performance numbers.
const TONE = { online: "ok", degraded: "warn", offline: "bad" };

export default function LinkTable({ network }) {
  if (!network) return null;
  return (
    <section className="panel">
      <h2>Network links</h2>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Link</th>
              <th>From → To</th>
              <th>Type</th>
              <th>Role</th>
              <th>Status</th>
              <th>Latency</th>
              <th>Loss</th>
              <th>Bandwidth</th>
            </tr>
          </thead>
          <tbody>
            {network.links.map((l) => (
              <tr key={l.link_id}>
                <td>{l.link_id}</td>
                <td>{l.source_node} → {l.target_node}</td>
                <td>{l.link_type}</td>
                <td className="muted">{l.is_active_path ? "primary" : "backup"}</td>
                <td className={`tone-${TONE[l.status]}`}>{l.status}{l.rain_fade ? " 🌧" : ""}</td>
                <td>{l.status === "offline" ? "—" : `${l.latency_ms} ms`}</td>
                <td>{l.packet_loss}%</td>
                <td>{l.bandwidth_mbps >= 1000 ? `${(l.bandwidth_mbps / 1000).toFixed(1)} Gbps` : `${l.bandwidth_mbps} Mbps`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
