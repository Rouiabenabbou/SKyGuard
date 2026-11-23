// A close-up 3D view of one device or piece of equipment, with numbered parts.
import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";
import * as THREE from "three";
import { ContactShadows, OrbitControls } from "@react-three/drei";
import IotModel from "./models/IotModels.jsx";
import { CoreModel, GroundStationModel, SatelliteModel, SecurityServerModel, Tower5GModel } from "./models/Infrastructure.jsx";

// A numbered round marker for one part (drawn on a canvas, always faces the camera).
function PartMarker({ n, position, active, onClick }) {
  const texture = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const ctx = c.getContext("2d");
    ctx.beginPath();
    ctx.arc(32, 32, 28, 0, Math.PI * 2);
    ctx.fillStyle = active ? "#f59e0b" : "#0284c7";
    ctx.fill();
    ctx.lineWidth = 5;
    ctx.strokeStyle = "#ffffff";
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 30px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(n), 32, 34);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, [n, active]);
  const size = active ? 0.085 : 0.065;
  return (
    <sprite position={position} scale={[size, size, size]} renderOrder={10}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      onPointerOver={() => { document.body.style.cursor = "pointer"; }}
      onPointerOut={() => { document.body.style.cursor = ""; }}>
      <spriteMaterial map={texture} depthTest={false} transparent />
    </sprite>
  );
}

function Model({ node, device, color, dim }) {
  const props = { color, dim };
  switch (node.node_type) {
    case "satellite":
      return <group position={[0, 0.5, 0]} rotation={[0.4, 0.6, 0]} scale={0.6}><SatelliteModel {...props} /></group>;
    case "ground_station": return <GroundStationModel {...props} />;
    case "base_station": return <Tower5GModel {...props} />;
    case "core": return <CoreModel {...props} />;
    case "security_server": return <SecurityServerModel {...props} />;
    default: return <IotModel device={device} live {...props} />;
  }
}

export default function DeviceViewerScene({ node, device, color, dim, parts = [], showParts, activePart, onPart }) {
  return (
    <Canvas camera={{ position: [1.5, 1.1, 1.8], fov: 38 }} dpr={[1, 2]} shadows>
      <color attach="background" args={["#0b1220"]} />
      <ambientLight intensity={0.55} />
      <hemisphereLight args={["#e0f2fe", "#1e293b", 0.7]} />
      <directionalLight position={[3, 5, 3]} intensity={2.2} castShadow />
      <directionalLight position={[-3, 2, -2]} intensity={0.6} color="#93c5fd" />
      <group position={[0, -0.45, 0]}>
        <Model node={node} device={device} color={color} dim={dim} />
        {showParts && parts.map(([name, , pos], i) => (
          <PartMarker key={name} n={i + 1} position={pos} active={activePart === i} onClick={() => onPart(i)} />
        ))}
        <ContactShadows position={[0, 0, 0]} opacity={0.55} scale={3} blur={2.4} far={1.5} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.002, 0]}>
          <circleGeometry args={[1.4, 48]} />
          <meshStandardMaterial color="#111827" roughness={1} />
        </mesh>
      </group>
      <OrbitControls autoRotate autoRotateSpeed={0.8} enablePan={false} minDistance={0.8} maxDistance={5} target={[0, 0, 0]} makeDefault />
    </Canvas>
  );
}
