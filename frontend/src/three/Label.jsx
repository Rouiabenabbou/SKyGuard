import { useEffect, useMemo } from "react";
import * as THREE from "three";

// A text label drawn on a small canvas and shown as a sprite (always faces the camera).
// Works offline: no font files or HTML overlays needed.
// screen=true keeps the label the same size on screen at any zoom, so zooming in separates close labels.
export default function Label({ text, color = "#94a3b8", position = [0, 0.2, 0], highlight = false, height = 0.07, screen = false }) {
  const { texture, aspect } = useMemo(() => {
    const font = "600 44px ui-monospace, Menlo, Consolas, monospace";
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = font;
    const w = Math.ceil(ctx.measureText(text).width) + 36;
    const h = 64;
    canvas.width = w;
    canvas.height = h;
    ctx.font = font;
    ctx.fillStyle = highlight ? "rgba(12, 74, 110, 0.92)" : "rgba(3, 7, 18, 0.82)";
    ctx.strokeStyle = color;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.roundRect(2, 2, w - 4, h - 4, 14);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#e2e8f0";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 18, h / 2 + 2);
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    return { texture: tex, aspect: w / h };
  }, [text, color, highlight]);

  useEffect(() => () => texture.dispose(), [texture]);

  return (
    <sprite position={position} scale={[height * aspect, height, 1]} renderOrder={10}>
      <spriteMaterial map={texture} transparent depthWrite={false} toneMapped={false} sizeAttenuation={!screen} />
    </sprite>
  );
}
