"""
v2.2: Huawei Cloud IoTDA (IoT Device Access) bridge.

Real devices (the ESP32 board) can connect to Huawei IoTDA instead of the
local Mosquitto broker. IoTDA then forwards every property report to this
app with a "data forwarding" rule of type HTTP push:

    IoTDA console -> Rules -> Data Forwarding -> data source "Device property",
    trigger "Device property reported" -> forwarding target "HTTP(S) push"
    URL  https://<your server>/api/iotda/push?token=<IOTDA_PUSH_TOKEN>

Each push is turned into a normal reading and goes through the same
ingest_telemetry() path as MQTT (validation, registry check, quarantine,
detection, ML, dashboard). Readings are stored with source "iotda/https" and are
labelled LAB (real hardware), never SIM.

Push body (IoTDA format):
  {"resource": "device.property", "event": "report", "event_time": "20261104T101010Z",
   "notify_data": {"header": {"device_id": "<product>_ESP32-001", "node_id": "ESP32-001", ...},
                   "body": {"services": [{"service_id": "Sensor",
                                          "properties": {"temperature": 24.1, "humidity": 51, "battery": 100},
                                          "event_time": "20261104T101010Z"}]}}}

The device ID in this app is the IoTDA "node ID" (the identifier you type
when registering the device), so register the board in IoTDA with node ID
ESP32-001.
"""
import time

from app import config

stats = {"received": 0, "accepted": 0, "rejected": 0, "last_at": None, "last_error": None, "last_device": None}


def enabled() -> bool:
    return bool(config.IOTDA_PUSH_TOKEN)


def our_device_id(header: dict) -> str | None:
    node = header.get("node_id")
    if node:
        return str(node)
    dev = header.get("device_id") or ""
    return dev.split("_", 1)[1] if "_" in dev else (dev or None)


def readings_from_push(body: dict) -> list[dict]:
    """IoTDA push -> list of payloads for ingest_telemetry (one per service with sensor values)."""
    if not isinstance(body, dict) or body.get("resource") not in (None, "device.property"):
        return []
    data = body.get("notify_data") or {}
    device_id = our_device_id(data.get("header") or {})
    if not device_id:
        return []
    out = []
    for svc in (data.get("body") or {}).get("services") or []:
        p = svc.get("properties") or {}
        if "temperature" not in p or "humidity" not in p:
            continue
        item = {"device_id": device_id, "temperature": p["temperature"], "humidity": p["humidity"],
                "battery": p.get("battery", 100), "source": "iotda/https"}
        if "motion" in p:
            item["motion"] = bool(p["motion"])
        out.append(item)
    return out


def note(result: dict, device_id: str | None) -> None:
    stats["accepted" if result.get("ok") else "rejected"] += 1
    stats["last_at"] = time.time()
    stats["last_device"] = device_id
    if not result.get("ok"):
        stats["last_error"] = result.get("error")


def status() -> dict:
    return {"enabled": enabled(), "region": config.IOTDA_REGION or None, **stats,
            "push_path": "/api/iotda/push?token=<IOTDA_PUSH_TOKEN>"}
