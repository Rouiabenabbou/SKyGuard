import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import Earth from "./Earth.jsx";
import OrbitRing from "./OrbitRing.jsx";
import Satellite from "./Satellite.jsx";
import NodeModel from "./NodeModel.jsx";
import LinkLine from "./LinkLine.jsx";
import { GEO, geoFor, latLonToVector, orbitPoint, REGION, spreadPositions } from "./layout.js";

// The camera looks at the region from a little to the south, so the region sits
// near the top edge of the globe and the satellite shows up against space.
const REGION_DIR = latLonToVector(REGION.lat, REGION.lon, 1).normalize();
const CAMERA_POSITION = latLonToVector(REGION.lat - 7, REGION.lon, 2.95).toArray();
const CAMERA_TARGET = REGION_DIR.clone().multiplyScalar(2.08).toArray();

// Links that carry traffic right now: every hop on a device's route,
// plus the core -> security server link (monitoring traffic is always on).
export function linksInUse(network) {
  const used = new Set();
  Object.values(network?.routes ?? {}).forEach((r) => (r.links ?? []).forEach((id) => used.add(id)));
  (network?.links ?? []).forEach((l) => {
    if (l.link_type === "lan" && l.status !== "offline") used.add(l.link_id);
    if (l.in_use) used.add(l.link_id);
  });
  return used;
}

// v2.0: "Zoom to" flies the camera close to one node (smoothly), so crowded areas get room.
function FocusCamera({ focus, positions, satellitePositions }) {
  const controls = useThree((s) => s.controls);
  const camera = useThree((s) => s.camera);
  const goal = useRef(null);
  useEffect(() => {
    if (!focus?.id) return;
    const p = positions[focus.id] ?? satellitePositions.current[focus.id];
    if (!p) return;
    const target = p.clone();
    const out = target.clone().normalize();
    // stand a little above and south of the node, looking at it
    const cam = target.clone().add(out.multiplyScalar(focus.distance ?? 0.32)).add(new THREE.Vector3(0, -0.12, 0));
    goal.current = { target, cam };
  }, [focus, positions, satellitePositions]);
  useFrame(() => {
    if (!goal.current || !controls) return;
    controls.target.lerp(goal.current.target, 0.12);
    camera.position.lerp(goal.current.cam, 0.12);
    controls.update();
    if (camera.position.distanceTo(goal.current.cam) < 0.002) goal.current = null;
  });
  return null;
}

function Scene({ network, devices, selectedId, onSelect, showLabels, focus }) {
  // One moving position per satellite (an added satellite flies a little behind SAT-1).
  const satellitePositions = useRef({});
  const satelliteIds = (network?.nodes ?? []).filter((n) => n.node_type === "satellite").map((n) => n.node_id).sort();
  satelliteIds.forEach((id, i) => {
    if (!satellitePositions.current[id]) satellitePositions.current[id] = orbitPoint(i * 0.5);
  });
  const satelliteIndex = Object.fromEntries(satelliteIds.map((id, i) => [id, i]));

  // A fixed 3D position for every ground node (the satellite's one moves).
  // Real coordinates from the backend (v1.1), else the fallback table.
  const geoKey = (network?.nodes ?? []).map((n) => `${n.node_id}:${n.latitude ?? ""}:${n.longitude ?? ""}`).join(",");
  const positions = useMemo(() => {
    const map = {};
    const ground = {};
    let extra = 0;
    (network?.nodes ?? []).forEach((n) => {
      if (n.node_type === "satellite") map[n.node_id] = satellitePositions.current[n.node_id];
      else if (n.latitude != null && n.longitude != null) ground[n.node_id] = { lat: n.latitude, lon: n.longitude };
      else {
        ground[n.node_id] = geoFor(n.node_id, extra);
        if (!GEO[n.node_id]) extra += 1;
      }
    });
    const spread = spreadPositions(ground);
    for (const [id, g] of Object.entries(spread)) map[id] = latLonToVector(g.lat, g.lon);
    return map;
    // positions only depend on which nodes exist and where, not on their status
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geoKey]);

  // Labels of nodes that are close together sit at different heights so they don't cover each other.
  const labelLift = useMemo(() => {
    const ids = Object.keys(positions).filter((id) => !satelliteIndex.hasOwnProperty(id));
    const lift = {};
    const placed = [];
    ids.sort().forEach((id) => {
      const near = placed.filter((o) => positions[o].distanceTo(positions[id]) < 0.05).map((o) => lift[o]);
      let level = 0;
      while (near.includes(level)) level += 1;
      lift[id] = level;
      placed.push(id);
    });
    return lift;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions]);

  const used = linksInUse(network);
  const nodes = (network?.nodes ?? []).map((n) => ({
    ...n,
    security_status: devices[n.node_id]?.security_status,
    route_mode: network.routes?.[n.node_id]?.mode, // primary | backup | switching | down (Phase 8)
  }));

  return (
    <>
      <color attach="background" args={["#030712"]} />
      <ambientLight intensity={0.45} />
      <hemisphereLight args={["#bae6fd", "#0f172a", 0.6]} />
      <directionalLight position={[6, 5, 6]} intensity={1.8} />
      <directionalLight position={[-4, 2, -3]} intensity={0.4} color="#93c5fd" />
      <Stars radius={60} depth={30} count={2500} factor={3} fade speed={0.4} />
      <Earth />
      <OrbitRing />
      {nodes.map((n) =>
        n.node_type === "satellite" ? (
          <Satellite key={n.node_id} node={n} positionRef={{ current: satellitePositions.current[n.node_id] }} offset={satelliteIndex[n.node_id] * 0.5} selected={selectedId === n.node_id} onSelect={onSelect} showLabel={showLabels} />
        ) : (
          <NodeModel key={n.node_id} node={n} device={devices[n.node_id]} position={positions[n.node_id]} selected={selectedId === n.node_id} onSelect={onSelect} showLabel={showLabels} labelLevel={labelLift[n.node_id] ?? 0} />
        )
      )}
      {(network?.links ?? []).map((l) =>
        positions[l.source_node] && positions[l.target_node] ? (
          <LinkLine
            key={l.link_id}
            link={l}
            inUse={used.has(l.link_id)}
            positions={positions}
            selected={selectedId && (l.source_node === selectedId || l.target_node === selectedId)}
          />
        ) : null
      )}
      <OrbitControls target={CAMERA_TARGET} enablePan screenSpacePanning zoomToCursor zoomSpeed={1.2} minDistance={0.05} maxDistance={9} enableDamping makeDefault />
      <FocusCamera focus={focus} positions={positions} satellitePositions={satellitePositions} />
    </>
  );
}

// The 3D digital twin. `network` is the same snapshot the 2D map uses
// (live, or a past moment when the timeline is replaying in Phase 9).
export default function TwinScene(props) {
  return (
    <Canvas
      camera={{ position: CAMERA_POSITION, fov: 40, near: 0.005, far: 200 }}
      dpr={[1, 2]}
      onPointerMissed={() => props.onSelect(null)}
      fallback={<div className="twin-fallback">3D view needs WebGL. Try Chrome or Edge with hardware acceleration on.</div>}
    >
      <Scene {...props} />
    </Canvas>
  );
}
