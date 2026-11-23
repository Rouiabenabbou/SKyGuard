"""
v2.1 (SOC stage 2): the security event store and the network detection rules.

A security event is one line of what a broker log, a firewall, a 5G core or a
GNSS receiver would record: who connected from which address to which port,
which MQTT client published on which topic, a failed login, a 5G
authentication failure, a GNSS sample, a configuration change.

Where the events come from in this project:
  * every minute, one MQTT flow record per active device (from the real
    telemetry the backend received: message count and bytes)
  * the simulated attack scenarios in attack_scenarios.py
Every event carries its source: "simulation" or "lab" (a real test board).
"production" is never written: there is no authorised real infrastructure.

Addresses are SIMULATED: devices get a private 10.20.x.y address derived
from their ID, the broker is 10.0.0.10, the 5G core (AMF) 10.0.5.1, and
attackers use the documentation ranges 203.0.113.0/24 and 198.51.100.0/24
(RFC 5737), which never belong to a real host.

Network detection rules (CS-011 ... CS-021, catalogue in soc.py) run on every
event as it is stored, like the telemetry rules in detection_engine.py.
"""
import hashlib
import ipaddress
import json
import statistics
import time
from collections import defaultdict, deque
from datetime import timedelta

from sqlalchemy.orm import Session

from app import config
from app.models import SecurityEvent, utcnow
from app.websocket_manager import manager

BROKER_IP = "10.0.0.10"
BROKER_PORT = 1883
AMF_IP = "10.0.5.1"  # 5G core access and mobility function
BACKEND_CLIENTS = {"cybershield-backend", "cybershield-simulator"}


LAB_SOURCES = ("esp32", "iotda", "lab")


def is_lab(source: str | None) -> bool:
    """Real hardware? Telemetry sources look like "esp32/mqtt", "iotda/https", "builtin/direct"."""
    return (source or "").split("/")[0] in LAB_SOURCES


def device_ip(device_id: str) -> str:
    """Stable simulated private address of a device."""
    h = hashlib.sha1(device_id.encode()).digest()
    return f"10.20.{h[0]}.{max(2, h[1])}"


def attacker_ip(seed: str, net: str = "203.0.113") -> str:
    """A documentation-range address (RFC 5737): never a real host."""
    h = hashlib.sha1(seed.encode()).digest()
    return f"{net}.{10 + h[0] % 240}"


DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]


def is_documentation(ip: str | None) -> bool:
    try:
        a = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    return any(a in n for n in DOC_NETS)


def is_external(ip: str | None) -> bool:
    """Outside our network. The documentation ranges stand for internet hosts in the simulation
    (Python counts them as "private", so they are checked first)."""
    if not ip:
        return False
    if is_documentation(ip):
        return True
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback)


# ------------------------------------------------------------------ store
async def record(db: Session, event_type: str, *, category: str = "network", severity: str = "info",
                 source: str | None = None, device_id: str | None = None, src_ip: str | None = None,
                 src_port: int | None = None, dst_ip: str | None = None, dst_port: int | None = None,
                 protocol: str = "", mqtt_client: str = "", mqtt_topic: str = "", username: str = "",
                 outcome: str = "observed", nbytes: int = 0, message: str = "", details: dict | None = None,
                 detect: bool = True) -> SecurityEvent:
    """Store one security event, push it to the dashboard and run the network rules on it."""
    if source is None:
        from app import soc
        source = soc.source_of(db, device_id, {})
    ev = SecurityEvent(event_type=event_type, category=category, severity=severity, source=source,
                       device_id=device_id, src_ip=src_ip, src_port=src_port, dst_ip=dst_ip, dst_port=dst_port,
                       protocol=protocol, mqtt_client=mqtt_client[:64], mqtt_topic=mqtt_topic[:160],
                       username=username[:64], outcome=outcome, bytes=int(nbytes), message=message,
                       details=json.dumps(details or {}, default=str))
    db.add(ev)
    db.commit()
    if category != "flow":  # flow summaries are many and boring: not pushed live
        await manager.broadcast("security_event", ev.to_dict())
    if detect:
        try:
            await net_detector.process(db, ev)
        except Exception as exc:  # detection must never break ingestion
            print(f"[net-detect] skipped: {exc}")
    return ev


# ------------------------------------------------------- flow summaries
_flows: dict[str, list] = {}  # device_id -> [messages, bytes, source, topic]


def note_message(device_id: str, nbytes: int, source: str, topic: str = "") -> None:
    """Called for every stored reading; summarised into one flow event per device per minute."""
    f = _flows.setdefault(device_id, [0, 0, source, topic])
    f[0] += 1
    f[1] += nbytes
    f[2] = source


async def flush_flows(db: Session) -> int:
    from app import mqtt_topics
    items = list(_flows.items())
    _flows.clear()
    for device_id, (count, nbytes, source, _topic) in items:
        await record(db, "mqtt_publish_summary", category="flow", source="lab" if is_lab(source) else "simulation",
                     device_id=device_id, src_ip=device_ip(device_id), dst_ip=BROKER_IP, dst_port=BROKER_PORT,
                     protocol="mqtt", mqtt_client=device_id, mqtt_topic=mqtt_topics.telemetry_topic(device_id),
                     username=device_id, outcome="success", nbytes=nbytes,
                     message=f"{count} telemetry messages ({nbytes} bytes) in {config.FLOW_SUMMARY_SECONDS:g} s",
                     details={"messages": count, "window_s": config.FLOW_SUMMARY_SECONDS}, detect=False)
    return len(items)


def purge_old(db: Session) -> int:
    cutoff = utcnow() - timedelta(days=config.SECURITY_EVENT_RETENTION_DAYS)
    n = db.query(SecurityEvent).filter(SecurityEvent.timestamp < cutoff).delete()
    db.commit()
    return n


# ------------------------------------------------------- network rules
def _window(times: deque, now: float, window: float) -> int:
    while times and times[0] < now - window:
        times.popleft()
    return len(times)


class NetDetector:
    """In-memory sliding windows, like detection_engine.DetectionEngine."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.auth_fail: dict[str, deque] = defaultdict(deque)  # src_ip -> times
        self.auth_fail_recent: dict[str, float] = {}  # src_ip -> time the threshold was reached
        self.ports: dict[tuple, deque] = defaultdict(deque)  # (src, dst) -> (time, port)
        self.beacons: dict[tuple, deque] = defaultdict(deque)  # (device, dst, port) -> times
        self.outbound: dict[str, deque] = defaultdict(deque)  # device -> (time, bytes)
        self.g5_fail: dict[str, deque] = defaultdict(deque)  # supi -> times
        self.gnss_bad: dict[str, int] = defaultdict(int)  # device -> consecutive jammed samples
        self.gnss_jammed_at: dict[str, float] = {}

    async def _alert(self, db, alert_type, severity, text, device_id=None, subject=None):
        from app.detection_engine import detector
        return await detector.raise_alert(db, alert_type, severity, text, device_id=device_id, subject=subject)

    async def process(self, db: Session, ev: SecurityEvent) -> None:
        now = time.time()
        t = ev.event_type
        # CS-018: any address in the threat-intelligence list
        from app import intel
        for ip, role in ((ev.src_ip, "source"), (ev.dst_ip, "destination")):
            hit = intel.match(ip)
            if hit:
                await self._alert(db, "threat_intel_match", "critical" if hit["confidence"] >= 80 else "high",
                                  f"{ip} ({role} of {t} event #{ev.id}) is a known indicator: {hit['threat']} "
                                  f"(confidence {hit['confidence']}%, {hit['origin']}).",
                                  device_id=ev.device_id, subject=f"ioc-{ip}-{ev.device_id}")
        if t == "mqtt_auth_failure" and ev.src_ip:  # CS-011
            q = self.auth_fail[ev.src_ip]
            q.append(now)
            n = _window(q, now, config.BRUTE_FORCE_WINDOW_SECONDS)
            if n >= config.BRUTE_FORCE_THRESHOLD:
                self.auth_fail_recent[ev.src_ip] = now
                await self._alert(db, "mqtt_bruteforce", "high",
                                  f"{n} failed MQTT logins from {ev.src_ip} in {config.BRUTE_FORCE_WINDOW_SECONDS:g} s "
                                  f"(username '{ev.username}'). Password guessing against the broker.",
                                  device_id=ev.device_id, subject=f"bf-{ev.src_ip}")
        elif t == "mqtt_connect" and ev.outcome == "success" and ev.src_ip:  # CS-021
            started = self.auth_fail_recent.get(ev.src_ip)
            if started and now - started < 300:
                await self._alert(db, "credential_compromise", "critical",
                                  f"{ev.src_ip} logged in to the broker as '{ev.username}' right after a brute-force run. "
                                  "The device credentials are probably compromised.",
                                  device_id=ev.device_id, subject=f"cc-{ev.src_ip}")
        elif t in ("mqtt_publish_denied", "mqtt_subscribe_denied"):  # CS-014
            await self._alert(db, "unauthorized_publish", "high",
                              f"MQTT client '{ev.mqtt_client}' from {ev.src_ip} tried to "
                              f"{'publish to' if t == 'mqtt_publish_denied' else 'subscribe to'} '{ev.mqtt_topic}' "
                              "without permission (broker ACL denied it).",
                              device_id=ev.device_id, subject=f"pub-{ev.mqtt_client}")
        elif t == "net_conn_attempt" and ev.src_ip and ev.dst_port:  # CS-013
            q = self.ports[(ev.src_ip, ev.dst_ip)]
            q.append((now, ev.dst_port))
            while q and q[0][0] < now - config.PORT_SCAN_WINDOW_SECONDS:
                q.popleft()
            ports = {p for _, p in q}
            if len(ports) >= config.PORT_SCAN_THRESHOLD:
                await self._alert(db, "port_scan", "medium",
                                  f"{ev.src_ip} probed {len(ports)} different ports on {ev.dst_ip} in "
                                  f"{config.PORT_SCAN_WINDOW_SECONDS:g} s (network service discovery).",
                                  device_id=ev.device_id, subject=f"scan-{ev.src_ip}-{ev.dst_ip}")
        elif t == "net_connection" and ev.device_id and is_external(ev.dst_ip):  # CS-012 + CS-015
            key = (ev.device_id, ev.dst_ip, ev.dst_port)
            q = self.beacons[key]
            q.append(now)
            _window(q, now, 300)
            if len(q) >= config.BEACON_MIN_CONNECTIONS:
                gaps = [b - a for a, b in zip(list(q), list(q)[1:])]
                mean = statistics.mean(gaps)
                jitter = statistics.pstdev(gaps) / mean if mean > 0 else 1
                if jitter <= config.BEACON_MAX_JITTER:
                    await self._alert(db, "c2_beaconing", "high",
                                      f"{ev.device_id} connects to {ev.dst_ip}:{ev.dst_port} every {mean:.1f} s "
                                      f"({len(q)} times, jitter {jitter:.2f}). Regular call-home = botnet / C2 beaconing.",
                                      device_id=ev.device_id, subject=f"beacon-{ev.device_id}-{ev.dst_ip}")
            await self._outbound(db, ev, now)
        elif t == "outbound_transfer" and ev.device_id and is_external(ev.dst_ip):
            await self._outbound(db, ev, now)
        elif t == "5g_auth_failure" and ev.username:  # CS-016
            q = self.g5_fail[ev.username]
            q.append(now)
            n = _window(q, now, 60)
            if n >= config.G5_AUTH_FAIL_THRESHOLD:
                cell = json.loads(ev.details or "{}").get("cell", "?")
                await self._alert(db, "5g_auth_anomaly", "high",
                                  f"{n} failed 5G authentications for {ev.username} on cell {cell} in 60 s "
                                  "(cloned SIM or authentication attack against the 5G core).",
                                  device_id=ev.device_id, subject=f"5g-{ev.username}")
        elif t == "config_change":  # CS-017
            d = json.loads(ev.details or "{}")
            if not d.get("actor_authenticated", False):
                await self._alert(db, "unauthorized_config_change", "high",
                                  f"Configuration of {ev.device_id} changed by MQTT client '{ev.mqtt_client}' "
                                  f"from {ev.src_ip}, not through the dashboard: {d.get('changed', {})}.",
                                  device_id=ev.device_id, subject=f"cfg-{ev.device_id}")
        elif t == "gnss_sample" and ev.device_id:  # CS-019 / CS-020
            await self._gnss(db, ev, now)

    async def _outbound(self, db, ev, now) -> None:
        q = self.outbound[ev.device_id]
        q.append((now, ev.bytes))
        while q and q[0][0] < now - 60:
            q.popleft()
        total = sum(b for _, b in q)
        if total >= config.EXFIL_BYTES_PER_MINUTE:
            await self._alert(db, "data_exfiltration", "critical",
                              f"{ev.device_id} sent {total / 1048576:.1f} MB to external address {ev.dst_ip} in 60 s "
                              f"(limit {config.EXFIL_BYTES_PER_MINUTE / 1048576:.0f} MB; a sensor normally sends a few KB).",
                              device_id=ev.device_id, subject=f"exfil-{ev.device_id}")

    async def _gnss(self, db, ev, now) -> None:
        d = json.loads(ev.details or "{}")
        cn0, fix = d.get("cn0", 45), d.get("fix", True)
        if cn0 < config.GNSS_MIN_CN0 and not fix:
            self.gnss_bad[ev.device_id] += 1
            if self.gnss_bad[ev.device_id] >= 3:
                self.gnss_jammed_at[ev.device_id] = now
                # other terminals losing the signal at the same time (2+ bad samples in a row)
                together = sorted({ev.device_id} | {dv for dv, n in self.gnss_bad.items() if n >= 2}
                                  | {dv for dv, ts in self.gnss_jammed_at.items() if now - ts < 60})
                await self._alert(db, "gnss_jamming", "critical" if len(together) >= 2 else "high",
                                  f"GNSS signal lost on {ev.device_id}: C/N0 {cn0:.0f} dB-Hz, no position fix for "
                                  f"{self.gnss_bad[ev.device_id]} samples"
                                  + (f"; {len(together)} devices at once ({', '.join(together)})" if len(together) >= 2 else "")
                                  + ". Jamming indicator.", device_id=ev.device_id, subject=f"jam-{ev.device_id}")
        else:
            self.gnss_bad[ev.device_id] = 0
        speed, offset = d.get("implied_speed_mps", 0), d.get("offset_km", 0)
        if fix and (speed > config.GNSS_MAX_SPEED_MPS or offset > 5):
            await self._alert(db, "gnss_spoofing", "high",
                              f"{ev.device_id} reports a position {offset:.1f} km from where it is installed "
                              f"(implied speed {speed:.0f} m/s, C/N0 {cn0:.0f} dB-Hz, clock offset "
                              f"{d.get('clock_offset_us', 0):.0f} µs). A fixed device can't move: spoofing indicator.",
                              device_id=ev.device_id, subject=f"spoof-{ev.device_id}")


net_detector = NetDetector()
