import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";
import { HARDWARE, INFRA_HARDWARE, iotKind } from "../three/models/catalog.js";
import { STATUS_COLORS } from "../three/layout.js";

const Scene = lazy(() => import("../three/DeviceViewerScene.jsx"));
const OPEN_EVENT = "cybershield:view-device";

// Open the 3D model viewer for a device or network node from anywhere in the app.
export function openDeviceViewer(nodeId) {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: nodeId }));
}

const fmt = (v, unit, digits = 1) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(digits)}${unit}`);

function statusColor(node, device) {
  if (device?.security_status === "quarantined" || node?.status === "quarantined") return STATUS_COLORS.quarantined;
  if (device?.security_status === "suspicious") return STATUS_COLORS.suspicious;
  return STATUS_COLORS[node?.status] ?? STATUS_COLORS.unknown;
}

// Full-screen close-up of one device: rotating 3D model with numbered parts,
// live values, the hardware spec sheet and quick engineer actions.
export default function DeviceViewer({ network, devices }) {
  const [nodeId, setNodeId] = useState(null);
  const [showParts, setShowParts] = useState(true);
  const [activePart, setActivePart] = useState(null);
  const [ops, setOps] = useState(null);
  const [msg, setMsg] = useState(null);
  const { can, has } = useAuth();

  useEffect(() => {
    const open = (e) => {
      setNodeId(e.detail);
      setActivePart(null);
      setMsg(null);
    };
    window.addEventListener(OPEN_EVENT, open);
    return () => window.removeEventListener(OPEN_EVENT, open);
  }, []);

  useEffect(() => {
    if (!nodeId) return undefined;
    const onKey = (e) => e.key === "Escape" && setNodeId(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nodeId]);

  const node = network?.nodes.find((n) => n.node_id === nodeId);
  const device = devices?.[nodeId];
  const isDevice = node?.node_type === "iot_device" || !!device;

  useEffect(() => {
    if (!nodeId || !isDevice) return;
    api.engineeringDevices().then((d) => setOps(d.devices.find((x) => x.device_id === nodeId) ?? null)).catch(() => setOps(null));
  }, [nodeId, isDevice, msg]);

  if (!nodeId || !node) return null;
  const hw = isDevice ? HARDWARE[iotKind(device ?? { device_id: nodeId })] : INFRA_HARDWARE[node.node_type];
  const parts = hw?.parts ?? [];
  const route = network.routes?.[nodeId];
  const color = statusColor(node, device);

  const run = async (promise, ok) => {
    try {
      await promise;
      setMsg({ ok: true, text: ok });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  };

  return (
    <div className="viewer-backdrop" onClick={() => setNodeId(null)}>
      <div className="viewer" role="dialog" aria-label={`3D model of ${nodeId}`} onClick={(e) => e.stopPropagation()}>
        <div className="viewer-head">
          <div>
            <h2>{device?.device_name ?? node.name}</h2>
            <div className="muted small">{nodeId} · {hw?.title}</div>
          </div>
          <div className="button-row">
            <span className="status-chip" style={{ "--chip": color }}>{device?.security_status === "quarantined" ? "quarantined" : node.status}</span>
            {ops?.maintenance && <span className="status-chip" style={{ "--chip": "#d97706" }}>maintenance</span>}
            <button className="btn btn-small" onClick={() => setNodeId(null)} aria-label="Close">✕</button>
          </div>
        </div>

        <div className="viewer-body">
          <div className="viewer-canvas">
            <Suspense fallback={<div className="twin-fallback">Loading 3D model…</div>}>
              <Scene node={node} device={device} color={color} dim={node.status === "offline"} parts={parts}
                     showParts={showParts} activePart={activePart} onPart={setActivePart} />
            </Suspense>
            <label className="switch small viewer-toggle">
              <input type="checkbox" checked={showParts} onChange={(e) => setShowParts(e.target.checked)} /> Parts
            </label>
          </div>

          <div className="viewer-side">
            {isDevice && (
              <div className="viewer-live">
                <div><span>Temperature</span><b>{fmt(device?.temperature, " °C")}</b></div>
                <div><span>Humidity</span><b>{fmt(device?.humidity, " %")}</b></div>
                <div><span>Battery</span><b>{fmt(device?.battery, " %", 0)}</b></div>
                <div><span>Link</span><b>{route?.connected ? `${route.access} · ${route.latency_ms} ms` : route?.quarantined ? "blocked" : "down"}</b></div>
                <div><span>Signal</span><b>{ops?.signal_dbm != null ? `${ops.signal_dbm} dBm` : "—"}</b></div>
                <div><span>Firmware</span><b>{ops?.firmware ?? "—"}</b></div>
              </div>
            )}

            <h3>Parts</h3>
            <ol className="part-list">
              {parts.map(([name, what], i) => (
                <li key={name} className={activePart === i ? "on" : ""} onClick={() => setActivePart(i)}>
                  <b>{name}</b> <span className="muted">{what}</span>
                </li>
              ))}
            </ol>

            <h3>Specifications</h3>
            <table className="spec-table">
              <tbody>
                {(hw?.specs ?? []).map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}
                {device?.location && <tr><th>Location</th><td>{device.address || device.location}</td></tr>}
              </tbody>
            </table>

            {isDevice && has("respond") && (
              <div className="button-row viewer-actions">
                <button className="btn btn-small" disabled={!!ops?.busy} onClick={() => run(api.rebootDevice(nodeId), `${nodeId} is rebooting (simulated).`)}>⟳ Reboot</button>
                {ops && ops.firmware !== ops.latest_firmware && can("admin") && (
                  <button className="btn btn-small" disabled={!!ops?.busy} onClick={() => run(api.updateFirmware(nodeId, ops.latest_firmware), `Updating ${nodeId} to ${ops.latest_firmware}…`)}>
                    ⬆ Firmware {ops.latest_firmware}</button>
                )}
                <button className="btn btn-small" onClick={() => run(api.setMaintenance(nodeId, !ops?.maintenance, "from the 3D viewer"),
                  ops?.maintenance ? "Maintenance ended." : "Maintenance on: no phone alarm for this device.")}>
                  {ops?.maintenance ? "End maintenance" : "Maintenance"}</button>
                <button className="btn btn-small btn-danger" onClick={() => run(api.createIncident({ title: `Check ${nodeId} (${device?.device_name ?? ""})`, device_id: nodeId, severity: "medium" }), "Incident opened (see the Incidents tab).")}>
                  + Incident</button>
              </div>
            )}
            {ops?.busy && <div className="small tone-warn">{ops.busy.action === "firmware" ? `Flashing firmware ${ops.busy.target}…` : "Rebooting…"}</div>}
            {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
