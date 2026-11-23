import { useEffect, useState } from "react";
import { Locate, Radio, Satellite } from "lucide-react";
import { api } from "../services/api.js";
import FailoverPanel from "../components/FailoverPanel.jsx";
import LinkCharts from "../components/charts/LinkCharts.jsx";
import LinkTable from "../components/LinkTable.jsx";
import { SourceBadge } from "./AlertCenter.jsx";

const TONE = { online: "tone-ok", degraded: "tone-warn", offline: "tone-bad" };

function Segment({ title, icon: Icon, nodes, links }) {
  return (
    <section className="panel">
      <h2><Icon size={16} /> {title}</h2>
      <div className="table-wrap">
        <table className="data-table compact">
          <thead><tr><th>Node</th><th>Status</th><th>Links up</th><th>Avg latency</th><th>Max loss</th></tr></thead>
          <tbody>
            {nodes.map((n) => {
              const ls = links.filter((l) => l.source_node === n.node_id || l.target_node === n.node_id);
              const up = ls.filter((l) => l.status !== "offline");
              const lat = up.length ? (up.reduce((s, l) => s + l.latency_ms, 0) / up.length).toFixed(1) : "—";
              const loss = ls.length ? Math.max(...ls.map((l) => l.packet_loss)).toFixed(2) : "—";
              return (
                <tr key={n.node_id}>
                  <td><div className="mono">{n.node_id}</div><div className="small muted">{n.name}</div></td>
                  <td className={TONE[n.status] ?? ""}>{n.status}</td>
                  <td>{up.length}/{ls.length}</td>
                  <td>{lat} ms</td>
                  <td className={loss !== "—" && loss > 2 ? "tone-warn" : ""}>{loss}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const GNSS_TONE = { normal: "tone-ok", jammed: "tone-bad", spoofed: "tone-bad" };

// v2.1: GNSS integrity of every satellite terminal (simulated receiver values) + jamming / spoofing detections.
function GnssPanel() {
  const [g, setG] = useState(null);
  useEffect(() => {
    const load = () => api.gnss().then(setG).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);
  if (!g) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2><Locate size={16} /> GNSS integrity <span className="muted small">{g.devices.length} satellite terminals</span></h2>
        <span className="small muted">{g.note} Jamming: C/N0 &lt; {g.thresholds.min_cn0} dB-Hz and no fix · spoofing: &gt; {g.thresholds.max_offset_km} km from the installed place or &gt; {g.thresholds.max_speed_mps} m/s</span>
      </div>
      <div className="grid-main-side">
        <div className="table-wrap" style={{ maxHeight: 320 }}>
          <table className="data-table compact">
            <thead><tr><th>Terminal</th><th>State</th><th>C/N0 dB-Hz</th><th>Satellites</th><th>HDOP</th><th>Fix</th><th>Offset km</th><th>Clock µs</th><th>Src</th></tr></thead>
            <tbody>
              {g.devices.map((d) => (
                <tr key={d.device_id}>
                  <td><div className="mono">{d.device_id}</div><div className="small muted">{d.device_name}</div></td>
                  <td className={GNSS_TONE[d.state]}>{d.state}</td>
                  <td className={d.cn0 < g.thresholds.min_cn0 ? "tone-bad" : d.cn0 > 49 ? "tone-warn" : ""}>{d.cn0}</td>
                  <td>{d.satellites}</td>
                  <td>{d.hdop}</td>
                  <td className={d.fix ? "tone-ok" : "tone-bad"}>{d.fix ? "yes" : "lost"}</td>
                  <td className={d.offset_km > g.thresholds.max_offset_km ? "tone-bad" : ""}>{d.offset_km}</td>
                  <td>{d.clock_offset_us}</td>
                  <td><SourceBadge source={d.source} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="small"><b>Jamming / spoofing alerts · 24 h</b></div>
          {g.alerts.length === 0 ? <div className="empty">None. Try “GNSS jamming” or “GNSS spoofing” in Attack Simulation.</div> : (
            <ul className="mini-list">
              {g.alerts.slice(0, 10).map((a) => (
                <li key={a.id}><span className={`sev sev-${a.severity}`}>{a.severity}</span><a href={`#alerts/${a.id}`}>#{a.id} {a.rule_id}</a>
                  <span className="small" style={{ flex: 1 }}>{a.description}</span></li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

// v2.0 Satellite & 5G Security: space segment, ground segment and RAN health from the live
// (simulated) network snapshot, failover state and the network-fault detections.
export default function SatcomSecurity({ network, failover }) {
  const [faults, setFaults] = useState([]);
  useEffect(() => {
    const load = () => Promise.all([api.socAlerts({ rule_id: "CS-007", hours: 24 }), api.socAlerts({ rule_id: "CS-008", hours: 24 })])
      .then(([a, b]) => setFaults([...a.alerts, ...b.alerts].sort((x, y) => y.id - x.id))).catch(() => {});
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);
  if (!network) return <section className="panel"><div className="muted">Waiting for network data…</div></section>;
  const by = (t) => network.nodes.filter((n) => n.node_type === t);
  return (
    <>
      <div className="grid-3">
        <Segment title="Space segment" icon={Satellite} nodes={by("satellite")} links={network.links} />
        <Segment title="Ground stations" icon={Radio} nodes={by("ground_station")} links={network.links} />
        <Segment title="5G RAN and core" icon={Radio} nodes={[...by("base_station"), ...by("core")]} links={network.links} />
      </div>
      <div className="grid-main-side">
        <FailoverPanel failover={failover} network={network} />
        <section className="panel">
          <h2>Link and node faults · 24 h</h2>
          {faults.length === 0 ? <div className="empty">No link or node went down in the last 24 h.</div> : (
            <ul className="mini-list">
              {faults.slice(0, 15).map((a) => (
                <li key={a.id}><span className={`sev sev-${a.severity}`}>{a.severity}</span><a href={`#alerts/${a.id}`}>#{a.id}</a>
                  <span className="small" style={{ flex: 1 }}>{a.description}</span><SourceBadge source={a.source} /></li>
              ))}
            </ul>
          )}
          <div className="small muted" style={{ marginTop: 8 }}>
            5G authentication attacks (CS-016) and GNSS interference (CS-019, CS-020) are detected from simulated core and
            receiver logs; with real equipment the same rules would read the AMF/AUSF log and the receiver's NMEA/UBX output.
          </div>
        </section>
      </div>
      <GnssPanel />
      <LinkCharts network={network} />
      <LinkTable network={network} />
    </>
  );
}
