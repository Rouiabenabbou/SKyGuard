import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { QuadraticBezierLine } from "@react-three/drei";
import * as THREE from "three";
import { EARTH_RADIUS, STATUS_COLORS } from "./layout.js";

const tmpMid = new THREE.Vector3();

// Middle control point of the curve: ground-to-ground links arc above the surface,
// links to the satellite are straight.
function midPoint(a, b, toSpace, target) {
  target.addVectors(a, b).multiplyScalar(0.5);
  if (!toSpace) {
    const lift = EARTH_RADIUS + 0.025 + a.distanceTo(b) * 0.3;
    target.normalize().multiplyScalar(lift);
  }
  return target;
}

function bezier(a, m, b, t, target) {
  const u = 1 - t;
  return target.set(
    u * u * a.x + 2 * u * t * m.x + t * t * b.x,
    u * u * a.y + 2 * u * t * m.y + t * t * b.y,
    u * u * a.z + 2 * u * t * m.z + t * t * b.z
  );
}

// Visual style of a link from its state.
export function linkStyle(link, inUse) {
  if (link.blocked) return { color: STATUS_COLORS.blocked, width: 1.5, dashed: true, opacity: 0.8, packets: 0 };
  if (link.status === "offline") return { color: STATUS_COLORS.offline, width: 1.5, dashed: true, opacity: 0.75, packets: 0 };
  if (!inUse) return { color: STATUS_COLORS.backup, width: 1, dashed: true, opacity: 0.45, packets: 0 };
  if (link.status === "degraded") return { color: STATUS_COLORS.degraded, width: 2.5, dashed: true, opacity: 1, packets: 1, speed: 0.18 };
  return { color: STATUS_COLORS.online, width: 2.5, dashed: true, opacity: 1, packets: 2, speed: 0.4 };
}

// A link between two nodes, with moving dashes and small "data packets" when traffic flows.
export default function LinkLine({ link, inUse, positions, selected }) {
  const line = useRef();
  const packets = useRef([]);
  const style = linkStyle(link, inUse);
  const toSpace = link.source_node.startsWith("SAT") || link.target_node.startsWith("SAT");
  const start = positions[link.source_node];
  const end = positions[link.target_node];
  const mid = useMemo(() => midPoint(start, end, toSpace, new THREE.Vector3()), [start, end, toSpace]);

  useFrame(({ clock }, delta) => {
    if (!line.current) return;
    if (toSpace) {
      midPoint(start, end, true, tmpMid);
      mid.copy(tmpMid);
      line.current.setPoints(start, end, mid);
    }
    if (style.packets) line.current.material.dashOffset -= delta * style.speed * 2;
    packets.current.forEach((p, i) => {
      if (!p) return;
      const t = (clock.elapsedTime * style.speed + i / style.packets) % 1;
      bezier(start, mid, end, t, p.position);
    });
  });

  if (!start || !end) return null;
  return (
    <group>
      <QuadraticBezierLine
        ref={line}
        start={start}
        end={end}
        mid={mid}
        color={selected ? "#38bdf8" : style.color}
        lineWidth={selected ? style.width + 1.5 : style.width}
        dashed={style.dashed}
        dashSize={style.packets ? 0.025 : 0.015}
        gapSize={style.packets ? 0.01 : 0.015}
        transparent
        opacity={style.opacity}
      />
      {Array.from({ length: style.packets }, (_, i) => (
        <mesh key={i} ref={(el) => (packets.current[i] = el)}>
          <sphereGeometry args={[0.0045, 10, 10]} />
          <meshBasicMaterial color={style.color} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}
