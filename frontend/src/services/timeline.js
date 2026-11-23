// Helpers for the 4D timeline: find the frame at a moment, and turn a compact
// recorded frame back into the same shapes the live dashboard uses.

// Largest index whose frame time is <= t (binary search; frames are in time order).
export function frameIndexAt(frames, t) {
  let lo = 0;
  let hi = frames.length - 1;
  if (hi < 0 || t < frames[0].t) return 0;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].t <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

// Rebuild a network snapshot from a frame. Static details (names, link endpoints)
// come from the live snapshot, the state at that moment comes from the frame.
export function frameToNetwork(frame, live) {
  if (!frame || !live) return live;
  const nodes = live.nodes.map((n) => ({ ...n, status: frame.nodes[n.node_id] ?? n.status }));
  const links = live.links.map((l) => {
    const f = frame.links[l.link_id];
    if (!f) return l;
    const [status, latency_ms, packet_loss, in_use, blocked] = f;
    return { ...l, status, latency_ms, packet_loss, in_use, blocked, rain_fade: false, override: null };
  });
  const routes = Object.fromEntries(
    Object.entries(frame.routes).map(([id, r]) => {
      const hops = r.p ?? [];
      const linkIds = [];
      for (let i = 0; i < hops.length - 1; i++) {
        const l = live.links.find(
          (x) => (x.source_node === hops[i] && x.target_node === hops[i + 1]) || (x.target_node === hops[i] && x.source_node === hops[i + 1])
        );
        if (l) linkIds.push(l.link_id);
      }
      return [id, { connected: r.c, mode: r.m, path: hops, links: linkIds, latency_ms: r.l, access: r.a, quarantined: r.q, degraded: false }];
    })
  );
  return { ...live, nodes, links, routes, availability: { ...live.availability, current: frame.avail } };
}

export function frameToDevices(frame, liveDevices) {
  if (!frame) return liveDevices;
  const out = { ...liveDevices };
  Object.entries(frame.devices).forEach(([id, d]) => {
    out[id] = {
      ...(liveDevices[id] ?? { device_id: id, device_name: id }),
      status: d.s,
      security_status: d.sec,
      temperature: d.t,
      humidity: d.h,
      battery: d.b,
      message_count: d.n,
    };
  });
  return out;
}

// Events that deserve a marker on the timeline.
export function isKeyEvent(e) {
  if (e.category === "security") return true;
  return /failover|failback|connectivity|drill|offline|quarantin|released|attack|simulation_started/.test(e.event_type);
}

export function clock(ms) {
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
