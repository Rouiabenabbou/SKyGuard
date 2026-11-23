import { useState } from "react";
import { api } from "../services/api.js";

// Buttons that start a simulated attack inside this project.
// The detection engine must spot each one on its own.
const ATTACKS = [
  { id: "excessive-traffic", label: "Excessive traffic", rule: "Rule A", hint: "~20 msg/s for 8 s", pickDevice: true },
  { id: "unauthorized-device", label: "Unauthorized device", rule: "Rule B", hint: "unregistered IOT-999 sends data" },
  { id: "abnormal-reading", label: "Abnormal reading", rule: "Rule C", hint: "≈85 °C, ≈2 % humidity", pickDevice: true },
  { id: "connection-storm", label: "Connection storm", rule: "Rule D", hint: "12 reconnects in 4 s", pickDevice: true },
  // v2.1: network, 5G and GNSS scenarios (security events + rules CS-011 ... CS-021)
  { id: "mqtt-brute-force", label: "MQTT brute force", rule: "CS-011 · CS-021", hint: "8 wrong passwords, then a login", pickDevice: true },
  { id: "unauthorized-publish", label: "Unauthorized publish", rule: "CS-014", hint: "rogue client writes to a command topic", pickDevice: true },
  { id: "botnet-beaconing", label: "Botnet beaconing", rule: "CS-012 · CS-018", hint: "calls a C2 server every 1.5 s", pickDevice: true },
  { id: "port-scan", label: "Port scan", rule: "CS-013", hint: "24 ports probed", pickDevice: true },
  { id: "data-exfiltration", label: "Data exfiltration", rule: "CS-015", hint: "7 MB to an outside server", pickDevice: true },
  { id: "5g-auth-attack", label: "5G authentication attack", rule: "CS-016", hint: "6 failed 5G-AKA for one SIM", pickDevice: true },
  { id: "config-tampering", label: "Config tampering", rule: "CS-017", hint: "settings pushed outside the dashboard", pickDevice: true },
  { id: "gnss-jamming", label: "GNSS jamming", rule: "CS-019", hint: "signal lost on satellite terminals", pickDevice: true },
  { id: "gnss-spoofing", label: "GNSS spoofing", rule: "CS-020", hint: "position pulled 140 km away", pickDevice: true },
];

export default function AttackPanel({ devices }) {
  const [target, setTarget] = useState("IOT-002");
  const [message, setMessage] = useState(null);

  async function launch(attack) {
    try {
      const res = await api.attack(attack.id, attack.pickDevice ? target : undefined);
      setMessage(`${attack.label} started on ${res.device_id}. Watch the alerts.`);
    } catch (e) {
      setMessage(e.message);
    }
  }

  return (
    <section className="panel need-simulate">
      <h2>Attack simulation</h2>
      <label className="small muted">
        Target device{" "}
        <select className="select" value={target} onChange={(e) => setTarget(e.target.value)}>
          {devices.map((d) => (
            <option key={d.device_id} value={d.device_id}>{d.device_id} · {d.device_name}</option>
          ))}
        </select>
      </label>
      <div className="attack-grid">
        {ATTACKS.map((a) => (
          <button key={a.id} className="attack-btn" onClick={() => launch(a)}>
            <span className="attack-rule">{a.rule}</span>
            <span className="attack-label">{a.label}</span>
            <span className="attack-hint">{a.hint}</span>
          </button>
        ))}
      </div>
      {message && <div className="small tone-warn">{message}</div>}
      <div className="small muted">Attackers use documentation addresses (203.0.113.x, 198.51.100.x) that belong to no real host; nothing leaves this project.
        See the events in <a href="#hunting">Threat Hunting</a>.</div>
    </section>
  );
}
