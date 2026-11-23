// 3D models of the IoT devices (about 1 unit tall, standing on y = 0).
// `color` is the status colour: it lights the device's status LED.
import { Led } from "./Infrastructure.jsx";
import { corrugated, lcd, pcb, solarCells } from "./textures.js";
import { iotKind } from "./catalog.js";

const STEEL = { color: "#cbd5e1", metalness: 0.75, roughness: 0.35 };
const PLASTIC = { color: "#f1f5f9", metalness: 0.05, roughness: 0.55 };
const GREY = { color: "#64748b", metalness: 0.3, roughness: 0.6 };

function Box({ args, position, rotation, mat = PLASTIC, children }) {
  return (
    <mesh position={position} rotation={rotation}>
      <boxGeometry args={args} />
      {children ?? <meshStandardMaterial {...mat} />}
    </mesh>
  );
}

function Cyl({ args, position, rotation, mat = STEEL }) {
  return (
    <mesh position={position} rotation={rotation}>
      <cylinderGeometry args={args} />
      <meshStandardMaterial {...mat} />
    </mesh>
  );
}

function Antenna({ position, height = 0.25 }) {
  return (
    <group position={position}>
      <Cyl args={[0.012, 0.016, height, 8]} position={[0, height / 2, 0]} mat={{ color: "#111827", roughness: 0.6 }} />
      <mesh position={[0, height + 0.01, 0]}>
        <sphereGeometry args={[0.016, 8, 8]} />
        <meshStandardMaterial color="#111827" />
      </mesh>
    </group>
  );
}

function SolarPanel({ position, rotation, size = [0.3, 0.22] }) {
  return (
    <group position={position} rotation={rotation}>
      <Box args={[size[0] + 0.02, 0.015, size[1] + 0.02]} mat={{ color: "#94a3b8", metalness: 0.7, roughness: 0.3 }} />
      <mesh position={[0, 0.009, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={size} />
        <meshStandardMaterial map={solarCells()} metalness={0.4} roughness={0.25} />
      </mesh>
    </group>
  );
}

// ESP32 DevKit + DHT22 on a breadboard (the real board of Phase 11).
function Esp32({ color, dim }) {
  return (
    <group>
      {/* breadboard */}
      <Box args={[0.9, 0.08, 0.5]} position={[0, 0.04, 0]} mat={{ color: "#f8fafc", roughness: 0.8 }} />
      {Array.from({ length: 20 }).map((_, i) => (
        <Box key={i} args={[0.02, 0.005, 0.38]} position={[-0.42 + i * 0.044, 0.083, 0]} mat={{ color: "#e2e8f0" }} />
      ))}
      {/* ESP32 dev board */}
      <group position={[-0.12, 0.13, 0.02]}>
        <mesh>
          <boxGeometry args={[0.3, 0.025, 0.56]} />
          <meshStandardMaterial map={pcb()} roughness={0.6} />
        </mesh>
        {/* WROOM module with metal shield and PCB antenna */}
        <Box args={[0.2, 0.03, 0.26]} position={[0, 0.03, -0.06]} mat={{ color: "#d1d5db", metalness: 0.9, roughness: 0.25 }} />
        <Box args={[0.2, 0.006, 0.08]} position={[0, 0.016, -0.24]} mat={{ color: "#0f3d24" }} />
        <Box args={[0.09, 0.05, 0.07]} position={[0, 0.03, 0.27]} mat={{ color: "#9ca3af", metalness: 0.9, roughness: 0.3 }} />
        <Box args={[0.04, 0.02, 0.03]} position={[-0.08, 0.02, 0.18]} mat={{ color: "#111827" }} />
        <Box args={[0.04, 0.02, 0.03]} position={[0.08, 0.02, 0.18]} mat={{ color: "#111827" }} />
        {/* header pins */}
        {Array.from({ length: 15 }).map((_, i) => [-0.135, 0.135].map((x) => (
          <Box key={`${i}${x}`} args={[0.012, 0.03, 0.012]} position={[x, -0.02, -0.25 + i * 0.035]} mat={{ color: "#fbbf24", metalness: 0.9 }} />
        )))}
        <Led position={[0.1, 0.025, 0.2]} color={color} size={0.014} blink={dim ? 0 : 2} dim={dim} />
      </group>
      {/* DHT22: white perforated sensor on 4 legs */}
      <group position={[0.33, 0.1, 0.02]}>
        <Box args={[0.16, 0.24, 0.07]} position={[0, 0.2, 0]} mat={{ color: "#f8fafc", roughness: 0.4 }} />
        {Array.from({ length: 12 }).map((_, i) => (
          <Box key={i} args={[0.025, 0.012, 0.01]} position={[-0.045 + (i % 3) * 0.045, 0.12 + Math.floor(i / 3) * 0.045, 0.037]} mat={{ color: "#94a3b8" }} />
        ))}
        {[-0.045, -0.015, 0.015, 0.045].map((x) => (
          <Box key={x} args={[0.01, 0.08, 0.01]} position={[x, 0.04, 0]} mat={{ color: "#9ca3af", metalness: 0.9 }} />
        ))}
      </group>
      {/* jumper wires */}
      {[["#ef4444", -0.02], ["#111827", 0.04], ["#facc15", 0.1]].map(([c, z]) => (
        <mesh key={c} position={[0.12, 0.14, z]} rotation={[0, 0, Math.PI / 2]}>
          <torusGeometry args={[0.1, 0.008, 6, 16, Math.PI]} />
          <meshStandardMaterial color={c} />
        </mesh>
      ))}
    </group>
  );
}

// Weather / air-quality station: mast, radiation shield, solar panel, logger box, antenna.
function Station({ color, dim }) {
  return (
    <group>
      {/* tripod */}
      {[0, 1, 2].map((k) => {
        const a = (k / 3) * Math.PI * 2;
        return <Cyl key={k} args={[0.012, 0.012, 0.42, 6]} position={[Math.cos(a) * 0.12, 0.18, Math.sin(a) * 0.12]}
          rotation={[Math.sin(a) * 0.45, 0, -Math.cos(a) * 0.45]} />;
      })}
      <Cyl args={[0.02, 0.02, 1.0, 10]} position={[0, 0.5, 0]} />
      {/* Stevenson-type radiation shield: stacked white plates */}
      <group position={[0, 0.62, 0.12]}>
        <Cyl args={[0.008, 0.008, 0.12, 6]} position={[0, 0, -0.06]} rotation={[Math.PI / 2, 0, 0]} />
        {Array.from({ length: 7 }).map((_, i) => (
          <Cyl key={i} args={[0.075 - i * 0.002, 0.085 - i * 0.002, 0.016, 20]} position={[0, -0.08 + i * 0.026, 0]} mat={PLASTIC} />
        ))}
      </group>
      <SolarPanel position={[0, 0.93, -0.12]} rotation={[0.6, 0, 0]} size={[0.32, 0.24]} />
      {/* logger / modem box */}
      <Box args={[0.2, 0.24, 0.1]} position={[0, 0.33, 0.07]} mat={{ color: "#e5e7eb", roughness: 0.5 }} />
      <Box args={[0.06, 0.04, 0.03]} position={[0, 0.24, 0.13]} mat={{ color: "#f8fafc" }} />
      <mesh position={[0, 0.24, 0.146]}>
        <sphereGeometry args={[0.018, 10, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#fefce8" transparent opacity={0.8} />
      </mesh>
      <Led position={[0.07, 0.42, 0.125]} color={color} size={0.014} blink={dim ? 0 : 1.5} dim={dim} />
      <Antenna position={[0.12, 0.98, 0]} height={0.16} />
    </group>
  );
}

// Farm stake: pole in the soil, sensor head, solar cell, antenna.
function Agri({ color, dim }) {
  return (
    <group>
      <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.3, 24]} />
        <meshStandardMaterial color="#6b4f2a" roughness={1} />
      </mesh>
      {/* grass */}
      {Array.from({ length: 18 }).map((_, i) => {
        const a = i * 2.4;
        const r = 0.1 + (i % 5) * 0.035;
        return <Box key={i} args={[0.01, 0.07, 0.004]} position={[Math.cos(a) * r, 0.04, Math.sin(a) * r]} rotation={[0, a, 0.2]}
          mat={{ color: "#4d7c0f" }} />;
      })}
      <Cyl args={[0.018, 0.018, 0.2, 8]} position={[0, 0.06, 0.06]} mat={{ color: "#a3a3a3", metalness: 0.8 }} />
      <Cyl args={[0.025, 0.025, 0.85, 10]} position={[0, 0.43, 0]} mat={{ color: "#16a34a", roughness: 0.6 }} />
      <Box args={[0.16, 0.2, 0.12]} position={[0, 0.48, 0.05]} mat={{ color: "#f8fafc" }} />
      <Box args={[0.06, 0.03, 0.02]} position={[0, 0.4, 0.115]} mat={{ color: "#e5e7eb" }} />
      <mesh position={[0, 0.4, 0.13]}>
        <sphereGeometry args={[0.016, 10, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#fefce8" transparent opacity={0.8} />
      </mesh>
      <SolarPanel position={[0, 0.74, -0.06]} rotation={[0.5, 0, 0]} size={[0.2, 0.16]} />
      <Led position={[0.05, 0.56, 0.115]} color={color} size={0.013} blink={dim ? 0 : 1.5} dim={dim} />
      <Antenna position={[0.1, 0.86, 0]} height={0.14} />
    </group>
  );
}

// Wall sensor with a display.
function Building({ color, dim, reading }) {
  return (
    <group>
      <Box args={[0.6, 1.0, 0.04]} position={[0, 0.5, -0.04]} mat={{ color: "#e7e5e4", roughness: 0.95 }} />
      <Box args={[0.36, 0.5, 0.1]} position={[0, 0.5, 0.04]} mat={{ color: "#fafafa", roughness: 0.4 }} />
      <mesh position={[0, 0.58, 0.092]}>
        <planeGeometry args={[0.26, 0.13]} />
        <meshStandardMaterial map={lcd(reading)} emissive="#ffffff" emissiveMap={lcd(reading)} emissiveIntensity={dim ? 0.05 : 0.5} />
      </mesh>
      {Array.from({ length: 5 }).map((_, i) => (
        <Box key={i} args={[0.2, 0.012, 0.01]} position={[0, 0.32 + i * 0.03, 0.092]} mat={{ color: "#cbd5e1" }} />
      ))}
      <Led position={[0.15, 0.7, 0.095]} color={color} size={0.013} blink={dim ? 0 : 1.2} dim={dim} />
    </group>
  );
}

// Medical / food fridge with a logger on top.
function Fridge({ color, dim, reading }) {
  return (
    <group>
      {/* cabinet: open at the front so the glass door shows the inside */}
      <Box args={[0.55, 0.9, 0.03]} position={[0, 0.45, -0.21]} mat={{ color: "#f8fafc", metalness: 0.3, roughness: 0.4 }} />
      {[-0.26, 0.26].map((x) => (
        <Box key={x} args={[0.03, 0.9, 0.45]} position={[x, 0.45, 0]} mat={{ color: "#f8fafc", metalness: 0.3, roughness: 0.4 }} />
      ))}
      <Box args={[0.55, 0.05, 0.45]} position={[0, 0.875, 0]} mat={{ color: "#f8fafc", metalness: 0.3, roughness: 0.4 }} />
      <Box args={[0.55, 0.12, 0.45]} position={[0, 0.06, 0]} mat={{ color: "#e2e8f0", metalness: 0.3, roughness: 0.4 }} />
      <Box args={[0.49, 0.72, 0.01]} position={[0, 0.48, -0.19]} mat={{ color: "#dbeafe", roughness: 0.3 }} />
      {/* glass door */}
      <Box args={[0.48, 0.8, 0.01]} position={[0, 0.46, 0.23]}>
        <meshStandardMaterial color="#bae6fd" transparent opacity={0.35} metalness={0.2} roughness={0.05} />
      </Box>
      {[0.25, 0.45, 0.65].map((y) => (
        <Box key={y} args={[0.46, 0.012, 0.38]} position={[0, y, 0]} mat={{ color: "#cbd5e1", metalness: 0.6 }} />
      ))}
      {/* vaccine boxes */}
      {[[-0.12, 0.29], [0.06, 0.29], [-0.05, 0.49], [0.13, 0.49]].map(([x, y], i) => (
        <Box key={i} args={[0.12, 0.07, 0.1]} position={[x, y, 0]} mat={{ color: i % 2 ? "#60a5fa" : "#fca5a5" }} />
      ))}
      {/* probe bottle */}
      <Cyl args={[0.025, 0.025, 0.08, 10]} position={[0, 0.49, 0.12]} mat={{ color: "#e0f2fe", roughness: 0.2 }} />
      <Box args={[0.03, 0.4, 0.01]} position={[0.26, 0.62, 0.23]} mat={{ color: "#94a3b8", metalness: 0.8 }} />
      {/* logger on top */}
      <Box args={[0.22, 0.12, 0.08]} position={[0, 0.96, 0.15]} mat={{ color: "#1f2937" }} />
      <mesh position={[0, 0.965, 0.191]}>
        <planeGeometry args={[0.16, 0.07]} />
        <meshStandardMaterial map={lcd(reading)} emissive="#ffffff" emissiveMap={lcd(reading)} emissiveIntensity={dim ? 0.05 : 0.6} />
      </mesh>
      <Led position={[0.09, 1.0, 0.192]} color={color} size={0.012} blink={dim ? 0 : 1.5} dim={dim} />
      <Antenna position={[-0.2, 0.9, 0]} height={0.12} />
    </group>
  );
}

// 40 ft reefer container with a roof tracker.
function Container({ color, dim }) {
  return (
    <group>
      <Box args={[1.3, 0.5, 0.48]} position={[0, 0.27, 0]}>
        <meshStandardMaterial map={corrugated("#e2e8f0")} roughness={0.5} metalness={0.3} />
      </Box>
      {/* reefer machinery end */}
      <Box args={[0.04, 0.46, 0.44]} position={[0.67, 0.27, 0]} mat={{ color: "#94a3b8", metalness: 0.6 }} />
      {[[0.69, 0.36, -0.1], [0.69, 0.36, 0.1]].map((p, i) => (
        <mesh key={i} position={p} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.07, 0.07, 0.01, 20]} />
          <meshStandardMaterial color="#1f2937" />
        </mesh>
      ))}
      <Box args={[0.02, 0.1, 0.14]} position={[0.695, 0.16, 0.1]} mat={{ color: "#111827" }} />
      {/* doors */}
      {[-0.11, 0.11].map((z) => (
        <Box key={z} args={[0.012, 0.46, 0.21]} position={[-0.656, 0.27, z]} mat={{ color: "#cbd5e1", metalness: 0.5 }} />
      ))}
      {[-0.06, 0.06].map((z) => (
        <Cyl key={z} args={[0.006, 0.006, 0.44, 6]} position={[-0.665, 0.27, z]} />
      ))}
      {/* corner castings */}
      {[[-0.64, -0.22], [0.64, -0.22], [-0.64, 0.22], [0.64, 0.22]].map(([x, z]) => (
        <Box key={`${x}${z}`} args={[0.05, 0.05, 0.05]} position={[x, 0.04, z]} mat={{ color: "#475569" }} />
      ))}
      {/* tracker */}
      <Box args={[0.16, 0.05, 0.12]} position={[0, 0.545, 0]} mat={{ color: "#111827" }} />
      <mesh position={[0, 0.575, 0]}>
        <sphereGeometry args={[0.05, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#f8fafc" />
      </mesh>
      <Led position={[0.07, 0.57, 0.06]} color={color} size={0.012} blink={dim ? 0 : 1.5} dim={dim} />
    </group>
  );
}

// Conveyor motor with a vibration puck and a gateway.
function Vibration({ color, dim }) {
  return (
    <group>
      <Box args={[1.0, 0.04, 0.5]} position={[0, 0.02, 0]} mat={{ color: "#78716c", roughness: 1 }} />
      {/* conveyor frame + belt */}
      <Box args={[0.7, 0.04, 0.3]} position={[-0.2, 0.32, 0]} mat={{ color: "#1f2937", roughness: 0.9 }} />
      {[-0.5, 0.1].map((x) => (
        <Cyl key={x} args={[0.06, 0.06, 0.32, 16]} position={[x, 0.3, 0]} rotation={[Math.PI / 2, 0, 0]} mat={{ color: "#9ca3af", metalness: 0.7 }} />
      ))}
      {[-0.5, -0.2, 0.1].map((x) => (
        <Box key={x} args={[0.03, 0.28, 0.3]} position={[x, 0.15, 0]} mat={{ color: "#f59e0b", metalness: 0.3 }} />
      ))}
      {/* motor */}
      <Cyl args={[0.11, 0.11, 0.3, 20]} position={[0.1, 0.3, 0.26]} rotation={[Math.PI / 2, 0, 0]} mat={{ color: "#2563eb", metalness: 0.5, roughness: 0.4 }} />
      {Array.from({ length: 8 }).map((_, i) => (
        <Box key={i} args={[0.01, 0.24, 0.02]} position={[0.1 + Math.cos((i / 8) * Math.PI * 2) * 0.11, 0.3 + Math.sin((i / 8) * Math.PI * 2) * 0.11, 0.26]}
          rotation={[Math.PI / 2, 0, (i / 8) * Math.PI * 2]} mat={{ color: "#1d4ed8" }} />
      ))}
      {/* vibration puck (magnet mount) */}
      <Cyl args={[0.04, 0.04, 0.05, 20]} position={[0.1, 0.43, 0.26]} mat={{ color: "#f97316", roughness: 0.5 }} />
      <Led position={[0.1, 0.46, 0.29]} color={color} size={0.011} blink={dim ? 0 : 2} dim={dim} />
      {/* 5G gateway */}
      <Box args={[0.14, 0.18, 0.08]} position={[0.36, 0.5, 0]} mat={{ color: "#e5e7eb" }} />
      <Cyl args={[0.01, 0.01, 0.4, 6]} position={[0.36, 0.2, 0]} />
      <Antenna position={[0.4, 0.59, 0]} height={0.12} />
      <Antenna position={[0.32, 0.59, 0]} height={0.12} />
    </group>
  );
}

function Generic({ color, dim }) {
  return (
    <group>
      <Cyl args={[0.025, 0.03, 0.6, 10]} position={[0, 0.3, 0]} />
      <Box args={[0.24, 0.3, 0.14]} position={[0, 0.45, 0.05]} mat={{ color: "#f1f5f9" }} />
      <Led position={[0.08, 0.55, 0.125]} color={color} size={0.014} blink={dim ? 0 : 1.5} dim={dim} />
      <Antenna position={[0.12, 0.6, 0]} height={0.22} />
    </group>
  );
}

const MODELS = { esp32: Esp32, station: Station, agri: Agri, building: Building, fridge: Fridge,
  container: Container, vibration: Vibration, generic: Generic };

// The model for one device (kind from catalog.iotKind).
// live=true shows the device's current temperature on its display (device viewer).
export default function IotModel({ device, color = "#22c55e", dim = false, live = false }) {
  const kind = iotKind(device);
  const Model = MODELS[kind] ?? Generic;
  const reading = live && device?.temperature != null ? `${Math.round(device.temperature)}°C` : "CS-3D";
  return <Model color={color} dim={dim} reading={kind === "building" || kind === "fridge" ? reading : undefined} />;
}
