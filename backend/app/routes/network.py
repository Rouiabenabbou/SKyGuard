"""
Network endpoints.

GET  /api/network/topology             nodes + links (+ routes) for drawing the map
GET  /api/network/status               availability and a short summary
GET  /api/network/links/{id}/history   recent performance of one link
POST /api/network/links/{id}/state     {"state": "auto" | "degraded" | "offline"}
POST /api/network/nodes/{id}/state     {"state": "auto" | "degraded" | "offline"}

Network builder (operator designs their own topology):
POST   /api/network/nodes        add a satellite, ground station or 5G base station
DELETE /api/network/nodes/{id}   remove a node you added (and its links)
POST   /api/network/links        connect two nodes (primary or backup link)
DELETE /api/network/links/{id}   remove a link you added

"auto" means: back to normal simulated behaviour.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
import re
import time

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.event_log import log_event
from app.models import DeviceProfile, LinkMetric, NetworkLink, NetworkNode, TopologyAddition
from app.network_simulator import network
from app.simulation_controller import controller

router = APIRouter(prefix="/api/network", tags=["network"])


class StateChange(BaseModel):
    state: Literal["auto", "degraded", "offline"]


async def _snapshot(db: Session) -> dict:
    return network.latest or await network.tick(db, controller.session_id, update_metrics=False)


@router.get("/topology")
async def topology(db: Session = Depends(get_db)):
    return await _snapshot(db)


@router.get("/status")
async def status(db: Session = Depends(get_db)):
    snap = await _snapshot(db)
    links = snap["links"]
    return {
        "availability": snap["availability"],
        "links_online": sum(1 for l in links if l["status"] == "online"),
        "links_degraded": sum(1 for l in links if l["status"] == "degraded"),
        "links_offline": sum(1 for l in links if l["status"] == "offline"),
        "routes": snap["routes"],
        "availability_history": list(network.availability_history),
    }


@router.get("/links/{link_id}/history")
def link_history(link_id: str, limit: int = Query(default=60, ge=1, le=1000), db: Session = Depends(get_db)):
    from app import tenancy
    link = db.get(NetworkLink, link_id)
    hidden = tenancy.current_hidden()
    if link is None or link.source_node in hidden or link.target_node in hidden:
        raise HTTPException(status_code=404, detail=f"Link '{link_id}' not found")
    rows = (db.query(LinkMetric).filter(LinkMetric.link_id == link_id)
            .order_by(LinkMetric.id.desc()).limit(limit).all())
    return {"link_id": link_id, "history": [r.to_dict() for r in reversed(rows)]}


@router.post("/links/{link_id}/state")
async def set_link_state(link_id: str, change: StateChange, db: Session = Depends(get_db)):
    link = db.get(NetworkLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Link '{link_id}' not found")
    network.set_link_state(link_id, change.state)
    await log_event(db, "manual_link_change", f"Operator set link {link_id} to {change.state.upper()}",
                    category="network", session_id=controller.session_id)
    snap = await network.tick(db, controller.session_id)
    return {"message": f"Link {link_id} set to {change.state}", "link": next(l for l in snap["links"] if l["link_id"] == link_id)}


@router.post("/nodes/{node_id}/state")
async def set_node_state(node_id: str, change: StateChange, db: Session = Depends(get_db)):
    node = db.get(NetworkNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    if node.node_type == "iot_device":
        raise HTTPException(status_code=400, detail="IoT device status comes from its own messages; use quarantine in Phase 6")
    network.set_node_state(node_id, change.state)
    await log_event(db, "manual_node_change", f"Operator set {node.name} to {change.state.upper()}",
                    category="network", session_id=controller.session_id)
    snap = await network.tick(db, controller.session_id)
    return {"message": f"Node {node_id} set to {change.state}", "node": next(n for n in snap["nodes"] if n["node_id"] == node_id)}


# ------------------------------------------------------- network builder
NODE_ID = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,23}$")
BUILDABLE_NODES = ("satellite", "ground_station", "base_station")
NODE_LABELS = {"satellite": "satellite", "ground_station": "ground station", "base_station": "5G base station"}


class NewNode(BaseModel):
    node_id: str = Field(min_length=2, max_length=24)
    name: str = Field(default="", max_length=100)
    node_type: Literal["satellite", "ground_station", "base_station"]


class NewLink(BaseModel):
    source_node: str
    target_node: str
    link_type: Literal["satellite", "5g", "fiber", "lan"]
    role: Literal["primary", "backup"] = "primary"


async def _changed(db: Session, event_type: str, text: str) -> dict:
    await log_event(db, event_type, text, category="network", session_id=controller.session_id)
    return await network.tick(db, controller.session_id, update_metrics=False)  # also broadcasts the new map


def _added(db: Session, item_id: str, kind: str) -> bool:
    row = db.get(TopologyAddition, item_id)
    return row is not None and row.kind == kind


@router.post("/nodes", status_code=201)
async def add_node(new: NewNode, db: Session = Depends(get_db)):
    node_id = new.node_id.strip().upper()
    if not NODE_ID.match(node_id):
        raise HTTPException(status_code=400, detail="node ID: 2-24 characters, capital letters, digits and '-', e.g. SAT-2")
    if db.get(NetworkNode, node_id) is not None:
        raise HTTPException(status_code=409, detail=f"a node called {node_id} already exists")
    name = new.name.strip() or f"{node_id} ({NODE_LABELS[new.node_type]})"
    db.add(NetworkNode(node_id=node_id, name=name, node_type=new.node_type, status="online"))
    db.add(TopologyAddition(item_id=node_id, kind="node"))
    db.commit()
    await _changed(db, "topology_node_added", f"Operator added {NODE_LABELS[new.node_type]} {node_id}. "
                   "Connect it with links so traffic can use it.")
    return {"created": True, "node": db.get(NetworkNode, node_id).to_dict()}


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, db: Session = Depends(get_db)):
    node_id = node_id.upper()
    if db.get(NetworkNode, node_id) is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    if not _added(db, node_id, "node"):
        raise HTTPException(status_code=409, detail=f"{node_id} is part of the original network and can't be removed "
                            "(only nodes you added). To simulate a failure use: node {id} offline")
    links = db.query(NetworkLink).filter((NetworkLink.source_node == node_id) | (NetworkLink.target_node == node_id)).all()
    other = {l.target_node if l.source_node == node_id else l.source_node for l in links}
    devices = sorted(n.node_id for n in db.query(NetworkNode).filter(NetworkNode.node_id.in_(other),
                                                                        NetworkNode.node_type == "iot_device"))
    if devices:
        raise HTTPException(status_code=409, detail=f"IoT device(s) {', '.join(devices)} connect through {node_id}; "
                            "remove those devices first")
    for l in links:
        network.link_overrides.pop(l.link_id, None)
        added = db.get(TopologyAddition, l.link_id)
        if added:
            db.delete(added)
        db.delete(l)
    db.flush()
    network.node_overrides.pop(node_id, None)
    db.delete(db.get(NetworkNode, node_id))
    db.delete(db.get(TopologyAddition, node_id))
    profile = db.get(DeviceProfile, node_id)
    if profile is not None:
        db.delete(profile)
    db.commit()
    await _changed(db, "topology_node_removed", f"Operator removed node {node_id} and {len(links)} link(s)")
    return {"removed": True, "node_id": node_id, "links_removed": [l.link_id for l in links]}


@router.post("/links", status_code=201)
async def add_link(new: NewLink, db: Session = Depends(get_db)):
    a, b = new.source_node.strip().upper(), new.target_node.strip().upper()
    if a == b:
        raise HTTPException(status_code=400, detail="a link needs two different nodes")
    for n in (a, b):
        if db.get(NetworkNode, n) is None:
            raise HTTPException(status_code=404, detail=f"Node '{n}' not found")
    exists = db.query(NetworkLink).filter(((NetworkLink.source_node == a) & (NetworkLink.target_node == b)) |
                                          ((NetworkLink.source_node == b) & (NetworkLink.target_node == a))).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"{a} and {b} are already connected by {exists.link_id}")
    link_id = f"L-{a.replace('-', '')}-{b.replace('-', '')}"[:32]
    if db.get(NetworkLink, link_id) is not None:
        raise HTTPException(status_code=409, detail=f"link {link_id} already exists")
    link = NetworkLink(link_id=link_id, source_node=a, target_node=b, link_type=new.link_type,
                       is_active_path=new.role == "primary")
    network._update_link(link, time.time())  # realistic first latency / loss values
    db.add(link)
    db.add(TopologyAddition(item_id=link_id, kind="link"))
    db.commit()
    await _changed(db, "topology_link_added", f"Operator connected {a} ↔ {b} ({new.link_type}, {new.role}) as {link_id}")
    return {"created": True, "link": db.get(NetworkLink, link_id).to_dict()}


@router.delete("/links/{link_id}")
async def delete_link(link_id: str, db: Session = Depends(get_db)):
    link_id = link_id.upper()
    link = db.get(NetworkLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Link '{link_id}' not found")
    if not _added(db, link_id, "link"):
        raise HTTPException(status_code=409, detail=f"{link_id} is part of the original network and can't be removed "
                            "(only links you added). To simulate a failure use: link {id} offline")
    network.link_overrides.pop(link_id, None)
    db.delete(link)
    db.delete(db.get(TopologyAddition, link_id))
    db.commit()
    await _changed(db, "topology_link_removed", f"Operator removed link {link_id}")
    return {"removed": True, "link_id": link_id}


# ---------------------------------------------- v1.5: re-wire a device
class AccessChange(BaseModel):
    access_node: str = Field(min_length=2, max_length=24)
    backup_node: str | None = Field(default=None, max_length=24)


@router.post("/devices/{device_id}/access")
async def change_access(device_id: str, body: AccessChange, db: Session = Depends(get_db)):
    """Connect an IoT device through another satellite / 5G tower (and backup tower).
    Its old access links are replaced; it keeps its readings, alerts and company."""
    from app.device_registry import access_links
    from app.failover_service import failover
    from app.models import Device

    device_id = device_id.upper()
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    access = body.access_node.strip().upper()
    node = db.get(NetworkNode, access)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{access}' not found")
    if node.node_type not in ("satellite", "base_station"):
        raise HTTPException(status_code=400, detail="A device connects through a satellite or a 5G base station.")
    conn = "satellite" if node.node_type == "satellite" else "5g"
    backup = None
    if conn == "satellite":
        backup = (body.backup_node or "BS-5G").strip().upper()
        b = db.get(NetworkNode, backup)
        if b is None or b.node_type != "base_station":
            raise HTTPException(status_code=400, detail="The backup must be a 5G base station.")
    old = db.query(NetworkLink).filter((NetworkLink.source_node == device_id) | (NetworkLink.target_node == device_id)).all()
    for l in old:
        network.link_overrides.pop(l.link_id, None)
        added = db.get(TopologyAddition, l.link_id)
        if added:
            db.delete(added)
        db.delete(l)
    db.flush()
    for data in access_links(device_id, conn, access, backup or "BS-5G"):
        link = NetworkLink(**data)
        network._update_link(link, time.time())
        db.add(link)
    device.connection_type = conn
    failover.states.pop(device_id, None)
    db.commit()
    via = access + (f", backup {backup}" if backup else "")
    await _changed(db, "device_rewired", f"Operator connected {device_id} through {via}")
    return {"device_id": device_id, "connection_type": conn, "access_node": access, "backup_node": backup}
