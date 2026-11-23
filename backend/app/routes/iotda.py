"""
v2.2 Huawei IoTDA routes.

POST /api/iotda/push?token=...   data forwarding target (public, protected by IOTDA_PUSH_TOKEN)
GET  /api/iotda/status           is the bridge on, how many pushes were received
"""
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import config, iotda
from app.database import get_db
from app.telemetry_service import ingest_telemetry

router = APIRouter(prefix="/api/iotda", tags=["iotda"])


@router.post("/push")
async def push(request: Request, token: str = "", db: Session = Depends(get_db)):
    if not iotda.enabled():
        raise HTTPException(404, "IoTDA bridge is off (set IOTDA_PUSH_TOKEN in .env)")
    if not hmac.compare_digest(token.encode(), config.IOTDA_PUSH_TOKEN.encode()):
        raise HTTPException(401, "bad token")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "body must be JSON")
    iotda.stats["received"] += 1
    readings = iotda.readings_from_push(body)
    if not readings:
        iotda.note({"ok": False, "error": "no temperature/humidity in push"}, None)
        return {"ok": False, "accepted": 0}
    results = []
    for r in readings:
        res = await ingest_telemetry(db, r)
        iotda.note(res, r["device_id"])
        results.append({"device_id": r["device_id"], "ok": res.get("ok"), "error": res.get("error")})
    return {"ok": all(x["ok"] for x in results), "accepted": sum(1 for x in results if x["ok"]), "results": results}


@router.get("/status")
def status():
    return iotda.status()
