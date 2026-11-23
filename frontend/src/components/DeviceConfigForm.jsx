import { useState } from "react";
import { api } from "../services/api.js";

// Settings a network security operator can change for one device.
// The device ID and its network links are fixed.
const TEXT_FIELDS = [
  ["device_name", "Name"],
  ["device_type", "Type"],
  ["location", "Location"],
];

export default function DeviceConfigForm({ device, onClose }) {
  const [form, setForm] = useState({
    device_name: device.device_name,
    device_type: device.device_type,
    location: device.location ?? "",
    temp_min: device.ranges.temperature[0],
    temp_max: device.ranges.temperature[1],
    humidity_min: device.ranges.humidity[0],
    humidity_max: device.ranges.humidity[1],
  });
  // v1.1: real location and sensors (saved with PUT /api/profiles/{id})
  const [where, setWhere] = useState({
    latitude: device.latitude ?? "", longitude: device.longitude ?? "", place_type: device.place_type ?? "",
    address: device.address ?? "", has_motion: !!device.has_motion,
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function save(e) {
    e.preventDefault();
    const payload = { ...form };
    for (const key of ["temp_min", "temp_max", "humidity_min", "humidity_max"]) {
      payload[key] = Number(payload[key]);
      if (form[key] === "" || Number.isNaN(payload[key])) {
        setError("All limits must be numbers.");
        return;
      }
    }
    const lat = where.latitude === "" ? null : Number(where.latitude);
    const lon = where.longitude === "" ? null : Number(where.longitude);
    if ((lat === null) !== (lon === null) || Number.isNaN(lat) || Number.isNaN(lon)) {
      setError("Give both latitude and longitude (or leave both empty).");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.configureDevice(device.device_id, payload);
      await api.setProfile(device.device_id, { latitude: lat, longitude: lon, place_type: where.place_type,
                                               address: where.address, has_motion: where.has_motion });
      onClose();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  const numberInput = (key, step = "0.5") => (
    <input type="number" step={step} value={form[key]} onChange={set(key)} required />
  );

  return (
    <form className="config-form" onSubmit={save}>
      <h3>Configure {device.device_id}</h3>
      {TEXT_FIELDS.map(([key, label]) => (
        <label key={key}>
          <span>{label}</span>
          <input type="text" value={form[key]} onChange={set(key)} maxLength={key === "device_type" ? 50 : 100}
                 required={key !== "location"} />
        </label>
      ))}
      <div className="config-range">
        <span>Allowed temperature (°C)</span>
        <div>{numberInput("temp_min")} <span className="muted">to</span> {numberInput("temp_max")}</div>
      </div>
      <div className="config-range">
        <span>Allowed humidity (%)</span>
        <div>{numberInput("humidity_min", "1")} <span className="muted">to</span> {numberInput("humidity_max", "1")}</div>
      </div>
      <h4 className="config-sub">Real location</h4>
      <label>
        <span>Kind of place</span>
        <select value={where.place_type} onChange={(e) => setWhere({ ...where, place_type: e.target.value })}>
          <option value="">—</option>
          {["farm", "company", "factory", "desert", "lab", "home", "hospital", "school"].map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
      <label>
        <span>Address / description</span>
        <input value={where.address} maxLength={150} onChange={(e) => setWhere({ ...where, address: e.target.value })} />
      </label>
      <div className="config-range">
        <span>Latitude, longitude (tip: right-click a place in Google Maps to copy them)</span>
        <div>
          <input type="number" step="any" placeholder="33.8615" value={where.latitude} onChange={(e) => setWhere({ ...where, latitude: e.target.value })} />
          <input type="number" step="any" placeholder="-5.4489" value={where.longitude} onChange={(e) => setWhere({ ...where, longitude: e.target.value })} />
        </div>
      </div>
      <label className="config-check">
        <input type="checkbox" checked={where.has_motion} onChange={(e) => setWhere({ ...where, has_motion: e.target.checked })} />
        <span>Has a motion sensor (PIR HC-SR501): movement at night raises an alert</span>
      </label>
      <p className="muted small">
        Connection: {device.connection_type === "satellite" ? "Satellite" : "5G"} (set by the network topology)
      </p>
      {error && <div className="config-error">{error}</div>}
      <div className="config-actions">
        <button type="button" className="btn btn-small" onClick={onClose} disabled={saving}>Cancel</button>
        <button type="submit" className="btn btn-small btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}
