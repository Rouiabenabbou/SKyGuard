"""
v2.1 (SOC stage 2): GNSS integrity of the satellite-connected devices.

Satellite terminals need GNSS (GPS / Galileo) for their position and their
clock. Two attacks matter:
  jamming    noise drowns the signal: C/N0 falls below ~25 dB-Hz, satellites
             in view drop to 0-2 and the receiver loses its fix
  spoofing   a fake, strong signal: the reported position or clock drifts away
             from the truth while C/N0 looks unnaturally high and uniform

The values here are SIMULATED (the project has no GNSS receiver). The normal
state is generated around the device's registered coordinates; the
gnss-jamming and gnss-spoofing scenarios override it for a short time and
store every sample as a security event, where rules CS-019 / CS-020 look at it.
"""
import math
import random
import time

from sqlalchemy.orm import Session

from app.models import Device, DeviceProfile

_override: dict[str, dict] = {}  # device_id -> {"until": t, "state": "jammed"|"spoofed", "sample": {...}}


def set_override(device_id: str, state: str, sample: dict, seconds: float = 90) -> None:
    _override[device_id] = {"until": time.time() + seconds, "state": state, "sample": sample}


def clear() -> None:
    _override.clear()


def normal_sample(device_id: str) -> dict:
    rnd = random.Random(f"{device_id}-{int(time.time() // 10)}")
    return {"cn0": round(rnd.uniform(38, 47), 1), "satellites": rnd.randint(9, 14), "hdop": round(rnd.uniform(0.7, 1.3), 2),
            "fix": True, "offset_km": round(rnd.uniform(0.0, 0.01), 3), "clock_offset_us": round(rnd.uniform(-0.05, 0.05), 3),
            "implied_speed_mps": 0.0}


def distance_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def status(db: Session, hidden=frozenset()) -> list[dict]:
    now = time.time()
    out = []
    for d in db.query(Device).filter(Device.connection_type == "satellite").order_by(Device.device_id):
        if d.device_id in hidden:
            continue
        p = db.get(DeviceProfile, d.device_id)
        o = _override.get(d.device_id)
        if o and o["until"] > now:
            sample, state = o["sample"], o["state"]
        else:
            sample, state = normal_sample(d.device_id), "normal"
        out.append({"device_id": d.device_id, "device_name": d.device_name, "state": state, **sample,
                    "lat": p.latitude if p else None, "lon": p.longitude if p else None, "source": "simulation"})
    return out
