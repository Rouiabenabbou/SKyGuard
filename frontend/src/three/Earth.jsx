import { useEffect, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { EARTH_RADIUS } from "./layout.js";

// v1.1: the real Earth. NASA "Blue Marble" imagery (public domain), with a relief
// map for the mountains and a water mask so oceans shine a little.
// The files are in frontend/public/textures, so it works offline.
const loader = new THREE.TextureLoader();

function useTexture(url, srgb = true) {
  const [tex, setTex] = useState(null);
  useEffect(() => {
    let alive = true;
    loader.load(url, (t) => {
      if (!alive) return t.dispose();
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = 8;
      setTex(t);
    });
    return () => {
      alive = false;
    };
  }, [url, srgb]);
  return tex;
}

export default function Earth() {
  const day = useTexture("/textures/earth-blue-marble.jpg");
  const relief = useTexture("/textures/earth-topology.png", false);
  const water = useTexture("/textures/earth-water.png", false);
  const grid = useRef();
  useFrame((_, delta) => {
    if (grid.current) grid.current.rotation.y += delta * 0.005;
  });

  return (
    // The texture's longitude 0 lies on +X; our coordinates put it on +Z, hence the turn.
    <group>
      <mesh rotation={[0, -Math.PI / 2, 0]}>
        <sphereGeometry args={[EARTH_RADIUS, 160, 160]} />
        {day ? (
          <meshPhongMaterial
            key="real"
            map={day}
            bumpMap={relief}
            bumpScale={relief ? 0.015 : 0}
            specularMap={water}
            specular={new THREE.Color("#3b5b7a")}
            shininess={18}
          />
        ) : (
          <meshStandardMaterial key="loading" color="#1e3a8a" roughness={0.9} />
        )}
      </mesh>
      {/* very faint grid shell, gives a "digital twin" look */}
      <mesh ref={grid}>
        <sphereGeometry args={[EARTH_RADIUS * 1.003, 72, 36]} />
        <meshBasicMaterial color="#7dd3fc" wireframe transparent opacity={0.025} />
      </mesh>
      {/* atmosphere glow */}
      <mesh>
        <sphereGeometry args={[EARTH_RADIUS * 1.04, 64, 64]} />
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.07} side={THREE.BackSide} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
}
