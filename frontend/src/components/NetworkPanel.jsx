import { useState } from "react";
import NetworkMap from "./NetworkMap.jsx";
import { api } from "../services/api.js";

const STATUS_TONE = { online: "ok", degraded: "warn", offline: "bad" };
export const MODE_LABELS = { primary: "primary", backup: "backup 5G", switching: "switching", down: "down" };

export function StateButtons({ onSet, current }) {
  return (
    <div className="button-row">
      <button className="btn btn-small need-operator need-platform" disabled={!current} onClick={() => onSet("auto")}>Normal</button>
      <button className="btn btn-small btn-warn need-operator need-platform" disabled={current === "degraded"} onClick={() => onSet("degraded")}>Degrade</button>
      <button className="btn btn-small btn-danger need-operator need-platform" disabled={current === "offline"} onClick={() => onSet("offline")}>Take offline</button>
    </div>
  );
}

function Details({ network, selected }) {
  const [error, setError] = useState(null);
  const run = (promise) => promise.then(() => setError(null)).catch((e) => setError(e.message));

  if (!selected) {
    return (
      <div className="muted small">
        <div className="legend">
          <span><i className="sw sw-online" /> online (moving dots = traffic)</span>
          <span><i className="sw sw-degraded" /> degraded</span>
          <span><i className="sw sw-offline" /> offline</span>
          <span><i className="sw sw-backup" /> backup link on standby (carries traffic after a failover)</span>
          <span>quarantined device: its links are blocked</span>
        </div>
      </div>
    );
  }

  if (selected.kind === "link") {
    const l = network.links.find((x) => x.link_id === selected.id);
    if (!l) return null;
    return (
      <div className="details">
        <h3>{l.link_id}</h3>
        <div className="muted small">{l.source_node} ↔ {l.target_node} · {l.link_type} · {l.is_active_path ? "primary" : "backup"}{l.in_use ? " · carrying traffic" : ""}</div>
        <dl>
          <dt>Status</dt><dd className={`tone-${STATUS_TONE[l.status]}`}>{l.status}{l.rain_fade ? " (rain fade)" : ""}</dd>
          <dt>Latency</dt><dd>{l.latency_ms} ms</dd>
          <dt>Packet loss</dt><dd>{l.packet_loss}%</dd>
          <dt>Bandwidth</dt><dd>{l.bandwidth_mbps} Mbps</dd>
        </dl>
        <StateButtons current={l.override} onSet={(s) => run(api.setLinkState(l.link_id, s))} />
        {error && <div className="tone-bad small">{error}</div>}
      </div>
    );
  }

  const n = network.nodes.find((x) => x.node_id === selected.id);
  if (!n) return null;
  const links = network.links.filter((l) => l.source_node === n.node_id || l.target_node === n.node_id);
  const isDevice = n.node_type === "iot_device";
  return (
    <div className="details">
      <h3>{n.name}</h3>
      <div className="muted small">{n.node_id} · {n.node_type.replace("_", " ")}</div>
      <dl>
        <dt>Status</dt><dd className={`tone-${STATUS_TONE[n.status] ?? "neutral"}`}>{n.status}</dd>
        <dt>Links</dt><dd>{links.map((l) => `${l.link_id} (${l.status})`).join(", ")}</dd>
        {isDevice && network.routes[n.node_id] && (
          <>
            <dt>Route</dt>
            <dd>{network.routes[n.node_id].connected ? network.routes[n.node_id].path.join(" → ") : "no route to core"}</dd>
          </>
        )}
      </dl>
      {!isDevice && (
        <StateButtons
          current={n.status === "online" ? null : n.status}
          onSet={(s) => run(api.setNodeState(n.node_id, s))}
        />
      )}
      {error && <div className="tone-bad small">{error}</div>}
    </div>
  );
}

export default function NetworkPanel({ network }) {
  const [selected, setSelected] = useState(null);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Satellite–5G network</h2>
        {network && (
          <span className="muted small">
            {network.links.filter((l) => l.status === "online").length} online ·{" "}
            {network.links.filter((l) => l.status === "degraded").length} degraded ·{" "}
            {network.links.filter((l) => l.status === "offline").length} offline links
          </span>
        )}
      </div>
      <div className="network-layout">
        <NetworkMap network={network} selected={selected} onSelect={setSelected} />
        <div className="network-side">
          {network && <Details network={network} selected={selected} />}
        </div>
      </div>

      {network && (
        <div className="routes">
          <h3>Device routes to the telecom core</h3>
          {Object.entries(network.routes).map(([id, r]) => (
            <div key={id} className="route-row">
              <span className="route-id">{id}</span>
              {r.mode && r.mode !== "quarantined" && (
                <span className={`mode-badge mode-${r.mode}`}>{MODE_LABELS[r.mode] ?? r.mode}</span>
              )}
              {r.connected ? (
                <>
                  <span className="route-path">
                    {r.path.map((hop, i) => (
                      <span key={hop}>
                        {i > 0 && <span className="path-arrow"> → </span>}
                        <span className="path-node">{hop}</span>
                      </span>
                    ))}
                  </span>
                  <span className={r.degraded ? "tone-warn" : "tone-ok"}>{r.latency_ms} ms{r.degraded ? " (degraded)" : ""}</span>
                </>
              ) : r.quarantined ? (
                <span className="tone-bad">Quarantined: traffic blocked on purpose</span>
              ) : (
                <span className={r.mode === "switching" ? "tone-warn" : "tone-bad"}>
                  {r.mode === "switching"
                    ? `Handover to the ${r.switching_to} path… (${r.handover_remaining_s}s)`
                    : "No route to core: traffic interrupted"}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
