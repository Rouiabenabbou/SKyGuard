import { RadioTower, Satellite } from "lucide-react";
import { useState } from "react";
import Sparkline from "./Sparkline.jsx";
import DeviceConfigForm from "./DeviceConfigForm.jsx";
import { timeAgo } from "../hooks/useNow.js";
import { api } from "../services/api.js";
import { openDeviceViewer } from "./DeviceViewer.jsx";


function batteryTone(level) {
  if (level === null || level === undefined) return "neutral";
  if (level < 30) return "bad";
  if (level < 60) return "warn";
  return "ok";
}

const fmt = (value, unit) => (value === null || value === undefined ? "—" : `${value.toFixed(1)}${unit}`);

export default function DeviceCard({ device, history, now, quarantineRecord }) {
  const online = device.status === "online";
  const quarantined = device.security_status === "quarantined";
  const temps = history.map((r) => r.temperature);
  const [tMin, tMax] = device.ranges.temperature;
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <article className="device-card">
        <DeviceConfigForm device={device} onClose={() => setEditing(false)} />
      </article>
    );
  }

  return (
    <article className={`device-card ${online ? "" : "device-offline"} ${quarantined ? "device-quarantined" : ""}`}>
      {quarantined && (
        <div className="quarantine-banner">
          QUARANTINED · traffic blocked
          {quarantineRecord && (
            <span className="small"> · {quarantineRecord.blocked_messages} msgs blocked · {quarantineRecord.triggered_by === "auto" ? "auto" : "manual"}: {quarantineRecord.reason}</span>
          )}
        </div>
      )}
      <div className="device-head">
        <div className="device-icon">{device.connection_type === "satellite" ? <Satellite size={20} /> : <RadioTower size={20} />}</div>
        <div className="device-title">
          <h3>{device.device_name}</h3>
          <div className="muted small">
            {device.device_id} · {device.device_type}
          </div>
        </div>
        <span className={`status-badge ${online ? "status-online" : "status-offline"}`}>{device.status}</span>
      </div>

      <div className="device-metrics">
        <div>
          <div className="metric-label">Temperature</div>
          <div className="metric-value">{fmt(device.temperature, "°C")}</div>
        </div>
        <div>
          <div className="metric-label">Humidity</div>
          <div className="metric-value">{fmt(device.humidity, "%")}</div>
        </div>
      </div>

      {device.has_motion && (
        <div className={`motion-row ${device.motion_now ? "motion-active" : ""}`}>
          <span>{device.motion_now ? "Movement detected now" : "Motion sensor: quiet"}</span>
          <span className="muted small">{device.motion_24h ?? 0} in 24 h</span>
          <button className="btn btn-small need-operator" title="Simulate a person or animal moving at night"
                  onClick={() => api.simulateMotion(device.device_id, true)}>Simulate night movement</button>
        </div>
      )}

      <div className="metric-label">
        Temperature trend <span className="muted">(allowed {tMin}–{tMax}°C)</span>
      </div>
      <Sparkline values={temps} />

      <div className="metric-label">Battery {fmt(device.battery, "%")}</div>
      <div className="battery">
        <div className={`battery-fill bg-${batteryTone(device.battery)}`} style={{ width: `${device.battery ?? 0}%` }} />
      </div>

      <div className="device-footer">
        <span className={`tag ${device.connection_type === "satellite" ? "tag-sat" : "tag-5g"}`}>
          {device.connection_type === "satellite" ? "Satellite" : "5G"}
        </span>
        <span className={`tag sec-${device.security_status}`}>security: {device.security_status}</span>
        <span className="muted small push-right">
          {device.message_count} msgs · {timeAgo(device.last_seen, now)}
        </span>
      </div>
      <div className="device-actions">
        <span className="muted small" title={device.latitude != null ? `${device.latitude}, ${device.longitude}` : ""}>
          {device.address || device.location}</span>
        <button className="btn btn-small" title="See the device's 3D model and hardware" onClick={() => openDeviceViewer(device.device_id)}>3D</button>
        <button className="btn btn-small need-admin" title="Edit this device's settings" onClick={() => setEditing(true)}>Configure</button>
        {device.added_by_operator && (
          <button className="btn btn-small need-admin" title="Remove this device (only devices you added)"
                  onClick={() => window.confirm(`Remove ${device.device_id}? Its old readings stay in the history.`) && api.removeDevice(device.device_id)}>
            Remove
          </button>
        )}
        {quarantined ? (
          <button className="btn btn-small btn-primary push-right need-operator" onClick={() => api.releaseDevice(device.device_id)}>Release</button>
        ) : (
          <>
            {device.security_status === "suspicious" && (
              <button className="btn btn-small push-right need-operator" onClick={() => api.releaseDevice(device.device_id)}>Mark safe</button>
            )}
            <button className={`need-operator btn btn-small btn-danger ${device.security_status === "suspicious" ? "" : "push-right"}`}
                    onClick={() => api.quarantineDevice(device.device_id)}>Quarantine</button>
          </>
        )}
      </div>
    </article>
  );
}
