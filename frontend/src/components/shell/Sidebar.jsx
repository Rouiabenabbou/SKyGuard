import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { NAV } from "./navigation.js";

function loadClosed() {
  try {
    return JSON.parse(localStorage.getItem("cybershield.navClosed") ?? "[]");
  } catch {
    return [];
  }
}

// Left navigation: grouped modules, active state, counters (open alerts / incidents).
export default function Sidebar({ active, onNavigate, counts = {}, can, has = () => true, version }) {
  const [closed, setClosed] = useState(loadClosed);
  const toggle = (g) => {
    const next = closed.includes(g) ? closed.filter((x) => x !== g) : [...closed, g];
    setClosed(next);
    try {
      localStorage.setItem("cybershield.navClosed", JSON.stringify(next));
    } catch {
      /* private window */
    }
  };
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div className="sb-brand">
        <img src="/shield.svg" alt="" />
        <div><b>CyberShield SecOps</b><span>on Huawei Cloud · SatCom IoT</span></div>
      </div>
      <nav role="tablist" aria-orientation="vertical">
        {NAV.map((g) => {
          const items = g.items.filter((i) => (!i.role || can(i.role)) && (!i.perm || has(i.perm)));
          const isClosed = closed.includes(g.group) && !items.some((i) => i.id === active);
          return (
            <div className="sb-group" key={g.group}>
              <button className="sb-group-title" onClick={() => toggle(g.group)} aria-expanded={!isClosed}>
                <span>{g.group}</span>{isClosed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
              </button>
              {!isClosed && items.map((i) => {
                const Icon = i.icon;
                const c = counts[i.id];
                return (
                  <button key={i.id} role="tab" aria-selected={active === i.id} title={i.label}
                          className={`sb-item ${active === i.id ? "active" : ""}`} onClick={() => onNavigate(i.id)}>
                    <Icon size={17} strokeWidth={1.8} />
                    <span className="sb-label">{i.label}</span>
                    {c ? <span className={`sb-count ${c.tone === "bad" ? "bad" : ""}`}>{c.value}</span> : null}
                  </button>
                );
              })}
            </div>
          );
        })}
      </nav>
      <div className="sb-footer">v{version} · all devices, attacks and network events are simulated unless marked LAB</div>
    </aside>
  );
}
