"""
The backend's connection to the MQTT broker (Mosquitto).

How it works:
1. At startup we connect to the broker in the background. If the broker is
   not running, paho keeps retrying every few seconds, and the rest of the
   app works normally meanwhile.
2. We subscribe to every device's telemetry and status topics.
3. paho calls on_message() from its own thread. We hand each message over to
   FastAPI's event loop, where handle_message() validates it and stores it
   through the same ingest_telemetry() used in Phase 2.
"""
import asyncio
import json
import time

import paho.mqtt.client as mqtt

from app import config, mqtt_topics
from app.database import SessionLocal
from app.detection_engine import detector
from app.event_log import log_event
from app.models import Device
from app.telemetry_service import ingest_telemetry
import os as _os
_PROC_LOG = open(_os.environ['PROC_LOG'], 'a', buffering=1) if _os.getenv('PROC_LOG') else None
from app.websocket_manager import manager


class MQTTService:
    def __init__(self) -> None:
        self.client: mqtt.Client | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.connected = False
        self.messages_received = 0
        self.messages_rejected = 0
        self.last_message_at: float | None = None
        self.session_id_provider = lambda: None  # set by main.py

    # ------------------------------------------------------------- status
    def status(self) -> dict:
        return {
            "enabled": config.MQTT_ENABLED,
            "connected": self.connected,
            "broker": f"{config.MQTT_HOST}:{config.MQTT_PORT}",
            "mode": config.MQTT_MODE,  # v2.4: local Mosquitto or a cloud broker
            "subscriptions": [mqtt_topics.TELEMETRY_SUB, mqtt_topics.STATUS_SUB],
            "authenticated": bool(config.MQTT_USERNAME),  # v1.1: secure MQTT
            "tls": config.MQTT_TLS,
            "messages_received": self.messages_received,
            "messages_rejected": self.messages_rejected,
            "seconds_since_last_message": (
                round(time.time() - self.last_message_at, 1) if self.last_message_at else None
            ),
        }

    def _push_status(self) -> None:
        if self.loop:
            asyncio.run_coroutine_threadsafe(manager.broadcast("mqtt", self.status()), self.loop)

    # -------------------------------------------------------- lifecycle
    def start(self) -> None:
        if not config.MQTT_ENABLED:
            print("[mqtt] disabled in config")
            return
        self.loop = asyncio.get_running_loop()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=config.MQTT_CLIENT_ID or f"cybershield-backend-{int(time.time())}"
        )
        if config.MQTT_USERNAME:
            self.client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
        if config.MQTT_TLS:  # v1.1: encrypted connection, broker checked against our own CA
            # v2.4: no MQTT_CA_CERT = system CA store (cloud brokers use public certificates)
            import ssl
            self.client.tls_set(ca_certs=config.MQTT_CA_CERT, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        # connect_async + loop_start = connect in the background and retry forever.
        self.client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
        self.client.loop_start()
        print(f"[mqtt] connecting to {config.MQTT_HOST}:{config.MQTT_PORT} ({config.MQTT_MODE}) ...")

    def stop(self) -> None:
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

    # --------------------------------------------- paho callbacks (thread)
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[mqtt] connection refused: {reason_code}")
            return
        self.connected = True
        client.subscribe([(mqtt_topics.TELEMETRY_SUB, 0), (mqtt_topics.STATUS_SUB, 0)])
        print(f"[mqtt] connected, subscribed to {mqtt_topics.TELEMETRY_SUB} and {mqtt_topics.STATUS_SUB}")
        self._push_status()
        self._schedule(self._log_connection("mqtt_connected", f"Connected to MQTT broker {config.MQTT_HOST}:{config.MQTT_PORT}"))

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        was_connected = self.connected
        self.connected = False
        if was_connected:
            print(f"[mqtt] disconnected ({reason_code}), retrying ...")
            self._push_status()
            self._schedule(self._log_connection("mqtt_disconnected", "Lost connection to MQTT broker, retrying"))

    def _on_message(self, client, userdata, msg):
        self._schedule(self.handle_message(msg.topic, msg.payload, time.time()))

    def _schedule(self, coroutine) -> None:
        if self.loop:
            asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    # ------------------------------------------ message handling (async)
    async def _log_connection(self, event_type: str, description: str) -> None:
        with SessionLocal() as db:
            await log_event(db, event_type, description, category="system",
                            session_id=self.session_id_provider())

    async def handle_message(self, topic: str, raw: bytes, t_rx: float | None = None) -> None:
        t_start = time.time()
        parsed = mqtt_topics.parse_device_topic(topic)
        if parsed is None:
            return
        topic_device_id, kind = parsed
        self.messages_received += 1
        self.last_message_at = time.time()
        session_id = self.session_id_provider()

        with SessionLocal() as db:
            if kind == "status":
                await self._handle_status(db, topic_device_id, raw.decode(errors="replace").strip(), session_id)
                return
            if kind != "telemetry":
                return

            # 1. Is it valid JSON?
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("payload is not a JSON object")
            except ValueError as exc:
                self.messages_rejected += 1
                await detector.check_message_rate(db, topic_device_id)
                await detector.malformed_message(db, topic_device_id, f"invalid JSON on {topic} ({exc})")
                return

            # 2. Does the device ID in the message match the topic?
            payload.setdefault("device_id", topic_device_id)
            if payload["device_id"] != topic_device_id:
                self.messages_rejected += 1
                await detector.device_id_spoofing(db, topic_device_id, str(payload["device_id"]))
                return

            # 3. Validate, store and broadcast (same path as Phase 2).
            transport_source = f"{payload.get('source', 'device')}/mqtt"
            result = await ingest_telemetry(db, {**payload, "source": transport_source}, session_id=session_id)
            if _PROC_LOG and payload.get("seq") is not None:  # v2.8 measurement: queueing + processing time
                _PROC_LOG.write(f"{payload['device_id']},{payload['seq']},{t_rx or t_start:.6f},{t_start:.6f},{time.time():.6f}\n")
            if not result["ok"]:
                self.messages_rejected += 1
                if result["error"] == "quarantined":
                    self.messages_rejected -= 1  # blocked on purpose, counted by the quarantine service
                elif result["error"] == "invalid_message":
                    fields = ", ".join(str(e.get("loc", ["?"])[0]) for e in result.get("detail", []))
                    await detector.malformed_message(db, topic_device_id, f"invalid telemetry fields: {fields}")
                # unknown_device: the detection engine already raised an alert

    async def _handle_status(self, db, device_id: str, status: str, session_id) -> None:
        if status == "online":
            await detector.connection_attempt(db, device_id)  # Rule D
        device = db.get(Device, device_id)
        if device is None or status not in ("online", "offline"):
            return
        if status == "offline" and device.status != "offline":
            device.status = "offline"
            db.commit()
            await log_event(db, "device_offline", f"{device.device_name} ({device_id}) reported offline via MQTT",
                            category="device", device_id=device_id, session_id=session_id)
            await manager.broadcast("device", device.to_dict())

    # --------------------------------------------------------- publishing
    def publish(self, topic: str, payload, retain: bool = False) -> bool:
        """Publish a dict (sent as JSON) or a string. Returns False if not connected."""
        if not (self.client and self.connected):
            return False
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return self.client.publish(topic, data, qos=0, retain=retain).rc == mqtt.MQTT_ERR_SUCCESS


mqtt_service = MQTTService()
