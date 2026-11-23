// 2D live map of the simulated satellite-5G network (the 3D version is in src/three/).
// Click a node or a link to see its details and change its state.

// Where each node is drawn on the 760 x 400 canvas.
const LAYOUT = {
  "SAT-1": { x: 380, y: 50 },
  "GS-1": { x: 640, y: 180 },
  "BS-5G": { x: 130, y: 190 },
  CORE: { x: 380, y: 300 },
  SEC: { x: 640, y: 330 },
  "IOT-001": { x: 285, y: 175 },
  "IOT-003": { x: 475, y: 175 },
  "IOT-002": { x: 130, y: 345 },
  "ESP32-001": { x: 270, y: 360 }, // real ESP32 board (Phase 11, optional)
};

// Free spots for nodes the operator adds (network builder / Add device), per type.
const EXTRA_SLOTS = {
  satellite: [{ x: 200, y: 50 }, { x: 560, y: 50 }, { x: 60, y: 50 }, { x: 700, y: 50 }],
  ground_station: [{ x: 720, y: 100 }, { x: 720, y: 255 }, { x: 560, y: 120 }],
  base_station: [{ x: 40, y: 110 }, { x: 40, y: 270 }, { x: 200, y: 120 }],
};

// Position of every node: the fixed layout above, then free spots for added nodes.
// Extra IoT devices go in a row under the map (the map grows to make room).
function buildLayout(nodes) {
  const pos = {};
  const used = {};
  let extraDevices = 0;
  for (const n of nodes) {
    if (LAYOUT[n.node_id]) {
      pos[n.node_id] = LAYOUT[n.node_id];
    } else if (n.node_type === "iot_device") {
      pos[n.node_id] = { x: 60 + (extraDevices % 8) * 92, y: 440 + Math.floor(extraDevices / 8) * 70 };
      extraDevices += 1;
    } else {
      const slots = EXTRA_SLOTS[n.node_type] ?? [];
      const i = used[n.node_type] ?? 0;
      used[n.node_type] = i + 1;
      pos[n.node_id] = slots[i] ?? { x: 100 + ((i * 97) % 560), y: 120 + ((i * 53) % 160) };
    }
  }
  const height = extraDevices ? 400 + 70 * Math.ceil(extraDevices / 8) + 10 : 400;
  return { pos, height };
}

const ICONS = {
  satellite: "🛰️",
  ground_station: "📡",
  base_station: "🗼",
  core: "🖧",
  security_server: "🛡️",
  iot_device: "🔹",
};

// A backup link that carries traffic after a failover (Phase 8) is drawn like an active link.
function linkClass(link) {
  if (link.blocked) return "lnk lnk-blocked";
  if (!link.is_active_path && !link.in_use) return link.status === "offline" ? "lnk lnk-offline" : "lnk lnk-backup";
  return `lnk lnk-${link.status}`;
}

export default function NetworkMap({ network, selected, onSelect }) {
  if (!network) return <div className="muted">Loading network…</div>;
  const layout = buildLayout(network.nodes);
  const pos = (id) => layout.pos[id] ?? { x: 380, y: 200 };

  return (
    <svg className="netmap" viewBox={`0 0 760 ${layout.height}`} role="img" aria-label="Network topology">
      {network.links.map((l) => {
        const a = pos(l.source_node);
        const b = pos(l.target_node);
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        const isSel = selected?.kind === "link" && selected.id === l.link_id;
        // Backup links are drawn as curves bending downwards so they don't cross the devices.
        const bend = l.is_active_path ? 0 : 80;
        const d = `M ${a.x} ${a.y} Q ${mx} ${my + bend} ${b.x} ${b.y}`;
        const midY = my + bend / 2;
        return (
          <g key={l.link_id} className="lnk-group" onClick={() => onSelect({ kind: "link", id: l.link_id })}>
            <path d={d} className="lnk-hit" />
            <path d={d} className={`${linkClass(l)} ${isSel ? "lnk-selected" : ""}`} />
            {l.status === "offline" && !l.blocked && (
              <text x={mx} y={midY + 5} className="lnk-x" textAnchor="middle">✕</text>
            )}
            {l.blocked && l.is_active_path && (
              <text x={mx} y={midY + 5} className="lnk-lock" textAnchor="middle">🔒</text>
            )}
            {(l.is_active_path || l.in_use) && l.status !== "offline" && !l.blocked && (
              <text x={mx} y={midY - 6} className="lnk-label" textAnchor="middle">
                {l.latency_ms} ms
              </text>
            )}
          </g>
        );
      })}

      {network.nodes.map((n) => {
        const p = pos(n.node_id);
        const isSel = selected?.kind === "node" && selected.id === n.node_id;
        return (
          <g key={n.node_id} className="node" transform={`translate(${p.x} ${p.y})`}
             onClick={() => onSelect({ kind: "node", id: n.node_id })}>
            <circle r="24" className={`node-circle node-${n.status} ${isSel ? "node-selected" : ""}`} />
            <text className="node-icon" textAnchor="middle" y="7">{n.status === "quarantined" ? "🔒" : ICONS[n.node_type] ?? "●"}</text>
            <text className="node-label" textAnchor="middle" y="40">{n.node_id}</text>
          </g>
        );
      })}
    </svg>
  );
}
