// Shared look for every chart, matching the dark SOC theme (v2.0).
// Device colours: a fixed categorical order (checked for colour-blind separation on
// the white panel; every chart also has a legend). A device keeps its colour everywhere, whatever is filtered.
export const DEVICE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];

const EXTRA_COLORS = ["#6250d6", "#e34948", "#0e9aa7", "#b5487f", "#7a8b18", "#8a5a2b", "#3b5bdb", "#d9480f"];

// Fixed colour per known device, so enabling the ESP32 never repaints the others.
const FIXED = { "IOT-001": DEVICE_COLORS[0], "IOT-002": DEVICE_COLORS[1], "IOT-003": DEVICE_COLORS[2], "ESP32-001": DEVICE_COLORS[3] };

export function deviceColor(deviceId, allIds) {
  if (FIXED[deviceId]) return FIXED[deviceId];
  const others = [...allIds].filter((id) => !FIXED[id]).sort();
  const i = others.indexOf(deviceId);
  return i < 0 ? "#94a3b8" : EXTRA_COLORS[i % EXTRA_COLORS.length]; // extra devices
}

// Status colours are reserved for severity and never reused for series.
export const SEVERITY_COLORS = { low: "#94a3b8", medium: "#eda100", high: "#eb6834", critical: "#dc2626" };

export const axis = {
  stroke: "#2b3b55",
  tick: { fill: "#8b9bb4", fontSize: 11 },
  tickLine: false,
};
export const grid = { stroke: "#1f2c42", strokeDasharray: "3 3", vertical: false };
export const tooltip = {
  contentStyle: { background: "#0f1828", border: "1px solid #2b3b55", borderRadius: 4, fontSize: 12, color: "#e2e8f0", boxShadow: "0 6px 18px rgba(0,0,0,0.4)" },
  labelStyle: { color: "#8b9bb4" },
  cursor: { stroke: "#94a3b8", strokeWidth: 1 },
};
export const legend = { wrapperStyle: { fontSize: 12, color: "#c3cfdf" }, iconType: "plainline" };

export const timeTick = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
