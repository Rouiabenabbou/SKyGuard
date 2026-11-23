"""
v2.1 (SOC stage 3): Threat Intelligence endpoints (see app/intel.py).

GET    /api/intel/providers         which enrichment services have a key in .env (never the key)
GET    /api/intel/lookup?value=     local IOC + VirusTotal / AbuseIPDB / OTX (cached 24 h)
GET    /api/intel/iocs              local IOC list (?q=, ?active=)
POST   /api/intel/iocs              {"value", "threat", "confidence", "tags", "description", "days"}
PUT    /api/intel/iocs/{id}         {"active", "confidence", "threat", "description"}
DELETE /api/intel/iocs/{id}
GET    /api/intel/sightings?value=  security events and alerts that mention the indicator
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import intel, tenancy
from app.database import get_db
from app.models import Ioc, SecurityAlert, SecurityEvent, utcnow

router = APIRouter(prefix="/api/intel", tags=["intel"])


def _user(request: Request) -> str:
    u = getattr(request.state, "user", None)
    return u.username if u else "analyst"


@router.get("/providers")
def providers():
    return {"providers": intel.providers()}


@router.get("/lookup")
async def lookup(value: str = Query(min_length=3, max_length=300), external: bool = True, db: Session = Depends(get_db)):
    res = await intel.lookup(db, value, use_external=external)
    if res.get("kind") is None:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.get("/iocs")
def list_iocs(q: str | None = Query(default=None, max_length=100), active: bool | None = None, db: Session = Depends(get_db)):
    query = db.query(Ioc)
    if active is not None:
        query = query.filter(Ioc.active.is_(active))
    if q:
        n = f"%{q.lower()}%"
        query = query.filter(or_(Ioc.value.ilike(n), Ioc.threat.ilike(n), Ioc.tags.ilike(n)))
    rows = query.order_by(Ioc.id.desc()).limit(500).all()
    day = utcnow() - timedelta(hours=24)
    out = []
    for r in rows:
        hits = 0
        if r.kind == "ip":
            hq = db.query(SecurityEvent).filter(or_(SecurityEvent.src_ip == r.value, SecurityEvent.dst_ip == r.value),
                                                SecurityEvent.timestamp >= day)
            if tenancy.current().is_company:
                hq = hq.filter(SecurityEvent.device_id.in_(tenancy.devices_of(tenancy.current().company_id)))
            hits = hq.count()
        out.append({**r.to_dict(), "sightings_24h": hits})
    return {"iocs": out}


class IocIn(BaseModel):
    value: str = Field(min_length=3, max_length=300)
    threat: str = Field(default="", max_length=80)
    confidence: int = Field(default=60, ge=0, le=100)
    tags: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    days: int | None = Field(default=None, ge=1, le=3650)


@router.post("/iocs", status_code=201)
def add_ioc(body: IocIn, request: Request, db: Session = Depends(get_db)):
    value = body.value.strip()
    kind = intel.kind_of(value)
    if kind is None:
        raise HTTPException(status_code=400, detail="Give an IP address, a domain, a URL or an MD5/SHA1/SHA256 hash.")
    if kind == "domain" or kind == "hash":
        value = value.lower()
    row = intel.add_ioc(db, kind, value, body.threat.strip() or "Analyst-reported indicator", body.confidence,
                        ",".join(t.strip() for t in body.tags.split(",") if t.strip()), "analyst",
                        body.description.strip(), _user(request), body.days)
    return {"ioc": row.to_dict()}


class IocUpdate(BaseModel):
    active: bool | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    threat: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)


@router.put("/iocs/{ioc_id}")
def update_ioc(ioc_id: int, body: IocUpdate, db: Session = Depends(get_db)):
    row = db.get(Ioc, ioc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="IOC not found")
    for k in ("active", "confidence", "threat", "description"):
        v = getattr(body, k)
        if v is not None:
            setattr(row, k, v)
    db.commit()
    intel.reload(db)
    return {"ioc": row.to_dict()}


@router.delete("/iocs/{ioc_id}")
def delete_ioc(ioc_id: int, db: Session = Depends(get_db)):
    row = db.get(Ioc, ioc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="IOC not found")
    db.delete(row)
    db.commit()
    intel.reload(db)
    return {"deleted": ioc_id}


@router.get("/sightings")
def sightings(value: str = Query(min_length=3, max_length=300), hours: int = Query(default=168, ge=1, le=24 * 30),
              db: Session = Depends(get_db)):
    since = utcnow() - timedelta(hours=hours)
    q = db.query(SecurityEvent).filter(or_(SecurityEvent.src_ip == value, SecurityEvent.dst_ip == value,
                                           SecurityEvent.message.contains(value)), SecurityEvent.timestamp >= since)
    scope = tenancy.current()
    if scope.is_company:
        q = q.filter(SecurityEvent.device_id.in_(tenancy.devices_of(scope.company_id)))
    events = q.order_by(SecurityEvent.id.desc()).limit(100).all()
    hidden = tenancy.current_hidden()
    alerts = [a for a in db.query(SecurityAlert).filter(SecurityAlert.description.contains(value), SecurityAlert.timestamp >= since)
              .order_by(SecurityAlert.id.desc()).limit(50) if a.device_id not in hidden]
    return {"value": value, "events": [e.to_dict() for e in events], "alerts": [a.to_dict() for a in alerts],
            "devices": sorted({e.device_id for e in events if e.device_id})}
