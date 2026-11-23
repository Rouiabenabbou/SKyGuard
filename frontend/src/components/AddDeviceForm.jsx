import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";

// Operator form: register a new IoT device. The backend creates its network node,
// its access links (satellite devices also get a backup 5G link for failover)
// and a simulated twin that starts sending readings.
const EMPTY = {
  device_id: "", device_name: "", device_type: "Environmental Sensor", location: "",
  connection_type: "satellite", access_node: "", backup_node: "",
  temp_min: 0, temp_max: 45, humidity_min: 10, humidity_max: 90, simulated: true,
  place_type: "", address: "", latitude: "", longitude: "", has_motion: false, company_id: "",
};

export default function AddDeviceForm({ network, onClose }) {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const { isPlatform, company, authEnabled } = useAuth();
  const [companies, setCompanies] = useState([]);
  useEffect(() => {
    if (isPlatform && authEnabled) api.companies().then((r) => setCompanies(r.companies)).catch(() => {});
  }, [isPlatform, authEnabled]);
  const nodes = network?.nodes ?? [];
  const satellites = nodes.filter((n) => n.node_type === "satellite");
  const towers = nodes.filter((n) => n.node_type === "base_station");
  const sat = form.connection_type === "satellite";
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function save(e) {
    e.preventDefault();
    const payload = { ...form, device_id: form.device_id.trim().toUpperCase(), company_id: form.company_id || null };
    for (const k of ["temp_min", "temp_max", "humidity_min", "humidity_max"]) payload[k] = Number(payload[k]);
    payload.latitude = form.latitude === "" ? null : Number(form.latitude);
    payload.longitude = form.longitude === "" ? null : Number(form.longitude);
    if ((payload.latitude === null) !== (payload.longitude === null)) {
      setError("Give both latitude and longitude (or leave both empty).");
      return;
    }
    if (!payload.access_node) delete payload.access_node;
    if (!sat || !payload.backup_node) delete payload.backup_node;
    setSaving(true);
    setError("");
    try {
      await api.addDevice(payload);
      onClose();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <form className="config-form" onSubmit={save}>
      <h3>Add IoT device</h3>
      <label><span>Device ID</span>
        <input value={form.device_id} onChange={set("device_id")} placeholder="IOT-004" maxLength={24} required
               pattern="[A-Za-z0-9][A-Za-z0-9\-]{2,23}" title="3-24 characters: letters, numbers and -, e.g. PIR-001" />
      </label>
      <label><span>Name</span>
        <input value={form.device_name} onChange={set("device_name")} placeholder="Water Tank 04" maxLength={100} required />
      </label>
      <label><span>Type</span>
        <input value={form.device_type} onChange={set("device_type")} maxLength={50} required />
      </label>
      <label><span>Location</span>
        <input value={form.location} onChange={set("location")} maxLength={100} />
      </label>
      {company ? (
        <div className="small muted">This device will belong to <b>{company.name}</b>.</div>
      ) : companies.length > 0 && (
        <label><span>Company (owner)</span>
          <select value={form.company_id} onChange={set("company_id")}>
            <option value="">platform (no company)</option>
            {companies.map((c) => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}
          </select>
        </label>
      )}
      <label><span>Kind of place</span>
        <select value={form.place_type} onChange={set("place_type")}>
          <option value="">—</option>
          {["farm", "company", "factory", "desert", "lab", "home", "hospital", "school"].map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
      <label><span>Address / description</span>
        <input value={form.address} onChange={set("address")} maxLength={150} placeholder="Dairy farm, Saïss plain" />
      </label>
      <div className="config-range"><span>Latitude, longitude (optional: you can also click it on the Real map)</span>
        <div><input type="number" step="any" value={form.latitude} onChange={set("latitude")} placeholder="33.86" />
          <input type="number" step="any" value={form.longitude} onChange={set("longitude")} placeholder="-5.45" /></div>
      </div>
      <label className="config-check">
        <input type="checkbox" checked={form.has_motion} onChange={set("has_motion")} />
        <span>Has a motion sensor (PIR HC-SR501)</span>
      </label>
      <label><span>Connection</span>
        <select value={form.connection_type} onChange={set("connection_type")}>
          <option value="satellite">Satellite (with 5G backup)</option>
          <option value="5g">5G</option>
        </select>
      </label>
      <label><span>{sat ? "Satellite" : "5G tower"}</span>
        <select value={form.access_node} onChange={set("access_node")}>
          <option value="">{sat ? "SAT-1 (default)" : "BS-5G (default)"}</option>
          {(sat ? satellites : towers).filter((n) => n.node_id !== (sat ? "SAT-1" : "BS-5G"))
            .map((n) => <option key={n.node_id} value={n.node_id}>{n.node_id}</option>)}
        </select>
      </label>
      {sat && (
        <label><span>Backup 5G tower (failover)</span>
          <select value={form.backup_node} onChange={set("backup_node")}>
            <option value="">BS-5G (default)</option>
            {towers.filter((n) => n.node_id !== "BS-5G").map((n) => <option key={n.node_id} value={n.node_id}>{n.node_id}</option>)}
          </select>
        </label>
      )}
      <div className="config-range"><span>Allowed temperature (°C)</span>
        <div><input type="number" step="0.5" value={form.temp_min} onChange={set("temp_min")} required /> <span className="muted">to</span>{" "}
          <input type="number" step="0.5" value={form.temp_max} onChange={set("temp_max")} required /></div>
      </div>
      <div className="config-range"><span>Allowed humidity (%)</span>
        <div><input type="number" value={form.humidity_min} onChange={set("humidity_min")} required /> <span className="muted">to</span>{" "}
          <input type="number" value={form.humidity_max} onChange={set("humidity_max")} required /></div>
      </div>
      <label className="config-check">
        <input type="checkbox" checked={form.simulated} onChange={set("simulated")} />
        <span>Simulate its readings (untick for a real board that publishes over MQTT)</span>
      </label>
      {error && <div className="config-error">{error}</div>}
      <div className="config-actions">
        <button type="button" className="btn btn-small" onClick={onClose} disabled={saving}>Cancel</button>
        <button type="submit" className="btn btn-small btn-primary" disabled={saving}>{saving ? "Adding…" : "Add device"}</button>
      </div>
    </form>
  );
}
