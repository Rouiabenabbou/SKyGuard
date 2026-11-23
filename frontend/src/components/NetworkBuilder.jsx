import { useState } from "react";
import { api } from "../services/api.js";

// Network builder: the operator designs their own topology by adding satellites,
// ground stations, 5G towers and links. Traffic is routed over whatever path
// reaches the telecom core (CORE). Only items added here can be removed.
const NODE_TYPES = [
  ["satellite", "Satellite"],
  ["ground_station", "Ground station"],
  ["base_station", "5G base station"],
];
const LINK_TYPES = ["satellite", "5g", "fiber", "lan"];

export default function NetworkBuilder({ network }) {
  const [node, setNode] = useState({ node_id: "", name: "", node_type: "satellite" });
  const [link, setLink] = useState({ source_node: "", target_node: "", link_type: "satellite", role: "primary" });
  const [msg, setMsg] = useState(null);
  const nodes = network?.nodes ?? [];
  const addedNodes = nodes.filter((n) => n.added && n.node_type !== "iot_device");
  const addedLinks = (network?.links ?? []).filter((l) => l.added);

  async function run(promise, ok) {
    try {
      await promise;
      setMsg({ ok: true, text: ok });
      return true;
    } catch (e) {
      setMsg({ ok: false, text: e.message });
      return false;
    }
  }

  async function addNode(e) {
    e.preventDefault();
    const id = node.node_id.trim().toUpperCase();
    if (await run(api.addNode({ ...node, node_id: id }), `${id} added. Now connect it with links.`)) {
      setNode({ ...node, node_id: "", name: "" });
    }
  }

  async function addLink(e) {
    e.preventDefault();
    await run(api.addLink(link), `${link.source_node} ↔ ${link.target_node} connected.`);
  }

  const nodeOptions = nodes.map((n) => <option key={n.node_id} value={n.node_id}>{n.node_id}</option>);

  return (
    <section className="panel need-admin need-platform">
      <div className="panel-head">
        <h2>Network builder</h2>
      </div>
      <div className="builder-grid">
        <form className="config-form" onSubmit={addNode}>
          <h3>1. Add a node</h3>
          <label><span>Type</span>
            <select value={node.node_type} onChange={(e) => setNode({ ...node, node_type: e.target.value })}>
              {NODE_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label><span>Node ID</span>
            <input value={node.node_id} onChange={(e) => setNode({ ...node, node_id: e.target.value })}
                   placeholder={{ satellite: "SAT-2", ground_station: "GS-2", base_station: "BS-5G-2" }[node.node_type]}
                   maxLength={24} required />
          </label>
          <label><span>Name (optional)</span>
            <input value={node.name} onChange={(e) => setNode({ ...node, name: e.target.value })} maxLength={100} />
          </label>
          <div className="config-actions"><button className="btn btn-small btn-primary">Add node</button></div>
        </form>

        <form className="config-form" onSubmit={addLink}>
          <h3>2. Connect two nodes</h3>
          <label><span>From</span>
            <select value={link.source_node} onChange={(e) => setLink({ ...link, source_node: e.target.value })} required>
              <option value="">choose…</option>{nodeOptions}
            </select>
          </label>
          <label><span>To</span>
            <select value={link.target_node} onChange={(e) => setLink({ ...link, target_node: e.target.value })} required>
              <option value="">choose…</option>{nodeOptions}
            </select>
          </label>
          <div className="builder-row">
            <label><span>Link type</span>
              <select value={link.link_type} onChange={(e) => setLink({ ...link, link_type: e.target.value })}>
                {LINK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label><span>Role</span>
              <select value={link.role} onChange={(e) => setLink({ ...link, role: e.target.value })}>
                <option value="primary">primary</option>
                <option value="backup">backup</option>
              </select>
            </label>
          </div>
          <div className="config-actions"><button className="btn btn-small btn-primary">Add link</button></div>
        </form>

        <div className="config-form">
          <h3>3. Your additions</h3>
          {!addedNodes.length && !addedLinks.length && <div className="muted small">Nothing added yet.</div>}
          <ul className="builder-list">
            {addedNodes.map((n) => (
              <li key={n.node_id}>
                <span>{NODE_TYPES.find(([v]) => v === n.node_type)?.[1].split(" ")[0]} <b>{n.node_id}</b> <span className={`small tone-${n.status === "online" ? "ok" : "bad"}`}>{n.status}</span></span>
                <button className="btn btn-small btn-danger" onClick={() => run(api.removeNode(n.node_id), `${n.node_id} removed.`)}>Remove</button>
              </li>
            ))}
            {addedLinks.map((l) => (
              <li key={l.link_id}>
                <span>{l.source_node} ↔ {l.target_node} <span className="muted small">{l.link_type} · {l.role}</span></span>
                <button className="btn btn-small btn-danger" onClick={() => run(api.removeLink(l.link_id), `${l.link_id} removed.`)}>Remove</button>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </section>
  );
}
