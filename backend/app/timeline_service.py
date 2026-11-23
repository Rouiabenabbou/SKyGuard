"""
4D timeline recorder (Phase 9).

3D shows WHERE things are; the 4th dimension is WHEN. Every network tick
(2 s, while the simulation runs) this module stores one compact "frame" of
the whole twin in the state_snapshots table:

    {
      "t": 1730541600000,                       # epoch milliseconds
      "nodes":   {"SAT-1": "online", "IOT-002": "quarantined", ...},
      "links":   {"L-SAT-GS": ["online", 34.2, 0.3, true, false], ...},
                  #             status   latency loss in_use blocked
      "routes":  {"IOT-001": {"c": true, "m": "backup", "p": ["IOT-001","BS-5G","CORE"],
                              "l": 18.1, "a": "5g"}, ...},
      "devices": {"IOT-001": {"s": "online", "sec": "normal", "t": 31.2, "h": 22.0,
                              "b": 88.1, "n": 140}, ...},
      "avail": 100.0,
      "alerts": 2                               # open alerts at that moment
    }

The dashboard downloads these frames and replays them in the 3D scene and the
2D map: play, pause, rewind, jump to an event, change speed.
"""
import json
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app import config
from app.models import Device, SecurityAlert, StateSnapshot, iso


def build_frame(snapshot: dict, devices: list[Device], open_alerts: int) -> dict:
    return {
        "t": int(time.time() * 1000),
        "nodes": {n["node_id"]: n["status"] for n in snapshot["nodes"]},
        "links": {
            l["link_id"]: [l["status"], l["latency_ms"], l["packet_loss"], bool(l.get("in_use")), bool(l.get("blocked"))]
            for l in snapshot["links"]
        },
        "routes": {
            d: {"c": r["connected"], "m": r.get("mode"), "p": r.get("path", []), "l": r.get("latency_ms"),
                "a": r.get("access"), "q": bool(r.get("quarantined"))}
            for d, r in snapshot["routes"].items()
        },
        "devices": {
            d.device_id: {"s": d.status, "sec": d.security_status, "t": d.temperature, "h": d.humidity,
                          "b": d.battery, "n": d.message_count}
            for d in devices
        },
        "avail": snapshot["availability"]["current"],
        "alerts": open_alerts,
    }


class TimelineRecorder:
    def __init__(self) -> None:
        self.recorded = 0

    def record(self, db: Session, snapshot: dict, devices: list[Device], session_id: int | None) -> None:
        open_alerts = db.query(SecurityAlert).filter(SecurityAlert.status == "open").count()
        frame = build_frame(snapshot, devices, open_alerts)
        db.add(StateSnapshot(session_id=session_id, data=json.dumps(frame, separators=(",", ":"))))
        db.commit()
        self.recorded += 1
        if self.recorded % 100 == 0:
            self.prune(db)

    @staticmethod
    def prune(db: Session) -> None:
        total = db.query(StateSnapshot).count()
        extra = total - config.TIMELINE_MAX_SNAPSHOTS
        if extra > 0:
            oldest = db.query(StateSnapshot.id).order_by(StateSnapshot.id).limit(extra).subquery()
            db.query(StateSnapshot).filter(StateSnapshot.id.in_(oldest.select())).delete(synchronize_session=False)
            db.commit()

    @staticmethod
    def reset(db: Session) -> None:
        db.query(StateSnapshot).delete()
        db.commit()

    # ------------------------------------------------------------ queries
    @staticmethod
    def range(db: Session) -> dict:
        first = db.query(StateSnapshot).order_by(StateSnapshot.id).first()
        last = db.query(StateSnapshot).order_by(StateSnapshot.id.desc()).first()
        return {
            "count": db.query(StateSnapshot).count(),
            "start": iso(first.timestamp) if first else None,
            "end": iso(last.timestamp) if last else None,
            "start_ms": json.loads(first.data)["t"] if first else None,
            "end_ms": json.loads(last.data)["t"] if last else None,
        }

    @staticmethod
    def frames(db: Session, start: datetime | None, end: datetime | None, max_frames: int) -> list[dict]:
        q = db.query(StateSnapshot)
        if start:
            q = q.filter(StateSnapshot.timestamp >= start)
        if end:
            q = q.filter(StateSnapshot.timestamp <= end)
        ids = [row.id for row in q.with_entities(StateSnapshot.id).order_by(StateSnapshot.id).all()]
        if not ids:
            return []
        step = max(1, -(-len(ids) // max_frames))  # ceil division: keep at most max_frames
        keep = ids[::step]
        if keep[-1] != ids[-1]:
            keep.append(ids[-1])  # always include the newest frame
        rows = db.query(StateSnapshot).filter(StateSnapshot.id.in_(keep)).order_by(StateSnapshot.id).all()
        return [json.loads(r.data) for r in rows]


timeline = TimelineRecorder()
