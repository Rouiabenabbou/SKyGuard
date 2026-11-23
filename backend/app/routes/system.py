"""
System endpoints used to check that the backend is alive.

GET /api/health  -> quick "is the server up?" check
GET /api/info    -> project name, version, components planned
GET /api/mqtt/status -> is the backend connected to the MQTT broker?
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app import config
from app.ml_detector import ml_detector
from app.mqtt_client import mqtt_service
from app.websocket_manager import manager

router = APIRouter(prefix="/api", tags=["system"])

STARTED_AT = time.time()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "cybershield-backend",
        "time": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.time() - STARTED_AT, 1),
        "websocket_clients": manager.client_count,
    }


@router.get("/info")
def info():
    return {
        "name": config.APP_NAME,
        "version": config.APP_VERSION,
        "phase": 12,
        "components": [
            {"id": "backend", "name": "FastAPI Backend", "ready": True},
            {"id": "frontend", "name": "React Dashboard", "ready": True},
            {"id": "database", "name": "SQLite Database", "ready": True},
            {"id": "mqtt", "name": "MQTT Broker (Mosquitto)", "ready": True},
            {"id": "simulator", "name": "IoT Device Simulator", "ready": True},
            {"id": "detection", "name": "Cybersecurity Detection", "ready": True},
            {"id": "network", "name": "Satellite-5G Network Simulator", "ready": True},
            {"id": "twin", "name": "3D Digital Twin", "ready": True},
            {"id": "failover", "name": "Satellite-5G Failover", "ready": True},
            {"id": "timeline", "name": "4D Timeline Replay", "ready": True},
            {"id": "dashboard", "name": "Dashboard, charts and reports", "ready": True},
            {"id": "esp32", "name": "ESP32 + DHT22 hardware (optional)", "ready": config.ESP32_ENABLED},
            {"id": "ml", "name": "ML anomaly detector (optional)", "ready": ml_detector.enabled},
        ],
    }


@router.get("/mqtt/status")
def mqtt_status():
    return mqtt_service.status()
