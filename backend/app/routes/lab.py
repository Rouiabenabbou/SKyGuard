"""
v2.2: real-hardware lab test report.

GET /api/lab/report?hours=24            numbers measured from LAB readings (ESP32 over MQTT or Huawei IoTDA)
GET /api/lab/report?hours=24&format=md  the same as a Markdown file for the report / competition documents

Everything is computed from stored rows of real boards; simulated devices are
left out. Nothing is estimated: with no LAB readings the report says so.
"""
import statistics
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import SecurityAlert, Telemetry, utcnow

router = APIRouter(prefix="/api/lab", tags=["lab"])


def _pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def build_report(db: Session, hours: float) -> dict:
    since = utcnow() - timedelta(hours=hours)
    rows = (db.query(Telemetry).filter(Telemetry.timestamp >= since,
                                       or_(Telemetry.source.like("esp32%"), Telemetry.source.like("iotda%")))
            .order_by(Telemetry.device_id, Telemetry.timestamp).all())
    interval = config.LAB_SEND_INTERVAL_SECONDS
    by_dev: dict[str, list[Telemetry]] = {}
    for r in rows:
        by_dev.setdefault(r.device_id, []).append(r)
    devices = []
    for dev, rs in by_dev.items():
        times = [r.timestamp for r in rs]
        span = (times[-1] - times[0]).total_seconds()
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        expected = int(round(span / interval)) + 1
        temps = [r.temperature for r in rs]
        hums = [r.humidity for r in rs]
        alerts = (db.query(SecurityAlert).filter(SecurityAlert.device_id == dev, SecurityAlert.timestamp >= since).all())
        long_gaps = [g for g in gaps if g > 3 * interval]
        devices.append({
            "device_id": dev,
            "readings": len(rs),
            "first": times[0].isoformat() + "Z", "last": times[-1].isoformat() + "Z",
            "span_minutes": round(span / 60, 1),
            "expected_readings": expected,
            "delivery_percent": round(min(100.0, 100 * len(rs) / expected), 1) if expected else None,
            "interval_mean_s": round(statistics.mean(gaps), 2) if gaps else None,
            "interval_p95_s": round(_pct(gaps, 95), 2) if gaps else None,
            "interval_max_s": round(max(gaps), 1) if gaps else None,
            "jitter_s": round(statistics.pstdev(gaps), 2) if len(gaps) > 1 else None,
            "outages": len(long_gaps), "outage_seconds": round(sum(long_gaps)),
            "transport": dict(Counter(r.source.split("/", 1)[-1] for r in rs)),
            "temperature": {"min": min(temps), "avg": round(statistics.mean(temps), 2), "max": max(temps)},
            "humidity": {"min": min(hums), "avg": round(statistics.mean(hums), 2), "max": max(hums)},
            "alerts": dict(Counter(a.alert_type for a in alerts)),
        })
    return {"hours": hours, "generated_at": utcnow().isoformat() + "Z", "expected_interval_s": interval,
            "lab_readings": len(rows), "devices": devices,
            "note": None if rows else "No readings from a real board in this period. Connect the ESP32 (MQTT or Huawei IoTDA) and run the lab test."}


def to_markdown(r: dict) -> str:
    out = [f"# CyberShield lab test report", "",
           f"Real hardware only (ESP32 + DHT22). Period: last {r['hours']:g} h, generated {r['generated_at']}.",
           f"Expected send interval: {r['expected_interval_s']:g} s.", ""]
    if r["note"]:
        return "\n".join(out + [r["note"], ""])
    for d in r["devices"]:
        out += [f"## {d['device_id']}", "", "| Measure | Value |", "|---|---|",
                f"| Readings received | {d['readings']} of {d['expected_readings']} expected |",
                f"| Delivery | {d['delivery_percent']} % |",
                f"| Test length | {d['span_minutes']} min ({d['first']} to {d['last']}) |",
                f"| Interval mean / p95 / max | {d['interval_mean_s']} / {d['interval_p95_s']} / {d['interval_max_s']} s |",
                f"| Jitter (std of interval) | {d['jitter_s']} s |",
                f"| Outages (> 3 intervals) | {d['outages']} ({d['outage_seconds']} s) |",
                f"| Transport | {', '.join(f'{k}: {v}' for k, v in d['transport'].items())} |",
                f"| Temperature min / avg / max | {d['temperature']['min']} / {d['temperature']['avg']} / {d['temperature']['max']} C |",
                f"| Humidity min / avg / max | {d['humidity']['min']} / {d['humidity']['avg']} / {d['humidity']['max']} % |",
                f"| Alerts | {', '.join(f'{k}: {v}' for k, v in d['alerts'].items()) or 'none'} |", ""]
    return "\n".join(out)


@router.get("/report")
def report(hours: float = Query(24, gt=0, le=24 * 30), format: str = "json", db: Session = Depends(get_db)):
    r = build_report(db, hours)
    if format == "md":
        return PlainTextResponse(to_markdown(r), media_type="text/markdown",
                                 headers={"Content-Disposition": 'attachment; filename="cybershield-lab-report.md"'})
    return r
