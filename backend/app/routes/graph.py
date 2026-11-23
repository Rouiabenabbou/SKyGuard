"""
v1.5: Network investigation graph (Analytics tab).

GET /api/analytics/graph            assets (network + devices + companies), observables
                                    (alert types, unknown device IDs), their links, indicators
                                    and a 24 h alert timeline, in one reply
GET /api/analytics/graph/layout     the node positions this user saved
PUT /api/analytics/graph/layout     {"positions": {"SAT-1": [x, y], ...}}  save them (operator)

Disposition of a node (like a security investigation tool):
  malicious   quarantined device, or an open high / critical alert
  suspicious  open alerts, or the detector marked it suspicious
  clean       working normally
  unknown     no data (offline)
  asset       shared infrastructure (satellite, ground station, tower, core, SOC)
  common      a company (owner of devices)
A company user only gets its own devices and company (tenancy).
"""
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import tenancy
from app.database import get_db
from app.models import (Company, CompanyDevice, Device, DeviceProfile, GraphLayout, NetworkLink, NetworkNode,
                        SecurityAlert, TopologyAddition, utcnow)

router = APIRouter(prefix="/api/analytics/graph", tags=["analytics"])

SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
NETWORK_ALERTS = {"link_failure", "node_failure"}


def _source(alert: SecurityAlert) -> str:
    if alert.detection_method == "ml" or alert.alert_type == "ml_anomaly":
        return "ml"
    if alert.alert_type in NETWORK_ALERTS:
        return "network"
    return "rules"


@router.get("")
def graph(hours: int = 24, db: Session = Depends(get_db)):
    from app.network_simulator import network

    hours = max(1, min(hours, 168))
    scope = tenancy.current()
    hidden = scope.hidden
    since = utcnow() - timedelta(hours=hours)
    added = {r.item_id for r in db.query(TopologyAddition)}
    profiles = {p.node_id: p for p in db.query(DeviceProfile)}
    devices = {d.device_id: d for d in db.query(Device) if d.device_id not in hidden}
    owners = {r.device_id: r.company_id for r in db.query(CompanyDevice)}
    snap_links = {l["link_id"]: l for l in (network.latest or {}).get("links", [])}
    routes = (network.latest or {}).get("routes", {})

    alerts = [a for a in db.query(SecurityAlert).filter(SecurityAlert.timestamp >= since).order_by(SecurityAlert.id)
              if a.device_id not in hidden]
    open_by_device: dict[str, list[SecurityAlert]] = {}
    for a in alerts:
        if a.status == "open" and a.device_id:
            open_by_device.setdefault(a.device_id, []).append(a)

    nodes, edges = [], []
    for n in db.query(NetworkNode).order_by(NetworkNode.node_id):
        if n.node_id in hidden:
            continue
        p = profiles.get(n.node_id)
        row = {"id": n.node_id, "label": n.name, "kind": n.node_type, "status": n.status,
               "removable": n.node_id in added, "place": (p.address or p.place_type) if p else ""}
        if n.node_type == "iot_device":
            d = devices.get(n.node_id)
            opened = open_by_device.get(n.node_id, [])
            worst = max((SEV_RANK.get(a.severity, 0) for a in opened), default=0)
            if d and d.security_status == "quarantined" or worst >= 3:
                disp = "malicious"
            elif opened or (d and d.security_status == "suspicious"):
                disp = "suspicious"
            elif d is None or d.status != "online":
                disp = "unknown"
            else:
                disp = "clean"
            r = routes.get(n.node_id, {})
            row.update(disposition=disp, company=owners.get(n.node_id), open_alerts=len(opened),
                       device_type=d.device_type if d else "", connection=d.connection_type if d else "",
                       security=d.security_status if d else "", temperature=d.temperature if d else None,
                       route=r.get("path") or [], route_mode=r.get("mode"))
        else:
            row["disposition"] = "asset"
        nodes.append(row)
    node_ids = {n["id"] for n in nodes}

    for l in db.query(NetworkLink).order_by(NetworkLink.link_id):
        if l.source_node not in node_ids or l.target_node not in node_ids:
            continue
        s = snap_links.get(l.link_id, {})
        edges.append({"id": l.link_id, "source": l.source_node, "target": l.target_node, "kind": "link",
                      "link_type": l.link_type, "primary": l.is_active_path, "status": l.status,
                      "in_use": bool(s.get("in_use")), "latency_ms": round(l.latency_ms or 0, 1),
                      "removable": l.link_id in added})

    # companies own devices
    for c in db.query(Company).order_by(Company.company_id):
        if scope.is_company and c.company_id != scope.company_id:
            continue
        cid = f"CO:{c.company_id}"
        nodes.append({"id": cid, "label": c.name, "kind": "company", "disposition": "common", "sector": c.sector,
                      "status": "online", "removable": False})
        for dev, owner in owners.items():
            if owner == c.company_id and dev in node_ids:
                edges.append({"id": f"OWN:{dev}", "source": cid, "target": dev, "kind": "owns"})

    # observables: one per alert type, plus device IDs that aren't registered (rogue / spoofed)
    obs: dict[str, dict] = {}
    for a in alerts:
        key = f"OBS:{a.alert_type}"
        o = obs.setdefault(key, {"id": key, "label": a.alert_type, "kind": "observable", "alert_type": a.alert_type,
                                 "source": _source(a), "count": 0, "open": 0, "worst": 0, "devices": set(),
                                 "last_seen": None, "status": "online", "removable": False})
        o["count"] += 1
        o["open"] += a.status == "open"
        if a.status == "open":
            o["worst"] = max(o["worst"], SEV_RANK.get(a.severity, 0))
        o["last_seen"] = a.timestamp.isoformat() + "Z"
        target = a.device_id
        if target and target not in node_ids:
            rid = target
            if not any(n["id"] == rid for n in nodes):
                nodes.append({"id": rid, "label": f"Unknown device {rid}", "kind": "unknown_device",
                              "disposition": "malicious", "status": "offline", "removable": False})
                node_ids.add(rid)
        if target:
            o["devices"].add(target)
    for o in obs.values():
        o["disposition"] = "malicious" if o["worst"] >= 3 else "suspicious" if o["open"] else "common"
        for dev in sorted(o["devices"]):
            edges.append({"id": f"{o['id']}>{dev}", "source": dev, "target": o["id"], "kind": "alert"})
        o["devices"] = sorted(o["devices"])
        nodes.append(o)

    # timeline: alerts per hour by severity
    start = since.replace(minute=0, second=0, microsecond=0)
    buckets = [{"t": (start + timedelta(hours=i)).isoformat() + "Z", "low": 0, "medium": 0, "high": 0, "critical": 0}
               for i in range(hours + 1)]
    for a in alerts:
        i = int((a.timestamp - start).total_seconds() // 3600)
        if 0 <= i < len(buckets) and a.severity in buckets[i]:
            buckets[i][a.severity] += 1

    indicators = sorted(({"alert_type": o["alert_type"], "source": o["source"], "count": o["count"], "open": o["open"],
                          "disposition": o["disposition"], "devices": o["devices"], "last_seen": o["last_seen"]}
                         for o in obs.values()), key=lambda i: (-i["open"], -i["count"]))
    return {"hours": hours, "nodes": nodes, "edges": edges, "indicators": indicators, "timeline": buckets,
            "can_edit": not scope.is_company}


class LayoutIn(BaseModel):
    positions: dict[str, list[float]] = Field(default_factory=dict)


def _owner(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.username if user is not None else ""


@router.get("/layout")
def get_layout(request: Request, db: Session = Depends(get_db)):
    row = db.get(GraphLayout, _owner(request))
    return {"positions": json.loads(row.positions) if row else {}, "saved_at": row.updated_at.isoformat() + "Z" if row else None}


@router.put("/layout")
def save_layout(body: LayoutIn, request: Request, db: Session = Depends(get_db)):
    pos = {k[:40]: [round(float(v[0]), 1), round(float(v[1]), 1)]
           for k, v in list(body.positions.items())[:500] if isinstance(v, list) and len(v) == 2}
    row = db.get(GraphLayout, _owner(request)) or GraphLayout(owner=_owner(request))
    row.positions, row.updated_at = json.dumps(pos), utcnow()
    db.merge(row)
    db.commit()
    return {"saved": len(pos), "saved_at": row.updated_at.isoformat() + "Z"}
