// Draws a stylised Earth texture on a canvas, so no image file has to be downloaded.
// Land shapes come from smooth random noise with a fixed seed (same picture every time).
import * as THREE from "three";

function makeNoise(seed) {
  let s = seed;
  const rand = () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
  const size = 64;
  const grid = Array.from({ length: size * size }, rand);
  const smooth = (t) => t * t * (3 - 2 * t);
  const at = (x, y) => grid[((y % size) + size) % size * size + (((x % size) + size) % size)];
  return (x, y) => {
    const x0 = Math.floor(x), y0 = Math.floor(y);
    const fx = smooth(x - x0), fy = smooth(y - y0);
    const a = at(x0, y0), b = at(x0 + 1, y0), c = at(x0, y0 + 1), d = at(x0 + 1, y0 + 1);
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
  };
}

export function createEarthTexture() {
  const width = 1024;
  const height = 512;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(width, height);
  const noise = makeNoise(42);

  for (let y = 0; y < height; y++) {
    const lat = 90 - (y / height) * 180;
    for (let x = 0; x < width; x++) {
      // sample noise so the left and right edges of the map match
      const u = (x / width) * 16;
      const v = (y / height) * 8;
      let n = 0;
      let amp = 0.5;
      let freq = 1;
      for (let o = 0; o < 4; o++) {
        n += amp * noise(u * freq, v * freq);
        amp *= 0.5;
        freq *= 2;
      }
      const polar = Math.abs(lat) > 76;
      const land = n > 0.52;
      let r, g, b;
      if (polar) {
        [r, g, b] = [150, 170, 190];
      } else if (land) {
        const dry = Math.abs(lat) < 32 && n < 0.6; // deserts near the tropics
        [r, g, b] = dry ? [150, 128, 84] : [46, 104, 64];
        const shade = (n - 0.52) * 120;
        r += shade; g += shade; b += shade * 0.6;
      } else {
        const depth = (0.52 - n) * 160;
        [r, g, b] = [14, 52 - depth * 0.2, 104 - depth * 0.3];
      }
      const i = (y * width + x) * 4;
      image.data[i] = r;
      image.data[i + 1] = g;
      image.data[i + 2] = b;
      image.data[i + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);

  // faint latitude / longitude grid
  ctx.strokeStyle = "rgba(148, 197, 255, 0.12)";
  ctx.lineWidth = 1;
  for (let lon = 0; lon <= width; lon += width / 24) {
    ctx.beginPath(); ctx.moveTo(lon, 0); ctx.lineTo(lon, height); ctx.stroke();
  }
  for (let lat = 0; lat <= height; lat += height / 12) {
    ctx.beginPath(); ctx.moveTo(0, lat); ctx.lineTo(width, lat); ctx.stroke();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}
