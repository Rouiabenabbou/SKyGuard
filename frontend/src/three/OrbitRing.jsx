import { useMemo } from "react";
import { Line } from "@react-three/drei";
import { orbitPoint } from "./layout.js";

// The satellite's orbit drawn as a faint dashed circle.
export default function OrbitRing() {
  const points = useMemo(() => {
    const pts = [];
    for (let i = 0; i <= 160; i++) pts.push(orbitPoint((i / 160) * Math.PI * 2));
    return pts;
  }, []);
  return <Line points={points} color="#38bdf8" lineWidth={1} dashed dashSize={0.04} gapSize={0.03} transparent opacity={0.35} />;
}
