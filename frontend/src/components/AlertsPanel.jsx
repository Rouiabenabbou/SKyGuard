import { useState } from "react";
import { api } from "../services/api.js";

const TYPE_LABELS = {
  excessive_message_rate: "Excessive message rate",
  unauthorized_device: "Unauthorized device",
  abnormal_sensor_value: "Abnormal sensor value",
  suspicious_connections: "Suspicious connections",
  link_failure: "Link failure",
  node_failure: "Node failure",
  device_id_spoofing: "Device ID spoofing",
  malformed_message: "Malformed message",
  movement_detected: "Movement detected",
  ml_anomaly: "ML anomaly",
};

export const alertLabel = (type = "") =>
  TYPE_LABELS[type] ?? type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

// Live list of security alerts with a resolve button.
export default function AlertsPanel({ alerts, devices = {} }) {
  const [filter, setFilter] = useState("open");
  const shown = filter === "open" ? alerts.filter((a) => a.status === "open") : alerts;
  const open = alerts.filter((a) => a.status === "open");

  return (
    <section className="panel alerts-panel">
      <div className="panel-head">
        <h2>Security alerts</h2>
        <div className="tabs">
          <button className={`tab ${filter === "open" ? "tab-active" : ""}`} onClick={() => setFilter("open")}>
            Open ({open.length})
          </button>
          <button className={`tab ${filter === "all" ? "tab-active" : ""}`} onClick={() => setFilter("all")}>
            All ({alerts.length})
          </button>
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="muted">{filter === "open" ? "No open alerts. The network looks clean. ✅" : "No alerts yet."}</p>
      ) : (
        <ul className="alert-list">
          {shown.map((a) => (
            <li key={a.id} className={`alert-item sev-border-${a.severity} ${a.status === "resolved" ? "alert-resolved" : ""}`}>
              <div className="alert-top">
                <span className={`sev sev-${a.severity}`}>{a.severity}</span>
                <strong>{alertLabel(a.alert_type)}</strong>
                {a.device_id && <span className="tag">{a.device_id}</span>}
                <span className="muted small push-right">{new Date(a.timestamp).toLocaleTimeString()}</span>
              </div>
              <div className="alert-desc">{a.description}</div>
              <div className="alert-bottom muted small">
                #{a.id} · detected by {a.detection_method === "ml" ? "the machine-learning detector" : "the rule-based engine"}
                {a.device_id && devices[a.device_id] && devices[a.device_id].security_status !== "quarantined" && (
                  <button className="btn btn-small btn-danger push-right need-operator" onClick={() => api.quarantineDevice(a.device_id, `alert #${a.id}: ${alertLabel(a.alert_type)}`)}>
                    Quarantine {a.device_id}
                  </button>
                )}
                {a.status === "open" && (
                  <button className={`need-operator btn btn-small ${a.device_id && devices[a.device_id] && devices[a.device_id].security_status !== "quarantined" ? "" : "push-right"}`} title="Track the work on this alert in the Incidents tab"
                    onClick={() => api.createIncident({ alert_id: a.id }).then(() => { window.location.hash = "incidents"; }).catch(() => {})}>
                    + Incident</button>
                )}
                {a.status === "open" ? (
                  <button className="need-operator btn btn-small" onClick={() => api.resolveAlert(a.id)}>Resolve</button>
                ) : (
                  <span className="push-right tone-ok">resolved</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
