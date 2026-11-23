"""
Long-term data and analytics (v1.3, "big data").

The live tables (telemetry, security_alerts) hold the current session and are
emptied by Reset. For months of data the project keeps a small data warehouse:

* telemetry_archive  raw readings of the long-term history (can be generated: months
                     of realistic readings with day/night cycles, seasons and incidents)
* telemetry_hourly   one summary row per device per hour (avg/min/max)  <- Analytics reads this
* alert_hourly       number of alerts per device, type and hour          <- trends + heatmap

Live readings are summarised every few minutes (and just before a Reset), so
nothing is lost when a session ends. Analytics only reads the hourly tables, so
it stays fast with millions of raw readings.

Everything here is computed with plain Python + SQLAlchemy, so it works the same
on SQLite (your PC) and PostgreSQL (Huawei Cloud RDS).
"""
import math
import random
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, insert
from sqlalchemy.orm import Session

from app import config
from app.models import (AlertHourly, Device, SecurityAlert, Telemetry, TelemetryArchive, TelemetryHourly,
                        utcnow)

MAX_DAYS = 365


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


# ================================================================ rollup
def _upsert_hourly(db: Session, rows: dict) -> int:
    """rows: (device_id, hour) -> summary dict. A bucket is only replaced by a summary
    built from at least as many readings (so a Reset never shrinks old hours)."""
    if not rows:
        return 0
    hours = [h for _, h in rows]
    existing = {(r.device_id, r.hour): r for r in db.query(TelemetryHourly)
                .filter(TelemetryHourly.hour >= min(hours), TelemetryHourly.hour <= max(hours))}
    changed = 0
    for key, s in rows.items():
        old = existing.get(key)
        if old is None:
            db.add(TelemetryHourly(device_id=key[0], hour=key[1], **s))
            changed += 1
        elif s["readings"] >= old.readings:
            for k, v in s.items():
                setattr(old, k, v)
            changed += 1
    return changed


def _summarise(readings) -> dict:
    """readings: list of (temperature, humidity, battery)."""
    temps = [r[0] for r in readings]
    return {"readings": len(readings), "temp_avg": sum(temps) / len(temps), "temp_min": min(temps),
            "temp_max": max(temps), "hum_avg": sum(r[1] for r in readings) / len(readings),
            "battery_avg": sum(r[2] for r in readings) / len(readings)}


def rollup_live(db: Session, hours_back: int | None = 3) -> dict:
    """Summarise the live readings and alerts of the last `hours_back` hours (None = all)."""
    since = floor_hour(utcnow()) - timedelta(hours=hours_back) if hours_back is not None else None
    q = db.query(Telemetry.device_id, Telemetry.timestamp, Telemetry.temperature, Telemetry.humidity, Telemetry.battery)
    if since is not None:
        q = q.filter(Telemetry.timestamp >= since)
    groups = defaultdict(list)
    for device_id, ts, t, h, b in q:
        groups[(device_id, floor_hour(ts))].append((t, h, b))
    hourly = _upsert_hourly(db, {k: _summarise(v) for k, v in groups.items()})

    aq = db.query(SecurityAlert.device_id, SecurityAlert.timestamp, SecurityAlert.alert_type, SecurityAlert.severity)
    if since is not None:
        aq = aq.filter(SecurityAlert.timestamp >= since)
    counts = Counter((d or "-", floor_hour(ts), t, s) for d, ts, t, s in aq)
    alerts = 0
    if counts:
        hours = [k[1] for k in counts]
        existing = {(r.device_id, r.hour, r.alert_type, r.severity): r for r in db.query(AlertHourly)
                    .filter(AlertHourly.hour >= min(hours), AlertHourly.hour <= max(hours))}
        for key, n in counts.items():
            old = existing.get(key)
            if old is None:
                db.add(AlertHourly(device_id=key[0], hour=key[1], alert_type=key[2], severity=key[3], count=n))
                alerts += 1
            elif n > old.count:
                old.count = n
                alerts += 1
    db.commit()
    return {"hourly_rows": hourly, "alert_rows": alerts}


# ======================================================= history generator
# How each kind of place behaves (base °C, day/night swing °C, base humidity %).
PLACE_CLIMATE = {
    "desert": (27, 11, 18), "farm": (19, 7, 62), "company": (23, 1.5, 45), "offices": (23, 1.5, 45),
    "lab": (22.5, 1.2, 42), "factory": (26, 3, 40), "home": (21, 2, 50), "hospital": (22, 1, 45),
    "school": (21, 2.5, 48),
}
INCIDENTS = [  # (alert type, severity, weight)
    ("excessive_message_rate", "high", 3), ("connection_storm", "high", 2), ("abnormal_reading", "medium", 3),
    ("unauthorized_device", "critical", 1), ("spoofing_attempt", "critical", 1),
]


def _climate(db: Session, device: Device) -> tuple[float, float, float]:
    from app.models import DeviceProfile
    p = db.get(DeviceProfile, device.device_id)
    if p and p.place_type in PLACE_CLIMATE:
        return PLACE_CLIMATE[p.place_type]
    mid = (device.temp_min + device.temp_max) / 2 if device.temp_max - device.temp_min < 60 else 24
    return (mid, 3, (device.humidity_min + device.humidity_max) / 2)


def _incident_hours(rng: random.Random, start: datetime, hours: int) -> dict[int, tuple[str, str]]:
    """Pick the hours with a (simulated) incident. More at night (01-05 h) and at weekends,
    like real attack traffic, so the heatmap shows a pattern."""
    out = {}
    for i in range(hours):
        t = start + timedelta(hours=i)
        chance = 0.004
        if 1 <= t.hour <= 5:
            chance *= 4
        if t.weekday() >= 5:
            chance *= 1.8
        if rng.random() < chance:
            kind = rng.choices(INCIDENTS, weights=[w for *_, w in INCIDENTS])[0]
            out[i] = (kind[0], kind[1])
    return out


class HistoryJob:
    """State of the background history generator (one at a time)."""

    def __init__(self) -> None:
        self.state = {"running": False, "progress": 0.0, "message": "idle", "rows": 0, "seconds": 0.0}

    def run(self, days: int, interval_minutes: int, seed: int | None = None) -> dict:
        """Generate `days` of readings for every device (blocking: call it in a thread)."""
        from app.database import SessionLocal

        days = max(1, min(MAX_DAYS, int(days)))
        interval_minutes = max(1, min(60, int(interval_minutes)))
        self.state = {"running": True, "progress": 0.0, "message": "starting", "rows": 0, "seconds": 0.0}
        started = time.time()
        rng = random.Random(seed)
        try:
            with SessionLocal() as db:
                devices = db.query(Device).order_by(Device.device_id).all()
                end = floor_hour(utcnow()) - timedelta(hours=1)
                first_live = db.query(func.min(Telemetry.timestamp)).scalar()
                if first_live is not None:
                    end = min(end, floor_hour(first_live) - timedelta(hours=1))
                start = end - timedelta(days=days)
                hours = days * 24
                per_hour = max(1, 60 // interval_minutes)
                done_hours = {(d, h) for d, h in db.query(TelemetryHourly.device_id, TelemetryHourly.hour)
                              .filter(TelemetryHourly.hour >= start, TelemetryHourly.hour < end)}
                total = len(devices) * hours
                step = 0
                for device in devices:
                    base, swing, hum_base = _climate(db, device)
                    incidents = _incident_hours(rng, start, hours)
                    if device.device_id == "IOT-003" or "farm" in (device.location or "").lower():
                        pass  # farm: night movement alerts added below
                    raw, hourly, alerts = [], [], []
                    battery = rng.uniform(70, 100)
                    for i in range(hours):
                        hour = start + timedelta(hours=i)
                        step += 1
                        if (device.device_id, hour) in done_hours:
                            continue
                        day_index = i / 24
                        season = 2.5 * math.sin(2 * math.pi * (hour.timetuple().tm_yday - 110) / 365)
                        drift = 0.6 * math.sin(day_index / 9)  # slow weather changes over days
                        bucket = []
                        for k in range(per_hour):
                            ts = hour + timedelta(minutes=k * interval_minutes + rng.random() * 0.9)
                            daily = math.sin(2 * math.pi * ((ts.hour + ts.minute / 60) - 9) / 24)
                            t = base + season + drift + swing * daily + rng.gauss(0, 0.35)
                            h = max(3.0, min(98.0, hum_base - 1.6 * swing * daily + rng.gauss(0, 1.2)))
                            # solar battery: charges in the day, drains at night
                            battery += (0.55 if 8 <= ts.hour <= 17 else -0.35) * interval_minutes / 10
                            battery = max(15.0, min(100.0, battery))
                            if i in incidents and incidents[i][0] == "abnormal_reading" and k == 0:
                                t += rng.choice([-1, 1]) * rng.uniform(25, 40)  # the spike that raised the alert
                            r = (round(t, 2), round(h, 2), round(battery, 1))
                            bucket.append(r)
                            raw.append({"device_id": device.device_id, "temperature": r[0], "humidity": r[1],
                                        "battery": r[2], "timestamp": ts})
                        hourly.append({"device_id": device.device_id, "hour": hour, **_summarise(bucket)})
                        if i in incidents:
                            kind, sev = incidents[i]
                            alerts.append({"device_id": device.device_id, "hour": hour, "alert_type": kind,
                                           "severity": sev, "count": rng.randint(1, 4)})
                        is_farm = device.device_id == "IOT-003"
                        if is_farm and (hour.hour >= 22 or hour.hour < 6) and rng.random() < 0.03:
                            alerts.append({"device_id": device.device_id, "hour": hour, "alert_type": "movement_detected",
                                           "severity": "high", "count": 1})
                        if len(raw) >= 20000:
                            db.execute(insert(TelemetryArchive), raw)
                            self.state["rows"] += len(raw)
                            raw = []
                            db.commit()
                        self.state["progress"] = round(step / total, 3)
                        self.state["message"] = f"{device.device_id}: {hour:%Y-%m-%d}"
                    if raw:
                        db.execute(insert(TelemetryArchive), raw)
                        self.state["rows"] += len(raw)
                    if hourly:
                        db.execute(insert(TelemetryHourly), hourly)
                    if alerts:
                        db.execute(insert(AlertHourly), alerts)
                    db.commit()
            self.state.update(running=False, progress=1.0, seconds=round(time.time() - started, 1),
                              message=f"done: {self.state['rows']:,} readings for {len(devices)} devices, {days} days")
        except Exception as exc:  # report it in the dashboard instead of crashing the server
            self.state.update(running=False, message=f"failed: {exc}")
        return self.state


history_job = HistoryJob()


def clear_history(db: Session) -> dict:
    n = {"archive": db.query(TelemetryArchive).delete(), "hourly": db.query(TelemetryHourly).delete(),
         "alerts": db.query(AlertHourly).delete()}
    db.commit()
    return n


# ================================================================ analytics
def _since(days: int) -> datetime:
    return floor_hour(utcnow()) - timedelta(days=max(1, min(MAX_DAYS, days)))


def _visible(q, column, hidden):
    return q.filter(column.notin_(hidden)) if hidden else q


def database_size(db: Session) -> int | None:
    url = config.DATABASE_URL
    try:
        if url.startswith("sqlite"):
            from pathlib import Path
            path = Path(url.split("///", 1)[1])
            return path.stat().st_size if path.exists() else None
        if url.startswith("postgres"):
            return int(db.execute(func.pg_database_size(func.current_database()).select()).scalar())
    except Exception:
        return None
    return None


def summary(db: Session, hidden: frozenset) -> dict:
    live = _visible(db.query(func.count(Telemetry.id)), Telemetry.device_id, hidden).scalar()
    archive = _visible(db.query(func.count(TelemetryArchive.id)), TelemetryArchive.device_id, hidden).scalar()
    hourly_q = _visible(db.query(TelemetryHourly), TelemetryHourly.device_id, hidden)
    first, last, rows, readings = hourly_q.with_entities(func.min(TelemetryHourly.hour), func.max(TelemetryHourly.hour),
                                                         func.count(TelemetryHourly.id),
                                                         func.coalesce(func.sum(TelemetryHourly.readings), 0)).one()
    alerts = _visible(db.query(func.coalesce(func.sum(AlertHourly.count), 0)), AlertHourly.device_id, hidden).scalar()
    per_device = []
    for device_id, n, avg_t, mn, mx in (hourly_q.with_entities(
            TelemetryHourly.device_id, func.sum(TelemetryHourly.readings), func.avg(TelemetryHourly.temp_avg),
            func.min(TelemetryHourly.temp_min), func.max(TelemetryHourly.temp_max))
            .group_by(TelemetryHourly.device_id).order_by(TelemetryHourly.device_id)):
        per_device.append({"device_id": device_id, "readings": int(n or 0), "temp_avg": round(avg_t, 1),
                           "temp_min": round(mn, 1), "temp_max": round(mx, 1)})
    return {
        "raw_readings": {"live": live, "archive": archive, "total": live + archive},
        "hourly_rows": rows, "readings_summarised": int(readings), "alerts_total": int(alerts),
        "first_hour": first.isoformat() + "Z" if first else None, "last_hour": last.isoformat() + "Z" if last else None,
        "days_covered": round((last - first).total_seconds() / 86400, 1) if first and last else 0,
        "database_bytes": database_size(db) if not hidden else None,
        "database": "PostgreSQL" if config.DATABASE_URL.startswith("postgres") else "SQLite",
        "devices": per_device, "job": history_job.state,
    }


def trends(db: Session, hidden: frozenset, days: int = 30, bucket: str = "day", device_id: str | None = None) -> dict:
    since = _since(days)
    if bucket != "hour":
        since = since.replace(hour=0)  # whole days only
    q = _visible(db.query(TelemetryHourly).filter(TelemetryHourly.hour >= since), TelemetryHourly.device_id, hidden)
    if device_id:
        q = q.filter(TelemetryHourly.device_id == device_id)
    groups = defaultdict(list)
    for r in q.order_by(TelemetryHourly.hour):
        key = r.hour if bucket == "hour" else r.hour.replace(hour=0)
        groups[(r.device_id, key)].append(r)
    series = defaultdict(list)
    for (dev, key), rows in sorted(groups.items(), key=lambda kv: kv[0][1]):
        if bucket != "hour" and len(rows) < 20:
            continue  # a day with only a few hours (e.g. today so far) would bend the daily line
        n = sum(r.readings for r in rows) or 1
        series[dev].append({
            "t": key.isoformat() + "Z", "readings": n,
            "temp_avg": round(sum(r.temp_avg * r.readings for r in rows) / n, 2),
            "temp_min": round(min(r.temp_min for r in rows), 2), "temp_max": round(max(r.temp_max for r in rows), 2),
            "hum_avg": round(sum(r.hum_avg * r.readings for r in rows) / n, 2),
            "battery_avg": round(sum(r.battery_avg * r.readings for r in rows) / n, 1)})
    return {"days": days, "bucket": bucket, "series": dict(series)}


def alert_stats(db: Session, hidden: frozenset, days: int = 30) -> dict:
    q = _visible(db.query(AlertHourly).filter(AlertHourly.hour >= _since(days)), AlertHourly.device_id, hidden)
    per_day = defaultdict(lambda: {"low": 0, "medium": 0, "high": 0, "critical": 0})
    by_type, by_device = Counter(), Counter()
    heatmap = [[0] * 24 for _ in range(7)]  # [weekday 0=Mon][hour] (UTC)
    for r in q:
        per_day[r.hour.date().isoformat()][r.severity] = per_day[r.hour.date().isoformat()].get(r.severity, 0) + r.count
        by_type[r.alert_type] += r.count
        by_device[r.device_id] += r.count
        heatmap[r.hour.weekday()][r.hour.hour] += r.count
    peak = max(((d, h) for d in range(7) for h in range(24)), key=lambda dh: heatmap[dh[0]][dh[1]], default=None)
    return {
        "days": days,
        "per_day": [{"day": d, **v} for d, v in sorted(per_day.items())],
        "by_type": [{"alert_type": t, "count": c} for t, c in by_type.most_common()],
        "by_device": [{"device_id": d, "count": c} for d, c in by_device.most_common()],
        "heatmap": heatmap,
        "peak": ({"weekday": peak[0], "hour": peak[1], "count": heatmap[peak[0]][peak[1]]}
                 if peak and heatmap[peak[0]][peak[1]] else None),
        "total": sum(by_type.values()),
    }


def forecast(db: Session, device_id: str, hours: int = 24) -> dict:
    """Next hours of temperature and humidity from the hourly history: the average
    day-shape of the last 7 days + the trend of the last 14 days, with a 95 % band."""
    hours = max(1, min(72, hours))
    rows = (db.query(TelemetryHourly).filter(TelemetryHourly.device_id == device_id,
                                             TelemetryHourly.hour >= _since(14))
            .order_by(TelemetryHourly.hour).all())
    if len(rows) < 48:
        return {"device_id": device_id, "enough_data": False, "points": [],
                "message": "Needs at least 2 days of hourly data. Generate history in Analytics or let the simulation run."}
    last_time = rows[-1].hour
    recent = [r for r in rows if r.hour > last_time - timedelta(days=7)]

    def profile(attr):
        by_hour = defaultdict(list)
        for r in recent:
            by_hour[r.hour.hour].append(getattr(r, attr))
        overall = statistics.fmean(getattr(r, attr) for r in recent)
        return {h: statistics.fmean(by_hour[h]) if by_hour[h] else overall for h in range(24)}

    def daily_slope(attr):
        days = defaultdict(list)
        for r in rows:
            days[r.hour.date()].append(getattr(r, attr))
        pts = [(i, statistics.fmean(v)) for i, (_, v) in enumerate(sorted(days.items()))]
        if len(pts) < 3:
            return 0.0
        mx, my = statistics.fmean(p[0] for p in pts), statistics.fmean(p[1] for p in pts)
        den = sum((x - mx) ** 2 for x, _ in pts) or 1
        return sum((x - mx) * (y - my) for x, y in pts) / den  # change per day

    result = {}
    for attr in ("temp_avg", "hum_avg"):
        prof, slope = profile(attr), daily_slope(attr)
        resid = [getattr(r, attr) - prof[r.hour.hour] for r in recent]
        sigma = statistics.pstdev(resid) if len(resid) > 1 else 0.5
        result[attr] = (prof, slope, sigma)
    device = db.get(Device, device_id)
    points, warnings = [], []
    for k in range(1, hours + 1):
        t = last_time + timedelta(hours=k)
        p = {"t": t.isoformat() + "Z"}
        for attr, key in (("temp_avg", "temp"), ("hum_avg", "hum")):
            prof, slope, sigma = result[attr]
            value = prof[t.hour] + slope * (3.5 + k / 24)  # 3.5 days = middle of the 7-day profile
            p[key] = round(value, 2)
            p[f"{key}_low"] = round(value - 1.96 * sigma, 2)
            p[f"{key}_high"] = round(value + 1.96 * sigma, 2)
        if device and (p["temp"] > device.temp_max or p["temp"] < device.temp_min):
            warnings.append(f"{t:%a %H:00} UTC: {p['temp']} °C is outside the allowed {device.temp_min}–{device.temp_max} °C")
        points.append(p)
    history = [{"t": r.hour.isoformat() + "Z", "temp": round(r.temp_avg, 2), "hum": round(r.hum_avg, 2)}
               for r in rows if r.hour > last_time - timedelta(hours=48)]
    return {"device_id": device_id, "enough_data": True, "history": history, "points": points,
            "trend_per_day": {"temp": round(result["temp_avg"][1], 3), "hum": round(result["hum_avg"][1], 3)},
            "method": "average day-shape of the last 7 days + linear trend of the last 14 days, 95 % band",
            "warnings": warnings[:5]}
