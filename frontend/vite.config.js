import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server runs on port 5173. Requests to /api and /ws are forwarded
// ("proxied") to the FastAPI backend on port 8000, so the browser sees one
// address and we avoid cross-origin problems.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
