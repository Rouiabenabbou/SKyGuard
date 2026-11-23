import { useEffect, useState } from "react";

// v2.1 environment selector (top bar): which data source the SOC pages show.
//   all         everything
//   simulation  data from the built-in simulator and attack scenarios (SIM)
//   lab         data from real test boards (LAB)
//   production  real customer infrastructure: none is connected in this project
const KEY = "cybershield.environment";
export const ENVIRONMENTS = [
  { id: "all", label: "All sources" },
  { id: "simulation", label: "Simulation" },
  { id: "lab", label: "Lab" },
  { id: "production", label: "Production" },
];
const EVENT = "cybershield:environment";

export function getEnvironment() {
  try {
    return localStorage.getItem(KEY) || "all";
  } catch {
    return "all";
  }
}

export function setEnvironment(env) {
  try {
    localStorage.setItem(KEY, env);
  } catch {
    /* private window: kept for this page only */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: env }));
}

export function useEnvironment() {
  const [env, setEnv] = useState(getEnvironment);
  useEffect(() => {
    const on = (e) => setEnv(e.detail);
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, []);
  return env;
}

export const sourceParam = (env) => (env === "all" ? undefined : env);
