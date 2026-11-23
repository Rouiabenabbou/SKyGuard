"""
Rule-based cybersecurity detection engine.

Every rule is simple and explainable, which makes it a good fit for a demo
and for a report:

  Rule A  excessive_message_rate   a device sends more than RATE_THRESHOLD_PER_SEC
                                   messages per second (measured over RATE_WINDOW_SECONDS)
  Rule B  unauthorized_device      a message arrives from a device ID that is not registered
  Rule C  abnormal_sensor_value    a reading is outside the device's allowed range
  Rule D  suspicious_connections   a device connects more than CONN_THRESHOLD times
                                   within CONN_WINDOW_SECONDS
  Rule E  link_failure / node_failure   a network link or node goes offline
  Extra   device_id_spoofing       the device ID in the message differs from the MQTT topic
  Extra   malformed_message        the message is not valid JSON / not valid telemetry

For each alert we store: id, device, type, severity, description, time,
detection method ("rule") and status ("open" / "resolved").

The same (device, type) pair is not alerted again within ALERT_COOLDOWN_SECONDS,
so one attack produces one clear alert instead of hundreds.

All "attacks" are simulated inside this project only.
"""
import time
from collections import defaultdict, deque

from sqlalchemy.orm import Session

from app import config, mqtt_topics
from app.event_log import log_event
from app.models import Device, SecurityAlert
from app.websocket_manager import manager
import os
from app.link_probe import probe as link_probe

# v2.8 (experimental): "unaware" = v2.6 behaviour; "aware" = rules conditioned on the
# independently measured link state (see link_probe.py)
DETECTION_MODE = os.getenv("DETECTION_MODE", "unaware")
BACKLOG_MARGIN_S = 2.0       # a send time up to 2 s before the measured outage start counts as inside it
BACKLOG_FACTOR = 1.5         # budget = 1.5 x outage length x the device's usual send rate + 5
RECONNECT_GRACE_S = 10.0
# v1 (first version) also excused messages that arrive *while* the outage is still in progress;
# X1 run 1 showed this lets floods during an outage through, so v2 excuses a message only
# once the measured outage has ended (true backlog can only arrive after recovery).
AWARE_VARIANT = os.getenv("AWARE_VARIANT", "v2")     # reconnects within 10 s after a measured link recovery are link-caused

SEVERITIES = ["low", "medium", "high", "critical"]


class DetectionEngine:
    def __init__(self) -> None:
        self.message_times: dict[str, deque] = defaultdict(deque)
        self.connection_times: dict[str, deque] = defaultdict(deque)
        self.last_alert: dict[tuple[str, str], float] = {}
        self.session_id_provider = lambda: None  # set by main.py
        self.last_send: dict[str, float] = {}           # device -> last ts_sent (s) of a normal message
        self.send_rate: dict[str, float] = {}           # device -> EWMA of messages per second (send clock)
        self.backlog_used: dict[tuple, int] = {}        # (device, outage start) -> backlog messages excused
        self.backlog_excused = 0
        self.reconnects_excused = 0
        if DETECTION_MODE == "aware":
            link_probe.start()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _count_recent(times: deque, now: float, window: float) -> int:
        times.append(now)
        while times and times[0] < now - window:
            times.popleft()
        return len(times)

    async def raise_alert(self, db: Session, alert_type: str, severity: str, description: str,
                          device_id: str | None = None, subject: str | None = None,
                          detection_method: str = "rule", mark_suspicious: bool = True) -> SecurityAlert | None:
        """Store and broadcast an alert. `subject` (default: the device) is what the
        cooldown is tracked for, e.g. a link ID for link failures."""
        from app import soc
        if not soc.rule_enabled(alert_type):
            return None  # v2.0: rule switched off by an admin
        key = (subject or device_id or "-", alert_type)
        now = time.time()
        if now - self.last_alert.get(key, 0) < config.ALERT_COOLDOWN_SECONDS:
            return None  # same alert very recently: don't spam
        self.last_alert[key] = now

        alert = SecurityAlert(device_id=device_id, alert_type=alert_type, severity=severity,
                              description=description, detection_method=detection_method, status="open")
        db.add(alert)
        db.commit()

        # A registered device involved in a serious alert becomes "suspicious".
        # (Not for physical events such as movement: the device itself is fine.)
        if device_id and mark_suspicious and severity in ("high", "critical"):
            device = db.get(Device, device_id)
            if device and device.security_status == "normal":
                device.security_status = "suspicious"
                db.commit()
                await manager.broadcast("device", device.to_dict())

        await manager.broadcast("alert", alert.to_dict())
        await log_event(db, f"alert_{alert_type}", f"[{severity.upper()}] {description}",
                        category="security", device_id=device_id, session_id=self.session_id_provider())

        from app.mqtt_client import mqtt_service  # avoid a circular import
        from app.quarantine_service import quarantine

        mqtt_service.publish(mqtt_topics.SECURITY_ALERTS, alert.to_dict())
        try:  # v1.2: phone alarm (in the background; never blocks detection)
            from app.notifier import notifier
            notifier.alert(db, alert)
        except Exception as exc:
            print(f"[notify] skipped: {exc}")
        await quarantine.maybe_auto_quarantine(db, alert)  # Phase 6
        return alert

    # -------------------------------------------------------------- rules
    def _is_backlog(self, device_id: str, ts_sent) -> bool:
        """v2.8 aware mode: a late message whose send time lies inside a measured outage of
        the device's link is backlog, up to a budget derived from the outage length and
        the device's usual rate (so a forged-timestamp flood still exceeds it)."""
        try:
            t = float(ts_sent) / 1000.0
        except (TypeError, ValueError):
            return False
        iv = link_probe.outage_at(device_id, t, BACKLOG_MARGIN_S)
        if iv is None:
            if device_id in self.last_send and t > self.last_send[device_id]:
                gap = t - self.last_send[device_id]
                if 0.05 < gap < 60:
                    r = 1.0 / gap
                    self.send_rate[device_id] = r if device_id not in self.send_rate else 0.9 * self.send_rate[device_id] + 0.1 * r
            self.last_send[device_id] = max(t, self.last_send.get(device_id, 0))
            return False
        if AWARE_VARIANT == "v2" and (iv[1] is None or time.time() < iv[1]):
            return False
        end = iv[1] if iv[1] is not None else time.time()
        budget = int(BACKLOG_FACTOR * (end - iv[0] + BACKLOG_MARGIN_S) * self.send_rate.get(device_id, 1.0)) + 5
        key = (device_id, iv[0])
        if self.backlog_used.get(key, 0) >= budget:
            return False
        self.backlog_used[key] = self.backlog_used.get(key, 0) + 1
        self.backlog_excused += 1
        return True

    async def check_message_rate(self, db: Session, device_id: str, ts_sent=None) -> None:
        """Rule A. Called for EVERY incoming telemetry message, valid or not."""
        if DETECTION_MODE == "aware" and self._is_backlog(device_id, ts_sent):
            return  # delivered late because of a measured outage: not part of the device's current rate
        now = time.time()
        count = self._count_recent(self.message_times[device_id], now, config.RATE_WINDOW_SECONDS)
        rate = count / config.RATE_WINDOW_SECONDS
        if rate > config.RATE_THRESHOLD_PER_SEC:
            await self.raise_alert(
                db, "excessive_message_rate", "high",
                f"{device_id} is sending {rate:.1f} messages/s (limit {config.RATE_THRESHOLD_PER_SEC:g}/s). "
                "Possible flooding / DoS attempt.",
                device_id,
            )

    async def unauthorized_device(self, db: Session, device_id: str) -> None:
        """Rule B."""
        await self.raise_alert(
            db, "unauthorized_device", "high",
            f"Unauthorized IoT device detected: '{device_id}' is not in the device registry.",
            device_id,
        )

    async def check_sensor_ranges(self, db: Session, device: Device, temperature: float, humidity: float) -> None:
        """Rule C."""
        problems = []
        worst_distance = 0.0
        for name, value, low, high, unit in (
            ("temperature", temperature, device.temp_min, device.temp_max, "C"),
            ("humidity", humidity, device.humidity_min, device.humidity_max, "%"),
        ):
            if value < low or value > high:
                problems.append(f"{name} {value:g}{unit} (allowed {low:g}-{high:g}{unit})")
                worst_distance = max(worst_distance, low - value, value - high)
        if problems:
            severity = "high" if worst_distance >= config.ABNORMAL_MARGIN else "medium"
            await self.raise_alert(
                db, "abnormal_sensor_value", severity,
                f"{device.device_name} reported abnormal values: {', '.join(problems)}. "
                "Possible sensor tampering, malfunction or physical incident.",
                device.device_id,
            )

    async def connection_attempt(self, db: Session, device_id: str) -> None:
        """Rule D. Called each time a device announces it came online."""
        now = time.time()
        if DETECTION_MODE == "aware" and link_probe.recovered_within(device_id, now, RECONNECT_GRACE_S):
            self.reconnects_excused += 1
            return  # reconnect right after a measured link recovery: caused by the link
        count = self._count_recent(self.connection_times[device_id], now, config.CONN_WINDOW_SECONDS)
        if count > config.CONN_THRESHOLD:
            await self.raise_alert(
                db, "suspicious_connections", "high",
                f"{device_id} connected {count} times in {config.CONN_WINDOW_SECONDS:g} s "
                f"(limit {config.CONN_THRESHOLD}). Possible credential guessing or unstable/compromised device.",
                device_id,
            )

    async def link_failure(self, db: Session, link_id: str, source: str, target: str) -> None:
        """Rule E (links)."""
        severity = "critical" if "SAT" in link_id or "CORE" in link_id else "high"
        await self.raise_alert(db, "link_failure", severity,
                               f"Network link {link_id} ({source} -> {target}) is offline.", subject=link_id)

    async def node_failure(self, db: Session, node_id: str, name: str) -> None:
        """Rule E (nodes)."""
        await self.raise_alert(db, "node_failure", "critical", f"{name} ({node_id}) is offline.", subject=node_id)

    async def device_id_spoofing(self, db: Session, topic_id: str, claimed_id: str) -> None:
        await self.raise_alert(
            db, "device_id_spoofing", "high",
            f"Message on {topic_id}'s topic claims to be {claimed_id}. Possible identity spoofing.",
            topic_id,
        )

    async def malformed_message(self, db: Session, device_id: str, detail: str) -> None:
        await self.raise_alert(db, "malformed_message", "low", f"Malformed message from {device_id}: {detail}", device_id)

    # -------------------------------------------------------------- reset
    def forget_device(self, device_id: str) -> None:
        """Clear history for one device (used when it is released from quarantine)."""
        self.message_times.pop(device_id, None)
        self.connection_times.pop(device_id, None)
        for key in [k for k in self.last_alert if k[0] == device_id]:
            del self.last_alert[key]

    def reset(self) -> None:
        self.message_times.clear()
        self.connection_times.clear()
        self.last_alert.clear()


detector = DetectionEngine()
