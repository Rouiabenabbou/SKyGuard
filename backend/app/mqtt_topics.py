"""
MQTT topic names, in one place so the backend, the simulator and the ESP32
all agree.

    cybershield/iot/<device_id>/telemetry   device -> backend   sensor readings (JSON)
    cybershield/iot/<device_id>/status      device -> backend   "online" / "offline"
    cybershield/iot/<device_id>/command     backend -> device   {"action": "quarantine" | "release"}
    cybershield/security/alerts             backend -> anyone   security alerts (Phase 5)
    cybershield/network/events              backend -> anyone   everything in the event log

The "+" in a subscription is a wildcard for exactly one level (any device ID).
"""
from app.config import MQTT_TOPIC_PREFIX as P

TELEMETRY_SUB = f"{P}/iot/+/telemetry"
STATUS_SUB = f"{P}/iot/+/status"
SECURITY_ALERTS = f"{P}/security/alerts"
NETWORK_EVENTS = f"{P}/network/events"


def telemetry_topic(device_id: str) -> str:
    return f"{P}/iot/{device_id}/telemetry"


def status_topic(device_id: str) -> str:
    return f"{P}/iot/{device_id}/status"


def parse_device_topic(topic: str) -> tuple[str, str] | None:
    """'cybershield/iot/IOT-001/telemetry' -> ('IOT-001', 'telemetry'). None if not a device topic."""
    parts = topic.split("/")
    if len(parts) == 4 and parts[0] == P and parts[1] == "iot":
        return parts[2], parts[3]
    return None


def command_topic(device_id: str) -> str:
    return f"{P}/iot/{device_id}/command"
