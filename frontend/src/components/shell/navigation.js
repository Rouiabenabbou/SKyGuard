import {
  Activity, Bot, ChartColumn, CirclePlay, Cpu, Crosshair, FlaskConical, FolderKanban, Globe, HeartPulse, LayoutDashboard,
  ListChecks, Radar, Satellite, ScrollText, Settings, ShieldCheck, Siren, Terminal, Users, Waypoints, Workflow,
} from "lucide-react";

// v2.0: the SOC modules, grouped like an enterprise security console.
// Every entry opens a working page. `role` = minimum role, `perm` = permission needed to see it.
export const NAV = [
  { group: "Threat Operations", items: [
    { id: "overview", label: "Security Situation", icon: LayoutDashboard },
    { id: "alerts", label: "Alert Center", icon: Siren },
    { id: "incidents", label: "Incident Management", icon: FolderKanban },
    { id: "approvals", label: "Approvals", icon: ShieldCheck },
    { id: "simulation", label: "Attack Simulation", icon: FlaskConical, perm: "simulate" },
    { id: "demo", label: "Demo Scenario", icon: CirclePlay, perm: "simulate" },
  ] },
  { group: "Asset Management", items: [
    { id: "network", label: "Network Monitoring", icon: Activity },
    { id: "satcom", label: "Satellite & 5G Security", icon: Satellite },
    { id: "devices", label: "IoT Asset Management", icon: Cpu },
    { id: "topology", label: "Network Topology", icon: Waypoints },
    { id: "twin", label: "3D Digital Twin", icon: Globe },
  ] },
  { group: "Security Analysis", items: [
    { id: "rules", label: "Detection Rules", icon: ListChecks },
    { id: "hunting", label: "Threat Hunting", icon: Crosshair },
    { id: "intel", label: "Threat Intelligence", icon: Radar },
    { id: "ai", label: "AI Analyst (DeepSeek)", icon: Bot },
    { id: "automation", label: "Security Orchestration", icon: Workflow },
  ] },
  { group: "Settings & Compliance", items: [
    { id: "analytics", label: "Analytics & Reports", icon: ChartColumn },
    { id: "health", label: "System Health", icon: HeartPulse },
    { id: "users", label: "User Management", icon: Users, role: "admin" },
    { id: "admin", label: "Administration", icon: Settings, role: "admin" },
    { id: "audit", label: "Audit Logs", icon: ScrollText, role: "admin" },
    { id: "console", label: "Operator Console", icon: Terminal },
  ] },
];

export const PAGES = Object.fromEntries(NAV.flatMap((g) => g.items.map((i) => [i.id, { ...i, group: g.group }])));

// Old tab names (bookmarks, links inside the app) still work.
export const ALIASES = { security: "alerts", engineering: "health", data: "analytics", map: "topology" };

export function pageFromHash() {
  const raw = window.location.hash.replace("#", "").split(/[/?]/)[0];
  const id = ALIASES[raw] ?? raw;
  return PAGES[id] ? id : "overview";
}

// Query part of the hash: #hunting?q=src:1.2.3.4 -> { q: "src:1.2.3.4" }
export function hashParams() {
  const h = window.location.hash;
  const i = h.indexOf("?");
  return i < 0 ? {} : Object.fromEntries(new URLSearchParams(h.slice(i + 1)));
}
