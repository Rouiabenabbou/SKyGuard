"""
v2.1 (SOC stage 2): Threat Hunting on the security event store.

GET    /api/hunt/events        ?q=&hours=24 | from=&to=, &source=, &limit=, &offset=
                               -> events, total, histogram, top values (facets)
GET    /api/hunt/export        same filters + format=csv|json (max 10 000 rows)
GET    /api/hunt/fields        the query language (fields and examples)
GET    /api/hunt/queries       saved queries (mine + shared) and ready-made templates
POST   /api/hunt/queries       {"name", "query", "hours", "shared"}
DELETE /api/hunt/queries/{id}

Query language (all terms must match):
    field:value          exact (type:mqtt_auth_failure)
    field:a,b            any of (outcome:failure,denied)
    field:10.20.*        wildcard
    -field:value         NOT
    bytes:>100000        numbers: > >= < <=
    "some words"         free text in the event message
"""
import csv
import io
import json
import re
import shlex
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import tenancy
from app.database import get_db
from app.models import SavedQuery, SecurityEvent, utcnow

router = APIRouter(prefix="/api/hunt", tags=["hunt"])

FIELDS = {
    "type": ("event_type",), "category": ("category",), "severity": ("severity",), "source": ("source",),
    "device": ("device_id",), "src": ("src_ip",), "dst": ("dst_ip",), "ip": ("src_ip", "dst_ip"),
    "sport": ("src_port",), "dport": ("dst_port",), "port": ("src_port", "dst_port"), "proto": ("protocol",),
    "client": ("mqtt_client",), "topic": ("mqtt_topic",), "user": ("username",), "outcome": ("outcome",),
    "bytes": ("bytes",), "id": ("id",),
}
NUMERIC = {"src_port", "dst_port", "bytes", "id"}
TEMPLATES = [
    {"name": "MQTT login failures", "query": "type:mqtt_auth_failure", "hours": 24},
    {"name": "Logins from outside", "query": "type:mqtt_connect outcome:success -src:10.*", "hours": 24},
    {"name": "Refused publish / subscribe", "query": "type:mqtt_publish_denied,mqtt_subscribe_denied", "hours": 24},
    {"name": "Outbound to the internet", "query": "type:net_connection,outbound_transfer -dst:10.*", "hours": 24},
    {"name": "Large transfers (> 1 MB)", "query": "bytes:>1000000", "hours": 168},
    {"name": "Port scans", "query": "type:net_conn_attempt outcome:denied", "hours": 24},
    {"name": "5G authentication failures", "query": "category:5g outcome:failure", "hours": 24},
    {"name": "GNSS samples", "query": "category:gnss", "hours": 24},
    {"name": "Config changes", "query": "type:config_change", "hours": 168},
    {"name": "Normal MQTT traffic (flows)", "query": "category:flow", "hours": 1},
]


def _user(request: Request) -> str:
    u = getattr(request.state, "user", None)
    return u.username if u else ""


def _cond(col, value: str):
    c = getattr(SecurityEvent, col)
    if col in NUMERIC:
        m = re.fullmatch(r"(>=|<=|>|<)?(\d+)", value)
        if not m:
            raise HTTPException(status_code=400, detail=f"'{value}' is not a number")
        op, n = m.group(1) or "=", int(m.group(2))
        return {"=": c == n, ">": c > n, ">=": c >= n, "<": c < n, "<=": c <= n}[op]
    parts = [v for v in value.split(",") if v]
    conds = []
    for v in parts:
        if "*" in v:
            conds.append(func.lower(c).like(v.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("*", "%"), escape="\\"))
        else:
            conds.append(func.lower(c) == v.lower())
    return or_(*conds) if len(conds) > 1 else conds[0]


def build(db: Session, q: str | None, hours: float | None, start: str | None, end: str | None, source: str | None):
    query = db.query(SecurityEvent)
    if start or end:
        try:
            if start:
                query = query.filter(SecurityEvent.timestamp >= datetime.fromisoformat(start.replace("Z", "")))
            if end:
                query = query.filter(SecurityEvent.timestamp <= datetime.fromisoformat(end.replace("Z", "")))
        except ValueError:
            raise HTTPException(status_code=400, detail="from / to must be ISO times, e.g. 2026-11-04T10:00:00")
    else:
        query = query.filter(SecurityEvent.timestamp >= utcnow() - timedelta(hours=hours or 24))
    if source and source != "all":
        query = query.filter(SecurityEvent.source == source)
    scope = tenancy.current()
    if scope.is_company:
        query = query.filter(SecurityEvent.device_id.in_(tenancy.devices_of(scope.company_id)))
    try:
        tokens = shlex.split(q or "")
    except ValueError:
        raise HTTPException(status_code=400, detail="Unbalanced quotes in the query")
    for tok in tokens:
        neg = tok.startswith("-") and ":" in tok
        body = tok[1:] if neg else tok
        m = re.fullmatch(r"([a-z_]+):(.+)", body)
        if m and m.group(1) in FIELDS:
            cols = FIELDS[m.group(1)]
            cond = or_(*[_cond(c, m.group(2)) for c in cols]) if len(cols) > 1 else _cond(cols[0], m.group(2))
            if neg:  # NULL columns count as "not equal"
                nulls = [getattr(SecurityEvent, c).is_(None) for c in cols]
                cond = or_(~cond, *nulls)
            query = query.filter(cond)
        elif m:
            raise HTTPException(status_code=400, detail=f"Unknown field '{m.group(1)}'. Fields: {', '.join(FIELDS)}")
        else:
            query = query.filter(func.lower(SecurityEvent.message).contains(tok.lower()))
    return query


def _hist(times: list[datetime], start: datetime, end: datetime, buckets: int = 30) -> list[dict]:
    span = max((end - start).total_seconds(), 60)
    size = span / buckets
    out = [{"t": (start + timedelta(seconds=i * size)).isoformat(timespec="seconds") + "Z", "count": 0} for i in range(buckets)]
    for t in times:
        i = int((t - start).total_seconds() // size)
        if 0 <= i < buckets:
            out[i]["count"] += 1
    return out


@router.get("/fields")
def fields():
    return {"fields": {k: list(v) for k, v in FIELDS.items()}, "templates": TEMPLATES,
            "examples": ["type:mqtt_auth_failure src:203.0.113.*", "device:IOT-003 -dst:10.*", "bytes:>1000000",
                         "category:5g outcome:failure", '"refused by ACL"']}


@router.get("/events")
def events(q: str | None = Query(default=None, max_length=500), hours: float = Query(default=24, gt=0, le=24 * 30),
           start: str | None = Query(default=None, alias="from"), end: str | None = Query(default=None, alias="to"),
           source: str | None = None, limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0),
           db: Session = Depends(get_db)):
    query = build(db, q, hours, start, end, source)
    total = query.count()
    rows = query.order_by(SecurityEvent.id.desc()).offset(offset).limit(limit).all()
    stats = query.with_entities(SecurityEvent.timestamp, SecurityEvent.event_type, SecurityEvent.src_ip,
                                SecurityEvent.dst_ip, SecurityEvent.device_id, SecurityEvent.dst_port,
                                SecurityEvent.protocol, SecurityEvent.source).order_by(SecurityEvent.id.desc()).limit(20000).all()
    t_end = datetime.fromisoformat(end.replace("Z", "")) if end else utcnow()
    t_start = datetime.fromisoformat(start.replace("Z", "")) if start else (
        min((s[0] for s in stats), default=t_end - timedelta(hours=hours)) if end else t_end - timedelta(hours=hours))
    facet_names = ["event_type", "src_ip", "dst_ip", "device_id", "dst_port", "protocol", "source"]
    facets = {}
    for i, name in enumerate(facet_names, start=1):
        facets[name] = [{"value": v, "count": n} for v, n in Counter(s[i] for s in stats if s[i] not in (None, "")).most_common(6)]
    return {"total": total, "events": [r.to_dict() for r in rows], "histogram": _hist([s[0] for s in stats], t_start, t_end),
            "facets": facets, "sampled": len(stats) < total, "from": t_start.isoformat() + "Z", "to": t_end.isoformat() + "Z"}


@router.get("/export")
def export(q: str | None = Query(default=None, max_length=500), hours: float = Query(default=24, gt=0, le=24 * 30),
           start: str | None = Query(default=None, alias="from"), end: str | None = Query(default=None, alias="to"),
           source: str | None = None, format: str = Query(default="csv", pattern="^(csv|json)$"),
           db: Session = Depends(get_db)):
    rows = [r.to_dict() for r in build(db, q, hours, start, end, source).order_by(SecurityEvent.id).limit(10000)]
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    if format == "json":
        body = json.dumps({"query": q or "", "exported_at": utcnow().isoformat() + "Z", "count": len(rows), "events": rows}, indent=1)
        return StreamingResponse(iter([body]), media_type="application/json",
                                 headers={"Content-Disposition": f'attachment; filename="hunt-{stamp}.json"'})
    cols = ["id", "timestamp", "source", "event_type", "category", "severity", "device_id", "src_ip", "src_port", "dst_ip",
            "dst_port", "protocol", "mqtt_client", "mqtt_topic", "username", "outcome", "bytes", "message"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] if r[c] is not None else "" for c in cols])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="hunt-{stamp}.csv"'})


class QueryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    query: str = Field(default="", max_length=500)
    hours: int = Field(default=24, ge=1, le=24 * 30)
    shared: bool = False


@router.get("/queries")
def list_queries(request: Request, db: Session = Depends(get_db)):
    me = _user(request)
    rows = db.query(SavedQuery).filter(or_(SavedQuery.owner == me, SavedQuery.shared.is_(True))).order_by(SavedQuery.name).all()
    return {"queries": [r.to_dict() for r in rows], "templates": TEMPLATES}


@router.post("/queries", status_code=201)
def save_query(body: QueryIn, request: Request, db: Session = Depends(get_db)):
    build(db, body.query, body.hours, None, None, None).limit(1).all()  # refuse a query that does not parse
    row = SavedQuery(owner=_user(request), name=body.name.strip(), query=body.query.strip(), hours=body.hours, shared=body.shared)
    db.add(row)
    db.commit()
    return {"query": row.to_dict()}


@router.delete("/queries/{query_id}")
def delete_query(query_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.get(SavedQuery, query_id)
    user = getattr(request.state, "user", None)
    if row is None or (row.owner != _user(request) and not (user is None or user.role == "admin")):
        raise HTTPException(status_code=404, detail="Saved query not found")
    db.delete(row)
    db.commit()
    return {"deleted": query_id}
