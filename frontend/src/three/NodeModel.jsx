import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { NODE_SCALE, STATUS_COLORS } from "./layout.js";
import Label from "./Label.jsx";
import { CoreModel, GroundStationModel, SecurityServerModel, Tower5GModel } from "./models/Infrastructure.jsx";
import IotModel from "./models/IotModels.jsx";

const UP = new THREE.Vector3(0, 1, 0);

function statusColor(node) {
  if (node.status === "quarantined") return STATUS_COLORS.quarantined;
  if (node.security_status === "suspicious") return STATUS_COLORS.suspicious;
  return STATUS_COLORS[node.status] ?? STATUS_COLORS.unknown;
}

// Realistic models of each kind of equipment (three/models). They are about 1 unit tall,
// so they are scaled down to stand on the globe.
const MODEL_SCALE = 0.075;

function Shape({ type, color, dim, device }) {
  const props = { color, dim };
  let model;
  switch (type) {
    case "ground_station": model = <GroundStationModel {...props} />; break;
    case "base_station": model = <Tower5GModel {...props} />; break;
    case "core": model = <CoreModel {...props} />; break;
    case "security_server": model = <SecurityServerModel {...props} />; break;
    default: model = <IotModel device={device} {...props} />;
  }
  return (
    <group>
      {/* status halo on the ground: easy to read even when zoomed out */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, 0]}>
        <circleGeometry args={[0.04, 32]} />
        <meshBasicMaterial color={color} transparent opacity={dim ? 0.15 : 0.35} depthWrite={false} />
      </mesh>
      <group scale={MODEL_SCALE}>{model}</group>
    </group>
  );
}

// A red rotating cage around a quarantined device.
function QuarantineCage() {
  const ref = useRef();
  useFrame(({ clock }) => {
    if (!ref.current) return;
    ref.current.rotation.y = clock.elapsedTime * 0.8;
    const s = 1 + Math.sin(clock.elapsedTime * 4) * 0.08;
    ref.current.scale.setScalar(s);
  });
  return (
    <mesh ref={ref} position={[0, 0.04, 0]}>
      <icosahedronGeometry args={[0.06, 0]} />
      <meshBasicMaterial color={STATUS_COLORS.quarantined} wireframe />
    </mesh>
  );
}

// A pulsing ring on the ground, shown for alerts and selection.
function PulseRing({ color, speed = 2 }) {
  const ref = useRef();
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = (clock.elapsedTime * speed) % 1;
    ref.current.scale.setScalar(1 + t * 1.8);
    ref.current.material.opacity = 0.7 * (1 - t);
  });
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]}>
      <ringGeometry args={[0.05, 0.065, 32]} />
      <meshBasicMaterial color={color} transparent side={THREE.DoubleSide} depthWrite={false} />
    </mesh>
  );
}

// A thin line from the equipment up to a raised label.
function LabelStem({ height, color }) {
  return (
    <mesh position={[0, height / 2, 0]}>
      <cylinderGeometry args={[0.0025, 0.0025, height, 4]} />
      <meshBasicMaterial color={color} transparent opacity={0.6} />
    </mesh>
  );
}

// One piece of equipment standing on the globe, facing "up" (away from the centre).
export default function NodeModel({ node, device, position, selected, onSelect, showLabel, labelLevel = 0 }) {
  const [hovered, setHovered] = useState(false);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(UP, position.clone().normalize());
  const color = statusColor(node);
  const dim = node.status === "offline";
  const alerting = node.status === "quarantined" || node.security_status === "suspicious" || node.status === "degraded";
  const switching = node.route_mode === "switching"; // handover in progress (Phase 8)

  return (
    <group
      position={position}
      quaternion={quaternion}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(node.node_id);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "";
      }}
      scale={(hovered || selected ? 1.25 : 1) * 1.5 * NODE_SCALE}
    >
      <Shape type={node.node_type} color={color} dim={dim} device={device ?? { device_id: node.node_id, device_name: node.name }} />
      {node.status === "quarantined" && <QuarantineCage />}
      {(alerting || selected) && <PulseRing color={selected ? "#38bdf8" : color} speed={selected ? 1 : 1.6} />}
      {switching && <PulseRing color="#22d3ee" speed={3} />}
      {/* invisible bigger sphere, makes small nodes easy to click */}
      <mesh position={[0, 0.04, 0]} visible={false}>
        <sphereGeometry args={[0.06, 8, 8]} />
      </mesh>
      {showLabel && <Label text={node.status === "quarantined" ? `${node.node_id} [Q]` : node.node_id} color={color} highlight={selected} position={[0, 0.13 + labelLevel * 0.07, 0]} height={0.03} screen />}
      {showLabel && <LabelStem height={0.13 + labelLevel * 0.07 - 0.02} color={color} />}
    </group>
  );
}
