// Small textures drawn on a canvas (no image files, works offline). Each is made once and reused.
import * as THREE from "three";

const cache = {};

function make(key, w, h, draw, repeat = [1, 1]) {
  if (cache[key]) return cache[key];
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  draw(canvas.getContext("2d"), w, h);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(...repeat);
  tex.anisotropy = 4;
  cache[key] = tex;
  return tex;
}

// Blue photovoltaic cells with silver bus bars.
export const solarCells = () =>
  make("solar", 256, 256, (c, w, h) => {
    c.fillStyle = "#0b1d4d";
    c.fillRect(0, 0, w, h);
    const n = 4;
    const s = w / n;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const g = c.createLinearGradient(i * s, j * s, (i + 1) * s, (j + 1) * s);
        g.addColorStop(0, "#1e3a8a");
        g.addColorStop(1, "#172554");
        c.fillStyle = g;
        c.fillRect(i * s + 3, j * s + 3, s - 6, s - 6);
        c.fillStyle = "rgba(203,213,225,0.55)";
        for (let k = 1; k < 3; k++) c.fillRect(i * s + 3, j * s + (k * s) / 3, s - 6, 1.5);
      }
    }
  });

// Gold multi-layer insulation foil (satellite body).
export const goldFoil = () =>
  make("foil", 256, 256, (c, w, h) => {
    c.fillStyle = "#b8860b";
    c.fillRect(0, 0, w, h);
    for (let i = 0; i < 900; i++) {
      const x = Math.random() * w;
      const y = Math.random() * h;
      const l = 10 + Math.random() * 40;
      c.strokeStyle = Math.random() > 0.5 ? "rgba(255,230,140,0.35)" : "rgba(120,80,10,0.35)";
      c.lineWidth = 1 + Math.random() * 2;
      c.beginPath();
      c.moveTo(x, y);
      c.lineTo(x + l * (Math.random() - 0.5), y + l * (Math.random() - 0.5));
      c.stroke();
    }
  });

// Green printed circuit board with traces and pads.
export const pcb = () =>
  make("pcb", 256, 512, (c, w, h) => {
    c.fillStyle = "#14532d";
    c.fillRect(0, 0, w, h);
    c.strokeStyle = "rgba(190,242,100,0.35)";
    c.lineWidth = 2;
    for (let i = 0; i < 40; i++) {
      let x = Math.random() * w;
      let y = Math.random() * h;
      c.beginPath();
      c.moveTo(x, y);
      for (let k = 0; k < 3; k++) {
        if (Math.random() > 0.5) x += (Math.random() - 0.5) * 120;
        else y += (Math.random() - 0.5) * 120;
        c.lineTo(x, y);
      }
      c.stroke();
    }
    c.fillStyle = "#d4d4d8";
    for (let i = 0; i < 19; i++) {
      c.fillRect(10, 30 + i * 24, 12, 12);
      c.fillRect(w - 22, 30 + i * 24, 12, 12);
    }
  });

// Concrete pad.
export const concrete = () =>
  make("concrete", 128, 128, (c, w, h) => {
    c.fillStyle = "#a8a29e";
    c.fillRect(0, 0, w, h);
    for (let i = 0; i < 1500; i++) {
      c.fillStyle = `rgba(${Math.random() > 0.5 ? "255,255,255" : "40,40,40"},0.07)`;
      c.fillRect(Math.random() * w, Math.random() * h, 2, 2);
    }
  }, [2, 2]);

// Corrugated steel (shipping container, shelters).
export const corrugated = (color = "#1d4ed8") =>
  make(`corr-${color}`, 256, 64, (c, w, h) => {
    for (let x = 0; x < w; x += 16) {
      const g = c.createLinearGradient(x, 0, x + 16, 0);
      g.addColorStop(0, color);
      g.addColorStop(0.5, "#ffffff22");
      g.addColorStop(1, color);
      c.fillStyle = color;
      c.fillRect(x, 0, 16, h);
      c.fillStyle = g;
      c.fillRect(x, 0, 16, h);
    }
  }, [3, 1]);

// Server front panel: drive bays and LEDs.
export const serverFront = () =>
  make("server", 128, 256, (c, w, h) => {
    c.fillStyle = "#111827";
    c.fillRect(0, 0, w, h);
    for (let u = 0; u < 12; u++) {
      const y = 6 + u * 20.5;
      c.fillStyle = "#1f2937";
      c.fillRect(6, y, w - 12, 17);
      for (let b = 0; b < 6; b++) {
        c.fillStyle = "#374151";
        c.fillRect(10 + b * 14, y + 3, 11, 11);
      }
      c.fillStyle = u % 3 === 0 ? "#f59e0b" : "#22c55e";
      c.fillRect(w - 22, y + 6, 4, 4);
      c.fillStyle = "#38bdf8";
      c.fillRect(w - 14, y + 6, 4, 4);
    }
  });

// Small LCD showing a reading.
export function lcd(text = "21.5°C") {
  return make(`lcd-${text}`, 128, 64, (c, w, h) => {
    c.fillStyle = "#0f2a1d";
    c.fillRect(0, 0, w, h);
    c.fillStyle = "#86efac";
    c.font = "bold 28px ui-monospace, Menlo, monospace";
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.fillText(text, w / 2, h / 2 + 2);
  });
}
