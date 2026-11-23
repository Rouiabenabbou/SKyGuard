"""
Simplified satellite-5G network simulator.

This is a teaching model, NOT a real satellite handover protocol or a real 5G
core. It gives every link realistic-looking numbers and lets links and nodes
fail, so the dashboard and the 3D twin have something meaningful to show.

Every few seconds (while the simulation runs) it:
1. gives each link new latency / packet-loss / bandwidth values with noise,
2. applies failures: manual overrides, offline nodes, random "rain fade",
3. decides each link's status (online / degraded / offline) from its numbers,
4. works out each IoT device's route to the telecom core,
5. computes network availability, records history, and pushes a snapshot.
"""
import random
import time
from collections import deque

from sqlalchemy.orm import Session

from app import config
from app.detection_engine import detector
from app.event_log import log_event
from app.failover_service import failover
from app.timeline_service import timeline
from app.models import Device, DeviceProfile, DeviceSetting, LinkMetric, NetworkLink, NetworkNode, TopologyAddition
from app.websocket_manager import manager

# Typical values per link type: (latency ms, latency jitter, packet loss %, bandwidth Mbps)
LINK_PROFILES = {
    "satellite": {"latency": 35.0, "jitter": 6.0, "loss": 0.3, "bandwidth": 120.0},  # LEO satellite
    "5g": {"latency": 12.0, "jitter": 3.0, "loss": 0.1, "bandwidth": 500.0},
    "fiber": {"latency": 3.0, "jitter": 0.5, "loss": 0.01, "bandwidth": 10000.0},
    "lan": {"latency": 0.5, "jitter": 0.1, "loss": 0.0, "bandwidth": 1000.0},
}

# When a link counts as "degraded"
DEGRADED_LOSS = 2.0  # packet loss above 2 %
DEGRADED_LATENCY_FACTOR = 2.5  # latency more than 2.5x normal

CORE_NODE = "CORE"
HISTORY_EVERY_N_TICKS = 3  # store link history every 3rd tick (~6 s)


class NetworkSimulator:
    def __init__(self) -> None:
        self.link_overrides: dict[str, str] = {}  # link_id -> "degraded" | "offline"
        self.node_overrides: dict[str, str] = {}  # node_id -> "degraded" | "offline"
        self.rain_fade_until: dict[str, float] = {}  # link_id -> time the fade ends
        self.tick_count = 0
        self.availability_sum = 0.0
        self.availability_ticks = 0
        self.latest: dict = {}
        self.availability_history: deque = deque(maxlen=120)

    # ------------------------------------------------------------ metrics
    @staticmethod
    def _normal_metrics(link_type: str) -> tuple[float, float, float]:
        p = LINK_PROFILES.get(link_type, LINK_PROFILES["fiber"])
        latency = max(0.1, random.gauss(p["latency"], p["jitter"]))
        loss = max(0.0, random.gauss(p["loss"], p["loss"] * 0.5))
        bandwidth = max(1.0, random.gauss(p["bandwidth"], p["bandwidth"] * 0.08))
        return latency, loss, bandwidth

    def _impairment(self, link: NetworkLink, now: float) -> str | None:
        """Why is this link impaired right now? Returns "offline", "degraded" or None."""
        node_states = {self.node_overrides.get(link.source_node), self.node_overrides.get(link.target_node)}
        if "offline" in node_states or self.link_overrides.get(link.link_id) == "offline":
            return "offline"
        if "degraded" in node_states or self.link_overrides.get(link.link_id) == "degraded":
            return "degraded"
        if self.rain_fade_until.get(link.link_id, 0) > now:
            return "degraded"
        return None

    def _update_link(self, link: NetworkLink, now: float) -> None:
        latency, loss, bandwidth = self._normal_metrics(link.link_type)
        impairment = self._impairment(link, now)
        if impairment == "offline":
            latency, loss, bandwidth = 0.0, 100.0, 0.0
        elif impairment == "degraded":
            latency *= random.uniform(3.0, 4.0)
            loss = random.uniform(3.0, 8.0)
            bandwidth *= random.uniform(0.2, 0.4)

        link.latency_ms = round(latency, 1)
        link.packet_loss = round(loss, 2)
        link.bandwidth_mbps = round(bandwidth, 1)

        normal_latency = LINK_PROFILES.get(link.link_type, LINK_PROFILES["fiber"])["latency"]
        if impairment == "offline":
            link.status = "offline"
        elif loss > DEGRADED_LOSS or latency > normal_latency * DEGRADED_LATENCY_FACTOR:
            link.status = "degraded"
        else:
            link.status = "online"

    async def _maybe_start_rain_fade(self, db: Session, links: list[NetworkLink], now: float, session_id) -> None:
        """Small random chance that heavy rain degrades a satellite link for 15-30 s."""
        if not config.NET_RANDOM_EVENTS or random.random() > 1 / 90:
            return
        candidates = [l for l in links if l.link_type == "satellite" and self.rain_fade_until.get(l.link_id, 0) < now]
        if not candidates:
            return
        link = random.choice(candidates)
        duration = random.uniform(15, 30)
        self.rain_fade_until[link.link_id] = now + duration
        await log_event(db, "rain_fade", f"Heavy rain is weakening satellite link {link.link_id} (about {duration:.0f} s)",
                        category="network", session_id=session_id)

    # ------------------------------------------------------------- routes
    @staticmethod
    def _find_path(start: str, links: list[NetworkLink], blocked: set[str] = frozenset(),
                   include_backup: bool = False, exclude: set[str] = frozenset()) -> list[str] | None:
        """Breadth-first search from a device to the core over usable links.
        Primary links only, unless include_backup. Links touching a quarantined
        (blocked) device, and links in `exclude`, are not usable."""
        graph: dict[str, list[str]] = {}
        for l in links:
            if l.source_node in blocked or l.target_node in blocked or l.link_id in exclude:
                continue
            if (l.is_active_path or include_backup) and l.status != "offline":
                graph.setdefault(l.source_node, []).append(l.target_node)
                graph.setdefault(l.target_node, []).append(l.source_node)
        queue, came_from = deque([start]), {start: None}
        while queue:
            node = queue.popleft()
            if node == CORE_NODE:
                path = []
                while node is not None:
                    path.append(node)
                    node = came_from[node]
                return list(reversed(path))
            for nxt in graph.get(node, []):
                if nxt not in came_from:
                    came_from[nxt] = node
                    queue.append(nxt)
        return None

    @staticmethod
    def _describe_path(path: list[str] | None, by_pair: dict) -> dict | None:
        if not path:
            return None
        hops = [by_pair[(a, b)] for a, b in zip(path, path[1:])]
        return {
            "path": path,
            "links": [h.link_id for h in hops],
            "access": hops[0].link_type,
            "latency_ms": round(sum(h.latency_ms for h in hops), 1),
            "degraded": any(h.status == "degraded" for h in hops),
        }

    async def _routes(self, db: Session, devices: list[Device], links: list[NetworkLink], advance: bool) -> dict:
        """Route of every device. The failover manager (Phase 8) picks primary or backup."""
        by_pair = {}
        for l in links:
            by_pair[(l.source_node, l.target_node)] = l
            by_pair[(l.target_node, l.source_node)] = l
        routes = {}
        blocked = {d.device_id for d in devices if d.security_status == "quarantined"}
        now = time.time()
        for d in devices:
            if d.device_id in blocked:
                routes[d.device_id] = {"connected": False, "quarantined": True, "path": [], "links": [],
                                       "access": None, "latency_ms": None, "degraded": False, "mode": "quarantined"}
                continue
            path = self._find_path(d.device_id, links, blocked)
            if path is None:
                # v1.5: keep the device's own primary access link but let the traffic use
                # the network's backup links (e.g. SAT-1 -> GS-2 when GS-1 is down).
                own_backup = {l.link_id for l in links
                              if not l.is_active_path and d.device_id in (l.source_node, l.target_node)}
                path = self._find_path(d.device_id, links, blocked, include_backup=True, exclude=own_backup)
            primary = self._describe_path(path, by_pair)
            # Backup: any path that avoids the device's own primary access links.
            own_primary = {l.link_id for l in links if l.is_active_path and d.device_id in (l.source_node, l.target_node)}
            backup = self._describe_path(
                self._find_path(d.device_id, links, blocked, include_backup=True, exclude=own_primary), by_pair)
            routes[d.device_id] = await failover.decide(db, d.device_id, primary, backup, now, advance=advance)
        return routes

    # -------------------------------------------------------------- tick
    async def tick(self, db: Session, session_id=None, update_metrics: bool = True) -> dict:
        now = time.time()
        links = db.query(NetworkLink).order_by(NetworkLink.link_id).all()
        nodes = db.query(NetworkNode).order_by(NetworkNode.node_id).all()
        devices = db.query(Device).order_by(Device.device_id).all()

        if update_metrics:
            await self._maybe_start_rain_fade(db, links, now, session_id)
            before = {l.link_id: l.status for l in links}
            for l in links:
                self._update_link(l, now)
            node_before = {n.node_id: n.status for n in nodes}
            for n in nodes:
                if n.node_type != "iot_device":
                    n.status = self.node_overrides.get(n.node_id, "online")
            db.commit()
            for l in links:
                if l.status != before[l.link_id]:
                    await log_event(db, f"link_{l.status}", self._describe_change(l, before[l.link_id]),
                                    category="network", session_id=session_id)
                    # Rule E. If a whole node is down, one node alert is enough (no alert per link).
                    node_down = "offline" in (self.node_overrides.get(l.source_node), self.node_overrides.get(l.target_node))
                    if l.status == "offline" and not node_down:
                        await detector.link_failure(db, l.link_id, l.source_node, l.target_node)
            for n in nodes:
                if n.status == "offline" and node_before[n.node_id] != "offline":
                    await detector.node_failure(db, n.node_id, n.name)  # Rule E
            self.tick_count += 1
            if self.tick_count % HISTORY_EVERY_N_TICKS == 0:
                db.add_all(LinkMetric(link_id=l.link_id, status=l.status, latency_ms=l.latency_ms,
                                      packet_loss=l.packet_loss, bandwidth_mbps=l.bandwidth_mbps) for l in links)
                db.commit()

        routes = await self._routes(db, devices, links, advance=update_metrics)
        # Quarantined devices are isolated on purpose, so they don't count against availability.
        counted = {k: r for k, r in routes.items() if not r.get("quarantined")}
        connected = sum(1 for r in counted.values() if r["connected"])
        current = 100.0 * connected / len(counted) if counted else 100.0
        if update_metrics:
            self.availability_sum += current
            self.availability_ticks += 1
            self.availability_history.append({"time": int(now * 1000), "availability": round(current, 1)})

        device_status = {d.device_id: ("quarantined" if d.security_status == "quarantined" else d.status)
                         for d in devices}
        quarantined = {d.device_id for d in devices if d.security_status == "quarantined"}
        in_use = {lid for r in routes.values() for lid in r.get("links", [])}
        # Items the operator added (network builder / Add device) can be removed again.
        added = {a.item_id for a in db.query(TopologyAddition).all()}
        added |= {s.device_id for s in db.query(DeviceSetting).filter(DeviceSetting.added_by_operator.is_(True)).all()}
        profiles = {p.node_id: p.to_dict() for p in db.query(DeviceProfile).all()}  # v1.1: real coordinates
        snapshot = {
            "nodes": [
                {**n.to_dict(), "status": device_status.get(n.node_id, n.status) if n.node_type == "iot_device" else n.status,
                 "added": n.node_id in added, **profiles.get(n.node_id, {})}
                for n in nodes
            ],
            "links": [{**l.to_dict(), "role": "primary" if l.is_active_path else "backup",
                       "in_use": l.link_id in in_use or (l.link_type == "lan" and l.status != "offline"),
                       "rain_fade": self.rain_fade_until.get(l.link_id, 0) > now,
                       "override": self.link_overrides.get(l.link_id),
                       "added": l.link_id in added,
                       "blocked": l.source_node in quarantined or l.target_node in quarantined} for l in links],
            "routes": routes,
            "availability": {
                "current": round(current, 1),
                "session": round(self.availability_sum / self.availability_ticks, 1) if self.availability_ticks else 100.0,
                "connected_devices": connected,
                "total_devices": len(counted),
                "quarantined_devices": len(quarantined),
            },
            "failover_enabled": failover.enabled,
        }
        self.latest = snapshot
        if update_metrics:
            timeline.record(db, snapshot, devices, session_id)  # Phase 9: one frame for the 4D timeline
        await manager.broadcast("network", snapshot)
        return snapshot

    @staticmethod
    def _describe_change(link: NetworkLink, old: str) -> str:
        if link.status == "offline":
            return f"Link {link.link_id} ({link.source_node} -> {link.target_node}) went OFFLINE"
        if link.status == "degraded":
            return (f"Link {link.link_id} degraded: {link.latency_ms} ms latency, "
                    f"{link.packet_loss}% packet loss")
        return f"Link {link.link_id} back to normal (was {old})"

    # ---------------------------------------------------------- controls
    def set_link_state(self, link_id: str, state: str) -> None:
        if state == "auto":
            self.link_overrides.pop(link_id, None)
            self.rain_fade_until.pop(link_id, None)
        else:
            self.link_overrides[link_id] = state

    def set_node_state(self, node_id: str, state: str) -> None:
        if state == "auto":
            self.node_overrides.pop(node_id, None)
        else:
            self.node_overrides[node_id] = state

    def reset(self, db: Session) -> None:
        self.link_overrides.clear()
        self.node_overrides.clear()
        self.rain_fade_until.clear()
        self.tick_count = 0
        self.availability_sum = 0.0
        self.availability_ticks = 0
        self.availability_history.clear()
        db.query(LinkMetric).delete()
        for n in db.query(NetworkNode).all():
            if n.node_type != "iot_device":
                n.status = "online"
        for l in db.query(NetworkLink).all():
            self._update_link(l, time.time())
        db.commit()


network = NetworkSimulator()
