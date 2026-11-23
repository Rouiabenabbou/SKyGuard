import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";

// v1.1: the real places where the devices and the network equipment are, on a
// real map (satellite photos or streets). Needs internet for the map tiles.
const PLACE_ICONS = {
  farm: "🐄", company: "🏢", desert: "🏜️", lab: "🔬", ground_station: "📡", tower: "🗼",
  data_center: "🖧", soc: "🛡️", home: "🏠", factory: "🏭", hospital: "🏥", school: "🏫",
};
const TYPE_ICONS = { iot_device: "📟", ground_station: "📡", base_station: "🗼", core: "🖧", security_server: "🛡️", satellite: "🛰️" };
const STATUS_RING = { online: "#16a34a", degraded: "#d97706", offline: "#dc2626", quarantined: "#7f1d1d" };
export const PLACE_TYPES = Object.keys(PLACE_ICONS);

function iconFor(node, device) {
  const status = node.status === "quarantined" ? "quarantined" : node.status;
  const emoji = PLACE_ICONS[node.place_type] ?? TYPE_ICONS[node.node_type] ?? "📍";
  const moving = device?.motion_now ? " map-pin-motion" : "";
  return L.divIcon({
    className: "",
    html: `<div class="map-pin${moving}" style="border-color:${STATUS_RING[status] ?? "#94a3b8"}">
             <span>${emoji}</span></div><div class="map-pin-label">${node.node_id}</div>`,
    iconSize: [38, 50],
    iconAnchor: [19, 19],
    popupAnchor: [0, -18],
  });
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function popupHtml(node, device) {
  const lines = [`<b>${esc(node.name)}</b> <span class="muted">(${esc(node.node_id)})</span>`];
  if (node.address) lines.push(esc(node.address));
  lines.push(`Status: <b>${esc(node.status)}</b>${device ? ` · security: ${esc(device.security_status)}` : ""}`);
  if (device) {
    const t = device.temperature == null ? "—" : `${device.temperature.toFixed(1)} °C`;
    const h = device.humidity == null ? "—" : `${device.humidity.toFixed(1)} %`;
    lines.push(`🌡 ${t} · 💧 ${h}`);
    if (device.has_motion) lines.push(device.motion_now ? "🚨 <b>movement now</b>" : `motion sensor: quiet (${device.motion_24h ?? 0} in 24 h)`);
  }
  lines.push(`<span class="muted">${node.latitude.toFixed(5)}, ${node.longitude.toFixed(5)}</span>`);
  return lines.join("<br/>");
}

export default function RealMap({ network, devices }) {
  const { can } = useAuth();
  const boxRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null); // links (redrawn)
  const markersRef = useRef({}); // node_id -> marker (updated in place, so open popups stay open)
  const placingRef = useRef(null);
  const fittedRef = useRef(false);
  const [selected, setSelected] = useState(null);
  const [placing, setPlacing] = useState("");
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState(null);

  const nodes = useMemo(() => network?.nodes ?? [], [network]);
  const located = useMemo(() => nodes.filter((n) => n.latitude != null && n.longitude != null), [nodes]);
  const missing = nodes.filter((n) => n.latitude == null && n.node_type !== "satellite");

  // Create the map once.
  useEffect(() => {
    const map = L.map(boxRef.current, { zoomControl: true, worldCopyJump: true }).setView([32.5, -6.5], 6);
    const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19, attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    });
    const labels = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19, attribution: "Labels © Esri",
    });
    const streets = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap contributors",
    });
    const hybrid = L.layerGroup([satellite, labels]).addTo(map);
    L.control.layers({ "Satellite photo": hybrid, Streets: streets }, null, { position: "topright" }).addTo(map);
    L.control.scale({ imperial: false }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    map.on("click", (e) => placingRef.current?.(e.latlng));
    mapRef.current = map;
    return () => {
      map.remove();
      markersRef.current = {};
    };
  }, []);

  // Draw markers and ground links whenever the live data changes.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();
    const pos = Object.fromEntries(located.map((n) => [n.node_id, [n.latitude, n.longitude]]));
    for (const l of network?.links ?? []) {
      const a = pos[l.source_node];
      const b = pos[l.target_node];
      if (!a || !b) continue;
      L.polyline([a, b], {
        color: l.status === "offline" ? "#dc2626" : l.status === "degraded" ? "#d97706" : l.in_use ? "#38bdf8" : "#94a3b8",
        weight: l.in_use ? 3 : 2, dashArray: l.in_use ? null : "6 6", opacity: 0.85,
      }).bindTooltip(`${l.link_id} · ${l.link_type} · ${l.status}${l.latency_ms ? ` · ${l.latency_ms} ms` : ""}`).addTo(layer);
    }
    const markers = markersRef.current;
    const keep = new Set();
    for (const n of located) {
      keep.add(n.node_id);
      const icon = iconFor(n, devices[n.node_id]);
      const html = popupHtml(n, devices[n.node_id]);
      let m = markers[n.node_id];
      if (!m) {
        m = L.marker([n.latitude, n.longitude], { icon }).bindPopup(html).on("click", () => setSelected(n.node_id));
        m.addTo(mapRef.current);
        markers[n.node_id] = m;
      } else {
        m.setLatLng([n.latitude, n.longitude]);
        if (m._lastIcon !== icon.options.html) m.setIcon(icon);
        m.setPopupContent(html);
      }
      m._lastIcon = icon.options.html;
    }
    for (const id of Object.keys(markers)) {
      if (!keep.has(id)) {
        markers[id].remove();
        delete markers[id];
      }
    }
    if (!fittedRef.current && located.length) {
      mapRef.current.fitBounds(L.latLngBounds(located.map((n) => [n.latitude, n.longitude])).pad(0.15));
      fittedRef.current = true;
    }
  }, [network, devices, located]);

  // "Click on the map to place" mode (admin).
  useEffect(() => {
    placingRef.current = placing
      ? async (latlng) => {
          const node = nodes.find((n) => n.node_id === placing);
          try {
            await api.setProfile(placing, {
              latitude: +latlng.lat.toFixed(6), longitude: +latlng.lng.toFixed(6),
              place_type: node?.place_type ?? "", address: node?.address ?? "",
              ...(node?.node_type === "iot_device" ? { has_motion: !!devices[placing]?.has_motion } : {}),
            });
            setMsg({ ok: true, text: `${placing} moved to ${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}.` });
          } catch (e) {
            setMsg({ ok: false, text: e.message });
          }
          setPlacing("");
        }
      : null;
    if (boxRef.current) boxRef.current.style.cursor = placing ? "crosshair" : "";
  }, [placing, nodes, devices]);

  function flyTo(n) {
    setSelected(n.node_id);
    mapRef.current.flyTo([n.latitude, n.longitude], 17, { duration: 1.2 });
    markersRef.current[n.node_id]?.openPopup();
  }

  async function findPlace(e) {
    e.preventDefault();
    if (!search.trim()) return;
    try {
      // OpenStreetMap's free place search (Nominatim). Only the typed text is sent.
      const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(search)}`);
      const [hit] = await r.json();
      if (!hit) return setMsg({ ok: false, text: `No place found for "${search}".` });
      mapRef.current.flyTo([+hit.lat, +hit.lon], 15, { duration: 1.2 });
      setMsg({ ok: true, text: hit.display_name });
    } catch {
      setMsg({ ok: false, text: "Place search needs internet." });
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Real locations</h2>
      </div>
      <div className="realmap-grid">
        <div className="realmap" ref={boxRef} />
        <aside className="realmap-side">
          <form className="realmap-search" onSubmit={findPlace}>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search a place (city, farm…)" />
            <button className="btn btn-small">Go</button>
          </form>
          <ul className="realmap-list">
            {located.map((n) => {
              const d = devices[n.node_id];
              return (
                <li key={n.node_id} className={selected === n.node_id ? "active" : ""}>
                  <button className="realmap-item" onClick={() => flyTo(n)}>
                    <span className="realmap-emoji">{PLACE_ICONS[n.place_type] ?? TYPE_ICONS[n.node_type] ?? "📍"}</span>
                    <span>
                      <b>{n.node_id}</b> <span className={`small tone-${n.status === "online" ? "ok" : "bad"}`}>{n.status}</span>
                      {d?.motion_now && <span className="small tone-bad"> · movement!</span>}
                      <br /><span className="muted small">{n.address || n.place_type || n.name}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          {missing.length > 0 && <p className="muted small">No location yet: {missing.map((n) => n.node_id).join(", ")}</p>}
          {can("admin") && (
            <div className="realmap-place">
              <label className="small muted">Move a device or node: choose it, then click on the map</label>
              <select value={placing} onChange={(e) => setPlacing(e.target.value)}>
                <option value="">choose…</option>
                {nodes.filter((n) => n.node_type !== "satellite").map((n) => <option key={n.node_id} value={n.node_id}>{n.node_id}</option>)}
              </select>
              {placing && <div className="small tone-warn">Click the new position of {placing} on the map…</div>}
            </div>
          )}
          {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
        </aside>
      </div>
    </section>
  );
}
