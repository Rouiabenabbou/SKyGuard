// Where each node sits in the 3D twin.
// v1.1: ground nodes stand at their REAL latitude / longitude (from the backend,
// editable in the dashboard) on a NASA Blue Marble globe. Nodes in the same city
// are spread a little so they don't hide each other (see spreadPositions).
import * as THREE from "three";

export const EARTH_RADIUS = 2;
export const ORBIT_RADIUS = 2.5; // satellite orbit (not to scale: a real LEO orbit would be ~2.1)
export const NODE_SCALE = 0.4; // size of the equipment models on the globe

// Fallback positions (the same places the backend seeds), used if a node has no coordinates.
export const GEO = {
  "IOT-001": { lat: 31.08, lon: -4.01 }, // desert, Erg Chebbi near Merzouga
  "IOT-002": { lat: 33.586, lon: -7.633 }, // office tower, Casablanca
  "IOT-003": { lat: 33.86, lon: -5.45 }, // livestock farm, Saïss plain near Meknès
  "ESP32-001": { lat: 34.0, lon: -6.86 }, // university lab, Rabat
  "GS-1": { lat: 32.22, lon: -7.94 }, // ground station, Benguerir
  "BS-5G": { lat: 33.573, lon: -7.59 }, // 5G tower, Casablanca
  CORE: { lat: 33.54, lon: -7.65 }, // telecom core, Casablanca
  SEC: { lat: 34.02, lon: -6.84 }, // security operations centre, Rabat
};

// The point the camera looks at (centre of the example region, Morocco).
export const REGION = { lat: 32.6, lon: -6.3 };

// Nodes closer than MIN_SEP degrees (e.g. the 5G tower, the core and an office in the
// same city) are placed on a small circle around their real point, so all stay visible.
const MIN_SEP = 1.5;
export function spreadPositions(points) {
  const ids = Object.keys(points);
  const groups = [];
  const seen = new Set();
  for (const id of ids) {
    if (seen.has(id)) continue;
    const group = [id];
    seen.add(id);
    for (const other of ids) {
      if (seen.has(other)) continue;
      if (group.some((g) => Math.hypot(points[g].lat - points[other].lat, points[g].lon - points[other].lon) < MIN_SEP)) {
        group.push(other);
        seen.add(other);
      }
    }
    groups.push(group);
  }
  const out = {};
  for (const group of groups) {
    if (group.length === 1) {
      out[group[0]] = points[group[0]];
      continue;
    }
    const lat = group.reduce((s, g) => s + points[g].lat, 0) / group.length;
    const lon = group.reduce((s, g) => s + points[g].lon, 0) / group.length;
    const r = MIN_SEP * (0.55 + group.length * 0.08);
    group.sort().forEach((g, i) => {
      const a = (i / group.length) * Math.PI * 2 + 0.6;
      out[g] = { lat: lat + r * Math.sin(a), lon: lon + (r * Math.cos(a)) / Math.cos(THREE.MathUtils.degToRad(lat)) };
    });
  }
  return out;
}

export function latLonToVector(lat, lon, radius = EARTH_RADIUS) {
  const phi = THREE.MathUtils.degToRad(lat);
  const theta = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(
    radius * Math.cos(phi) * Math.sin(theta),
    radius * Math.sin(phi),
    radius * Math.cos(phi) * Math.cos(theta)
  );
}

// Unknown devices (e.g. a newly registered one) get a free spot automatically.
export function geoFor(nodeId, index = 0) {
  return GEO[nodeId] ?? { lat: 6 + (index % 4) * 5, lon: -12 + Math.floor(index / 4) * 8 + (index % 4) * 6 };
}

// The satellite sweeps slowly back and forth over the region on a tilted orbit.
// The orbit is the circle spanned by two unit vectors: "up over the region" and "sideways".
const lonRad = THREE.MathUtils.degToRad(REGION.lon);
export const ORBIT_U = latLonToVector(REGION.lat, REGION.lon, 1).normalize();
const east = new THREE.Vector3(Math.cos(lonRad), 0, -Math.sin(lonRad));
export const ORBIT_V = east.applyAxisAngle(ORBIT_U, 0.5).normalize(); // tilt the pass a little

export function orbitPoint(angle, radius = ORBIT_RADIUS, target = new THREE.Vector3()) {
  return target
    .copy(ORBIT_U)
    .multiplyScalar(Math.cos(angle) * radius)
    .addScaledVector(ORBIT_V, Math.sin(angle) * radius);
}

export function satelliteAngle(seconds) {
  return 0.16 * Math.sin(seconds * 0.12); // radians either side of the region
}

export const STATUS_COLORS = {
  online: "#22c55e",
  degraded: "#f59e0b",
  offline: "#ef4444",
  suspicious: "#fb923c",
  quarantined: "#dc2626",
  unknown: "#94a3b8",
  backup: "#64748b",
  blocked: "#7f1d1d",
};

export const NODE_LABELS = {
  satellite: "Satellite",
  ground_station: "Ground station",
  base_station: "5G base station",
  core: "Telecom core",
  security_server: "Security server",
  iot_device: "IoT device",
};
