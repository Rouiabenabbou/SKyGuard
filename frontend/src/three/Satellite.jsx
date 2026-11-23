import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { NODE_SCALE, orbitPoint, satelliteAngle, STATUS_COLORS } from "./layout.js";
import Label from "./Label.jsx";
import { SatelliteModel } from "./models/Infrastructure.jsx";

// The satellite moves along its orbit and writes its position into `positionRef`,
// so the links attached to it can follow it every frame.
export default function Satellite({ node, positionRef, offset = 0, selected, onSelect, showLabel }) {
  const group = useRef(); // follows the orbit
  const body = useRef(); // turns to face the Earth
  const [hovered, setHovered] = useState(false);
  const color = STATUS_COLORS[node.status] ?? STATUS_COLORS.unknown;
  const dim = node.status === "offline";

  useFrame(({ clock }) => {
    const p = orbitPoint(satelliteAngle(clock.elapsedTime) + offset, undefined, positionRef.current);
    if (group.current) group.current.position.copy(p);
    if (body.current) {
      body.current.lookAt(0, 0, 0); // antenna points at the Earth
      body.current.rotateZ(clock.elapsedTime * 0.2);
    }
  });

  return (
    <group
      ref={group}
      scale={(hovered || selected ? 1.25 : 1) * NODE_SCALE * 0.8}
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
    >
      <group ref={body}>
      <group scale={0.16}>
        <SatelliteModel color={color} dim={dim} />
      </group>
      </group>
      <mesh visible={false}>
        <sphereGeometry args={[0.2, 8, 8]} />
      </mesh>
      {showLabel && <Label text={node.status === "quarantined" ? `${node.node_id} [Q]` : node.node_id} color={color} highlight={selected} position={[0, 0.2, 0]} />}
    </group>
  );
}
