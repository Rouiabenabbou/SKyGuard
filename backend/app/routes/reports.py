"""
Exports and the session report (Phase 10).

GET /api/export/telemetry.csv     all stored readings
GET /api/export/alerts.csv        all security alerts
GET /api/export/events.csv        the event log
GET /api/export/failover.csv      failover / failback / outage records
GET /api/export/quarantine.csv    quarantine records
POST /api/export/{name}/save      write the same CSV into the project's exports/ folder
                                  (for browsers that block downloads, e.g. the VS Code preview)
GET /api/report/summary           one JSON summary of the current session
                                  (used by the Report tab, which can be printed to PDF)
"""
import csv
import io
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import config, tenancy
from app.database import get_db
from app.failover_service import failover
from app.models import (Device, FailoverEvent, NetworkEvent, QuarantineRecord, SecurityAlert, SimulationSession,
                        Telemetry, TelemetryHourly, iso, utcnow)
from app.network_simulator import network
from app.simulation_controller import controller

router = APIRouter(prefix="/api", tags=["reports"])

EXPORTS = {
    "telemetry": (Telemetry, ["id", "device_id", "temperature", "humidity", "battery", "source", "timestamp"]),
    "alerts": (SecurityAlert, ["id", "device_id", "alert_type", "severity", "description", "detection_method", "status", "timestamp"]),
    "events": (NetworkEvent, ["id", "session_id", "event_type", "category", "device_id", "description", "timestamp"]),
    "failover": (FailoverEvent, ["id", "device_id", "kind", "from_mode", "to_mode", "reason", "from_path", "to_path",
                                 "started_at", "completed_at", "handover_ms", "interruption_ms", "readings_lost"]),
    "hourly": (TelemetryHourly, ["id", "device_id", "hour", "readings", "temp_avg", "temp_min", "temp_max",
                                 "hum_avg", "battery_avg"]),  # v1.3 long-term hourly data
    "quarantine": (QuarantineRecord, ["id", "device_id", "reason", "triggered_by", "alert_id", "blocked_messages",
                                      "started_at", "released_at"]),
}


def build_csv(name: str, db: Session) -> tuple[str, str, int]:
    """Return (filename, csv_text, row_count) for one export."""
    if name not in EXPORTS:
        raise HTTPException(status_code=404, detail=f"Unknown export '{name}'. Choose one of: {', '.join(EXPORTS)}")
    model, columns = EXPORTS[name]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    rows = 0
    hidden = tenancy.current_hidden()  # v1.2: a company only exports its own devices
    for row in db.query(model).order_by(model.id).yield_per(500):
        d = row.to_dict()
        if d.get("device_id") in hidden:
            continue
        writer.writerow([d.get(c) for c in columns])
        rows += 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"cybershield-{name}-{stamp}.csv", buffer.getvalue(), rows


@router.get("/export/{name}.csv")
def export_csv(name: str, db: Session = Depends(get_db)):
    filename, text, _ = build_csv(name, db)
    return StreamingResponse(
        iter([text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/{name}/save")
def save_csv(name: str, db: Session = Depends(get_db)):
    """Write the CSV into <project>/exports/ on this computer and return the path.
    "all" saves every export at once."""
    names = list(EXPORTS) if name == "all" else [name]
    config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for n in names:
        filename, text, rows = build_csv(n, db)
        path = config.EXPORTS_DIR / filename
        path.write_text(text, encoding="utf-8-sig")  # BOM so Excel opens it with the right characters
        saved.append({"name": n, "path": str(path), "rows": rows})
    return {"folder": str(config.EXPORTS_DIR), "files": saved}


@router.get("/report/summary")
def summary(db: Session = Depends(get_db)):
    session = db.get(SimulationSession, controller.session_id) if controller.session_id else None
    hidden = tenancy.current_hidden()  # v1.2: a company's report covers only its own devices
    devices = [d for d in db.query(Device).order_by(Device.device_id) if d.device_id not in hidden]
    alerts = [a for a in db.query(SecurityAlert).order_by(SecurityAlert.id) if a.device_id not in hidden]
    quarantines = [q for q in db.query(QuarantineRecord).order_by(QuarantineRecord.id) if q.device_id not in hidden]
    readings_q = db.query(Telemetry)
    events_q = db.query(NetworkEvent)
    if hidden:
        readings_q = readings_q.filter(Telemetry.device_id.notin_(hidden))
        events_q = events_q.filter((NetworkEvent.device_id.is_(None)) | (NetworkEvent.device_id.notin_(hidden)))

    per_device = []
    for d in devices:
        readings = db.query(Telemetry).filter(Telemetry.device_id == d.device_id)
        temps = [r.temperature for r in readings]
        per_device.append({
            "device_id": d.device_id,
            "device_name": d.device_name,
            "status": d.status,
            "security_status": d.security_status,
            "readings": len(temps),
            "temperature_avg": round(sum(temps) / len(temps), 1) if temps else None,
            "temperature_min": min(temps) if temps else None,
            "temperature_max": max(temps) if temps else None,
            "alerts": sum(1 for a in alerts if a.device_id == d.device_id),
            "quarantines": sum(1 for q in quarantines if q.device_id == d.device_id),
        })

    # alerts per minute, for the "alerts over time" chart
    per_minute = Counter(a.timestamp.replace(second=0, microsecond=0) for a in alerts)
    started = session.started_at if session else None
    return {
        "generated_at": iso(utcnow()),
        "app": {"name": config.APP_NAME, "version": config.APP_VERSION},
        "company": tenancy.current().company_name or None,
        "session": {
            "id": session.id if session else None,
            "status": session.status if session else None,
            "started_at": iso(started),
            "duration_s": round((utcnow() - started).total_seconds()) if started else 0,
        },
        "totals": {
            "devices": len(devices),
            "readings": readings_q.count(),
            "events": events_q.count(),
            "alerts": len(alerts),
            "open_alerts": sum(1 for a in alerts if a.status == "open"),
            "quarantines": len(quarantines),
            "blocked_messages": sum(q.blocked_messages for q in quarantines),
        },
        "alerts_by_type": dict(Counter(a.alert_type for a in alerts)),
        "alerts_by_severity": dict(Counter(a.severity for a in alerts)),
        "alerts_per_minute": [{"minute": iso(m), "count": c} for m, c in sorted(per_minute.items())],
        "devices": per_device,
        "network": {
            "availability_now": network.latest.get("availability", {}).get("current"),
            "availability_session": network.latest.get("availability", {}).get("session"),
        },
        "failover": failover.summary(db)["stats"],
        "simulated": True,
        "disclaimer": "All devices, attacks, quarantine actions and network events in this report are simulated.",
    }
