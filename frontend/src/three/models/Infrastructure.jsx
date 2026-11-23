// Detailed models of the network equipment, built from simple shapes (no model files needed).
// Every model is about 1 unit tall and stands on y = 0. `color` is the status colour
// (green online, amber degraded, red offline...). It lights the status LEDs, not the whole model.
import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { concrete, corrugated, goldFoil, serverFront, solarCells } from "./textures.js";

const STEEL = { color: "#cbd5e1", metalness: 0.75, roughness: 0.35 };
const DARK = { color: "#334155", metalness: 0.5, roughness: 0.5 };
const WHITE = { color: "#f1f5f9", metalness: 0.1, roughness: 0.6 };

// A small light that blinks (status LED / aircraft warning light).
export function Led({ position, color, size = 0.025, blink = 0, dim }) {
  const ref = useRef();
  useFrame(({ clock }) => {
    if (!ref.current || !blink) return;
    ref.current.material.emissiveIntensity = Math.sin(clock.elapsedTime * blink) > 0 ? 2.2 : 0.2;
  });
  return (
    <mesh ref={ref} position={position}>
      <sphereGeometry args={[size, 12, 8]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={dim ? 0.1 : 1.6} toneMapped={false} />
    </mesh>
  );
}

// A parabolic reflector (real dish shape, y = x² / 4f) opening towards +y.
export function Dish({ radius = 0.5, depth = 0.18, color = "#f8fafc" }) {
  const geometry = useMemo(() => {
    const pts = [];
    for (let i = 0; i <= 24; i++) {
      const r = (radius * i) / 24;
      pts.push(new THREE.Vector2(r, (depth * r * r) / (radius * radius)));
    }
    return new THREE.LatheGeometry(pts, 48);
  }, [radius, depth]);
  return (
    <group>
      <mesh geometry={geometry}>
        <meshStandardMaterial color={color} metalness={0.3} roughness={0.35} side={THREE.DoubleSide} />
      </mesh>
      {/* feed horn on three struts at the focal point */}
      <mesh position={[0, depth + radius * 0.55, 0]}>
        <cylinderGeometry args={[0.03, 0.05, 0.1, 12]} />
        <meshStandardMaterial {...DARK} />
      </mesh>
      {[0, 1, 2].map((k) => {
        const a = (k / 3) * Math.PI * 2;
        const base = new THREE.Vector3(Math.cos(a) * radius * 0.92, depth * 0.85, Math.sin(a) * radius * 0.92);
        const tip = new THREE.Vector3(0, depth + radius * 0.5, 0);
        const mid = base.clone().add(tip).multiplyScalar(0.5);
        const len = base.distanceTo(tip);
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), tip.clone().sub(base).normalize());
        return (
          <mesh key={k} position={mid} quaternion={q}>
            <cylinderGeometry args={[0.008, 0.008, len, 6]} />
            <meshStandardMaterial {...STEEL} />
          </mesh>
        );
      })}
    </group>
  );
}

// ------------------------------------------------------------------ satellite
// A communications satellite: gold-foil bus, two solar wings, an Earth-facing dish
// (the dish faces +z; the twin turns +z towards the Earth).
export function SatelliteModel({ color, dim }) {
  return (
    <group>
      <mesh>
        <boxGeometry args={[0.36, 0.36, 0.5]} />
        <meshStandardMaterial map={goldFoil()} metalness={0.85} roughness={0.35} color="#ffd27a" />
      </mesh>
      {/* radiator panels */}
      {[-1, 1].map((s) => (
        <mesh key={s} position={[0, s * 0.182, 0]}>
          <boxGeometry args={[0.3, 0.004, 0.44]} />
          <meshStandardMaterial color="#e2e8f0" metalness={0.9} roughness={0.15} />
        </mesh>
      ))}
      {/* solar wings: yoke + 3 panels each side */}
      {[-1, 1].map((s) => (
        <group key={s} position={[s * 0.18, 0, 0]}>
          <mesh position={[s * 0.1, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.012, 0.012, 0.2, 8]} />
            <meshStandardMaterial {...STEEL} />
          </mesh>
          {[0, 1, 2].map((p) => (
            <group key={p} position={[s * (0.36 + p * 0.33), 0, 0]}>
              <mesh>
                <boxGeometry args={[0.32, 0.012, 0.36]} />
                <meshStandardMaterial map={solarCells()} metalness={0.4} roughness={0.25}
                  emissive="#1e3a8a" emissiveIntensity={dim ? 0 : 0.25} />
              </mesh>
            </group>
          ))}
        </group>
      ))}
      {/* Earth-facing main dish */}
      <group position={[0, 0, 0.26]} rotation={[Math.PI / 2, 0, 0]}>
        <Dish radius={0.17} depth={0.06} />
      </group>
      {/* side dish and telemetry antenna */}
      <group position={[0.12, 0.2, 0.1]} rotation={[-0.4, 0, 0.3]}>
        <Dish radius={0.08} depth={0.03} color="#e5e7eb" />
      </group>
      <mesh position={[-0.12, 0.27, -0.15]}>
        <cylinderGeometry args={[0.006, 0.006, 0.18, 6]} />
        <meshStandardMaterial {...STEEL} />
      </mesh>
      {/* thrusters */}
      {[[-0.12, -0.12], [0.12, -0.12], [-0.12, 0.12], [0.12, 0.12]].map(([x, y], i) => (
        <mesh key={i} position={[x, y, -0.27]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.03, 0.05, 12, 1, true]} />
          <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.3} side={THREE.DoubleSide} />
        </mesh>
      ))}
      <Led position={[0, -0.19, 0.2]} color={color} size={0.025} blink={dim ? 0 : 3} dim={dim} />
    </group>
  );
}

// ------------------------------------------------------------------ ground station
// Satellite ground station: concrete pad, pedestal with azimuth/elevation mount, big dish,
// equipment shelter with an air conditioner.
export function GroundStationModel({ color, dim, spin = true }) {
  const head = useRef();
  useFrame(({ clock }) => {
    if (head.current && spin && !dim) head.current.rotation.y = Math.sin(clock.elapsedTime * 0.25) * 0.5;
  });
  return (
    <group>
      <mesh position={[0, 0.02, 0]}>
        <boxGeometry args={[1.1, 0.04, 0.9]} />
        <meshStandardMaterial map={concrete()} roughness={0.95} />
      </mesh>
      <mesh position={[-0.12, 0.2, 0]}>
        <cylinderGeometry args={[0.07, 0.1, 0.34, 16]} />
        <meshStandardMaterial {...WHITE} />
      </mesh>
      <group ref={head} position={[-0.12, 0.4, 0]}>
        <mesh>
          <boxGeometry args={[0.16, 0.08, 0.14]} />
          <meshStandardMaterial {...WHITE} />
        </mesh>
        <group position={[0, 0.08, 0.04]} rotation={[-0.75, 0, 0]}>
          <Dish radius={0.36} depth={0.12} />
        </group>
      </group>
      {/* equipment shelter */}
      <group position={[0.36, 0.04, 0.12]}>
        <mesh position={[0, 0.11, 0]}>
          <boxGeometry args={[0.3, 0.22, 0.4]} />
          <meshStandardMaterial map={corrugated("#e5e7eb")} roughness={0.6} />
        </mesh>
        <mesh position={[0.152, 0.1, -0.08]}>
          <boxGeometry args={[0.01, 0.14, 0.08]} />
          <meshStandardMaterial {...DARK} />
        </mesh>
        <mesh position={[0, 0.1, 0.205]}>
          <boxGeometry args={[0.16, 0.1, 0.02]} />
          <meshStandardMaterial color="#94a3b8" />
        </mesh>
        <Led position={[0.1, 0.18, 0.21]} color={color} size={0.018} blink={2} dim={dim} />
      </group>
    </group>
  );
}

// ------------------------------------------------------------------ 5G tower
// Lattice telecom tower with 3 sectors of 5G panel antennas, a microwave backhaul dish,
// a red aircraft warning light and a base-station cabinet.
export function Tower5GModel({ color, dim }) {
  const H = 1.0;
  const legs = [0, 1, 2].map((k) => (k / 3) * Math.PI * 2);
  const bars = [];
  for (let level = 0; level < 6; level++) {
    const y0 = (level / 6) * H;
    const y1 = ((level + 1) / 6) * H;
    const r0 = 0.14 * (1 - y0 / H) + 0.04;
    const r1 = 0.14 * (1 - y1 / H) + 0.04;
    legs.forEach((a, k) => {
      const b = legs[(k + 1) % 3];
      const p0 = new THREE.Vector3(Math.cos(a) * r0, y0, Math.sin(a) * r0);
      const p1 = new THREE.Vector3(Math.cos(b) * r1, y1, Math.sin(b) * r1);
      bars.push([p0, p1]);
      const q0 = new THREE.Vector3(Math.cos(a) * r1, y1, Math.sin(a) * r1);
      const q1 = new THREE.Vector3(Math.cos(b) * r1, y1, Math.sin(b) * r1);
      bars.push([q0, q1]);
    });
  }
  const strut = ([a, b], i) => {
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
    return (
      <mesh key={i} position={mid} quaternion={q}>
        <cylinderGeometry args={[0.005, 0.005, a.distanceTo(b), 4]} />
        <meshStandardMaterial {...STEEL} />
      </mesh>
    );
  };
  return (
    <group>
      <mesh position={[0, 0.015, 0]}>
        <boxGeometry args={[0.5, 0.03, 0.5]} />
        <meshStandardMaterial map={concrete()} roughness={0.95} />
      </mesh>
      {/* three legs */}
      {legs.map((a, k) => {
        const p0 = new THREE.Vector3(Math.cos(a) * 0.18, 0, Math.sin(a) * 0.18);
        const p1 = new THREE.Vector3(Math.cos(a) * 0.04, H, Math.sin(a) * 0.04);
        const mid = p0.clone().add(p1).multiplyScalar(0.5);
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), p1.clone().sub(p0).normalize());
        return (
          <mesh key={`leg${k}`} position={mid} quaternion={q}>
            <cylinderGeometry args={[0.012, 0.016, p0.distanceTo(p1), 6]} />
            <meshStandardMaterial {...STEEL} />
          </mesh>
        );
      })}
      {bars.map(strut)}
      {/* 5G sector antennas (3 x 2 panels) */}
      {[0, 1, 2].map((k) => {
        const a = (k / 3) * Math.PI * 2 + Math.PI / 3;
        return [0.86, 0.72].map((y) => (
          <group key={`${k}-${y}`} position={[Math.cos(a) * 0.09, y, Math.sin(a) * 0.09]} rotation={[0, -a + Math.PI / 2, 0]}>
            <mesh>
              <boxGeometry args={[0.06, 0.14, 0.025]} />
              <meshStandardMaterial {...WHITE} />
            </mesh>
            <Led position={[0, -0.06, 0.014]} color={color} size={0.007} dim={dim} />
          </group>
        ));
      })}
      {/* microwave backhaul dish */}
      <group position={[0, 0.58, 0.08]} rotation={[Math.PI / 2, 0, 0]}>
        <Dish radius={0.06} depth={0.025} color="#e2e8f0" />
      </group>
      <Led position={[0, H + 0.03, 0]} color="#ef4444" size={0.018} blink={2.5} />
      {/* base-station cabinet */}
      <group position={[0.22, 0.03, 0.16]}>
        <mesh position={[0, 0.09, 0]}>
          <boxGeometry args={[0.12, 0.18, 0.1]} />
          <meshStandardMaterial color="#d1d5db" metalness={0.4} roughness={0.5} />
        </mesh>
        <Led position={[0, 0.15, 0.052]} color={color} size={0.012} blink={1.5} dim={dim} />
      </group>
    </group>
  );
}

// ------------------------------------------------------------------ 5G core (data centre)
export function CoreModel({ color, dim }) {
  return (
    <group>
      <mesh position={[0, 0.02, 0]}>
        <boxGeometry args={[1.0, 0.04, 0.7]} />
        <meshStandardMaterial map={concrete()} roughness={0.95} />
      </mesh>
      {/* building */}
      <mesh position={[0, 0.24, 0]}>
        <boxGeometry args={[0.8, 0.4, 0.5]} />
        <meshStandardMaterial color="#e2e8f0" roughness={0.7} />
      </mesh>
      {/* glass band */}
      <mesh position={[0, 0.28, 0.252]}>
        <boxGeometry args={[0.72, 0.1, 0.005]} />
        <meshStandardMaterial color="#0ea5e9" metalness={0.9} roughness={0.1} emissive="#0c4a6e" emissiveIntensity={dim ? 0 : 0.5} />
      </mesh>
      {/* rooftop chillers */}
      {[-0.25, 0, 0.25].map((x) => (
        <group key={x} position={[x, 0.47, 0]}>
          <mesh>
            <boxGeometry args={[0.18, 0.06, 0.3]} />
            <meshStandardMaterial color="#94a3b8" metalness={0.5} roughness={0.4} />
          </mesh>
          <mesh position={[0, 0.035, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.06, 20]} />
            <meshStandardMaterial color="#1f2937" />
          </mesh>
        </group>
      ))}
      {/* door + status */}
      <mesh position={[0.25, 0.1, 0.252]}>
        <boxGeometry args={[0.1, 0.16, 0.005]} />
        <meshStandardMaterial {...DARK} />
      </mesh>
      <Led position={[-0.3, 0.42, 0.26]} color={color} size={0.02} blink={1.2} dim={dim} />
      {/* fibre cable trays */}
      <mesh position={[-0.45, 0.06, 0]}>
        <boxGeometry args={[0.1, 0.04, 0.6]} />
        <meshStandardMaterial color="#facc15" roughness={0.6} />
      </mesh>
    </group>
  );
}

// ------------------------------------------------------------------ security server (SOC)
export function SecurityServerModel({ color, dim }) {
  const shield = useRef();
  useFrame(({ clock }) => {
    if (shield.current) shield.current.rotation.y = clock.elapsedTime * 0.8;
  });
  return (
    <group>
      <mesh position={[0, 0.015, 0]}>
        <boxGeometry args={[0.7, 0.03, 0.5]} />
        <meshStandardMaterial color="#64748b" roughness={0.9} />
      </mesh>
      {[-0.17, 0.17].map((x) => (
        <group key={x} position={[x, 0.03, 0]}>
          <mesh position={[0, 0.3, 0]}>
            <boxGeometry args={[0.28, 0.6, 0.34]} />
            <meshStandardMaterial color="#0f172a" metalness={0.6} roughness={0.4} />
          </mesh>
          <mesh position={[0, 0.3, 0.172]}>
            <planeGeometry args={[0.25, 0.56]} />
            <meshStandardMaterial map={serverFront()} emissive="#ffffff" emissiveMap={serverFront()} emissiveIntensity={dim ? 0.05 : 0.6} />
          </mesh>
          <Led position={[0, 0.58, 0.175]} color={color} size={0.012} blink={4} dim={dim} />
        </group>
      ))}
      {/* the holographic shield of the SOC */}
      <group ref={shield} position={[0, 0.85, 0]}>
        <mesh>
          <octahedronGeometry args={[0.11]} />
          <meshStandardMaterial color="#38bdf8" emissive="#38bdf8" emissiveIntensity={dim ? 0.1 : 1.1} transparent opacity={0.85} toneMapped={false} />
        </mesh>
        <mesh>
          <octahedronGeometry args={[0.15]} />
          <meshBasicMaterial color="#38bdf8" wireframe transparent opacity={0.4} />
        </mesh>
      </group>
    </group>
  );
}
