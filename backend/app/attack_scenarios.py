"""
v2.1 (SOC stage 2): more simulated attack scenarios.

Each one writes the security events a broker, firewall, 5G core or GNSS
receiver would log while the attack happens (see security_events.py). The
network rules must then detect it on their own. Nothing is sent to a real
network: attacker addresses are documentation addresses (RFC 5737) and every
event is labelled source "simulation".

  mqtt-brute-force     8 wrong MQTT passwords, then one success      -> CS-011, CS-021
  unauthorized-publish a rogue client publishes to a device command topic -> CS-014
  botnet-beaconing     the device calls home every 1.5 s to a C2 address    -> CS-012, CS-018
  port-scan            24 ports probed on a device in a few seconds         -> CS-013
  data-exfiltration    ~7 MB sent to an external address in 6 s             -> CS-015, CS-018
  5g-auth-attack       6 failed 5G authentications for one SIM              -> CS-016
  config-tampering     device settings changed over MQTT, not via the dashboard -> CS-017
  gnss-jamming         GNSS signal lost on up to 3 satellite devices        -> CS-019
  gnss-spoofing        the reported position walks away from the real one   -> CS-020
"""
import asyncio
import random
import zlib

from app import config, gnss, mqtt_topics
from app.database import SessionLocal
from app.event_log import log_event
from app.models import Device
from app.security_events import AMF_IP, BROKER_IP, BROKER_PORT, attacker_ip, device_ip, record

C2_IP, C2_PORT = "198.51.100.66", 8443
DROP_IP = "198.51.100.23"


async def _start(db, device_id, session_id, text):
    await log_event(db, "attack_started", f"[SIMULATION] {text}", category="security", device_id=device_id,
                    session_id=session_id)


async def mqtt_brute_force(device_id: str, session_id, attempts: int = 8, succeed: bool = True, delay: float = 0.4,
                           src: str | None = None) -> None:
    src = src or attacker_ip(f"bf-{device_id}")
    with SessionLocal() as db:
        await _start(db, device_id, session_id, f"MQTT brute force from {src} against {device_id}'s broker account")
        for i in range(attempts):
            await record(db, "mqtt_auth_failure", category="auth", severity="low", source="simulation", device_id=device_id,
                         src_ip=src, src_port=40000 + i, dst_ip=BROKER_IP, dst_port=BROKER_PORT, protocol="mqtt",
                         mqtt_client=f"mqttx_{random.randint(1000, 9999)}", username=device_id, outcome="failure",
                         message="CONNECT refused: bad user name or password (CONNACK 0x86)",
                         details={"password_tried": f"guess-{i + 1}", "connack": "0x86"})
            await asyncio.sleep(delay)
        if succeed:
            await record(db, "mqtt_connect", category="auth", severity="medium", source="simulation", device_id=device_id,
                         src_ip=src, src_port=40100, dst_ip=BROKER_IP, dst_port=BROKER_PORT, protocol="mqtt",
                         mqtt_client="mqttx_owned", username=device_id, outcome="success",
                         message="CONNECT accepted (CONNACK 0x00) for an account under attack", details={"connack": "0x00"})


async def unauthorized_publish(device_id: str, session_id, src: str | None = None, delay: float = 0.5) -> None:
    src = src or attacker_ip(f"pub-{device_id}")
    with SessionLocal() as db:
        await _start(db, device_id, session_id, f"Rogue MQTT client from {src} publishes to {device_id}'s command topic")
        cmd_topic = mqtt_topics.command_topic(device_id)
        await record(db, "mqtt_subscribe_denied", category="mqtt", severity="medium", source="simulation", device_id=device_id,
                     src_ip=src, dst_ip=BROKER_IP, dst_port=BROKER_PORT, protocol="mqtt", mqtt_client="rogue-client",
                     mqtt_topic="#", username=device_id, outcome="denied", message="SUBSCRIBE '#' refused by ACL")
        for cmd in ("unlock", "set_interval 0", "reboot"):
            await record(db, "mqtt_publish_denied", category="mqtt", severity="high", source="simulation", device_id=device_id,
                         src_ip=src, dst_ip=BROKER_IP, dst_port=BROKER_PORT, protocol="mqtt", mqtt_client="rogue-client",
                         mqtt_topic=cmd_topic, username=device_id, outcome="denied", nbytes=40,
                         message=f"PUBLISH '{cmd}' refused by ACL (client is not the backend)", details={"payload": cmd})
            await asyncio.sleep(delay)


async def botnet_beaconing(device_id: str, session_id, beats: int = 8, interval: float = 1.5) -> None:
    with SessionLocal() as db:
        await _start(db, device_id, session_id, f"{device_id} infected: calls home to {C2_IP}:{C2_PORT} every {interval:g} s")
        for i in range(beats):
            await record(db, "net_connection", category="network", severity="info", source="simulation", device_id=device_id,
                         src_ip=device_ip(device_id), src_port=50000 + i, dst_ip=C2_IP, dst_port=C2_PORT, protocol="tls",
                         outcome="success", nbytes=random.randint(280, 320),
                         message=f"outbound TLS session to {C2_IP}:{C2_PORT} (SNI cdn-sync.example)",
                         details={"direction": "outbound", "sni": "cdn-sync.example", "beat": i + 1})
            await asyncio.sleep(interval * random.uniform(0.97, 1.03))


async def port_scan(device_id: str, session_id, src: str | None = None, delay: float = 0.1) -> None:
    src = src or attacker_ip(f"scan-{device_id}")
    target = device_ip(device_id)
    ports = [21, 22, 23, 25, 53, 80, 110, 123, 135, 139, 143, 161, 443, 445, 502, 554, 1883, 2323, 3389, 5683, 8080, 8443, 8883, 9000]
    with SessionLocal() as db:
        await _start(db, device_id, session_id, f"Port scan from {src} against {device_id} ({target})")
        for p in ports:
            open_ = p in (1883, 8883)
            await record(db, "net_conn_attempt", category="network", severity="info", source="simulation", device_id=device_id,
                         src_ip=src, src_port=random.randint(30000, 60000), dst_ip=target, dst_port=p,
                         protocol="udp" if p in (53, 123, 161, 5683) else "tcp", outcome="success" if open_ else "denied",
                         message=f"SYN to port {p}: {'open' if open_ else 'closed / filtered'}", details={"flags": "S"})
            await asyncio.sleep(delay)


async def data_exfiltration(device_id: str, session_id, chunks: int = 6, chunk_bytes: int = 1_250_000, delay: float = 1.0) -> None:
    with SessionLocal() as db:
        await _start(db, device_id, session_id, f"{device_id} uploads data to external address {DROP_IP}")
        for i in range(chunks):
            await record(db, "outbound_transfer", category="network", severity="info", source="simulation", device_id=device_id,
                         src_ip=device_ip(device_id), src_port=51000, dst_ip=DROP_IP, dst_port=443, protocol="https",
                         outcome="success", nbytes=chunk_bytes, message=f"HTTPS POST /upload part {i + 1}/{chunks}",
                         details={"direction": "outbound", "http_method": "POST", "path": "/upload"})
            await asyncio.sleep(delay)


async def g5_auth_attack(device_id: str, session_id, attempts: int = 6, delay: float = 0.6) -> None:
    supi = f"imsi-60401{zlib.crc32(device_id.encode()) % 10**10:010d}"
    with SessionLocal() as db:
        d = db.get(Device, device_id)
        cell = "BS-5G" if d is None or d.connection_type == "5g" else "BS-5G-RBT"
        await _start(db, device_id, session_id, f"Repeated 5G authentication failures for {device_id}'s SIM ({supi})")
        for i in range(attempts):
            await record(db, "5g_auth_failure", category="5g", severity="low", source="simulation", device_id=device_id,
                         src_ip=None, dst_ip=AMF_IP, protocol="nas-5g", username=supi, outcome="failure",
                         message="Registration reject: 5G-AKA authentication failure (MAC failure)",
                         details={"cell": cell, "cause": "MAC failure", "suci_concealed": True, "attempt": i + 1})
            await asyncio.sleep(delay)


async def config_tampering(device_id: str, session_id, src: str | None = None) -> None:
    src = src or attacker_ip(f"cfg-{device_id}")
    with SessionLocal() as db:
        d = db.get(Device, device_id)
        old = d.temp_max if d else 50
        await _start(db, device_id, session_id, f"Settings of {device_id} pushed over MQTT by an unknown client from {src}")
        await record(db, "config_change", category="config", severity="medium", source="simulation", device_id=device_id,
                     src_ip=src, dst_ip=BROKER_IP, dst_port=BROKER_PORT, protocol="mqtt", mqtt_client="unknown-client",
                     mqtt_topic=f"{config.MQTT_TOPIC_PREFIX}/iot/{device_id}/config", outcome="success",
                     message="retained config message: alarm limit raised, reporting interval 0",
                     details={"changed": {"temp_max": [old, 120], "interval_s": [5, 0]}, "actor_authenticated": False,
                              "applied": False, "note": "simulated: the dashboard's real device settings are not changed"})


async def gnss_jamming(device_id: str, session_id, samples: int = 5, delay: float = 0.8) -> None:
    with SessionLocal() as db:
        sats = [d.device_id for d in db.query(Device).filter(Device.connection_type == "satellite").order_by(Device.device_id)]
        targets = ([device_id] + [s for s in sats if s != device_id])[:3]
        await _start(db, device_id, session_id, f"GNSS jamming near {device_id} (affects {', '.join(targets)})")
        for i in range(samples):
            for t in targets:
                s = {"cn0": round(random.uniform(14, 22), 1), "satellites": random.randint(0, 2), "hdop": 99.0, "fix": False,
                     "offset_km": 0.0, "clock_offset_us": round(0.4 * (i + 1), 2), "implied_speed_mps": 0.0, "agc_db": -12.5}
                gnss.set_override(t, "jammed", s)
                await record(db, "gnss_sample", category="gnss", severity="info", source="simulation", device_id=t,
                             protocol="gnss", outcome="observed",
                             message=f"C/N0 {s['cn0']} dB-Hz, {s['satellites']} satellites, no fix", details=s)
            await asyncio.sleep(delay)


async def gnss_spoofing(device_id: str, session_id, delay: float = 1.0) -> None:
    with SessionLocal() as db:
        await _start(db, device_id, session_id, f"GNSS spoofing: a fake signal pulls {device_id}'s position away")
        prev = 0.0
        for i, off in enumerate([0.0, 0.8, 3.5, 12.0, 45.0, 140.0]):
            s = {"cn0": round(random.uniform(50.5, 51.0), 1), "satellites": 12, "hdop": 0.6, "fix": True,
                 "offset_km": off, "clock_offset_us": round(3.0 * i * i, 1), "implied_speed_mps": round((off - prev) * 1000 / 1.0, 1)}  # samples are 1 s apart (simulated clock)
            prev = off
            gnss.set_override(device_id, "spoofed", s)
            await record(db, "gnss_sample", category="gnss", severity="info", source="simulation", device_id=device_id,
                         protocol="gnss", outcome="observed",
                         message=f"position {off} km from the installed place, C/N0 {s['cn0']} dB-Hz on all satellites", details=s)
            await asyncio.sleep(delay)


# name -> (coroutine, default target). Merged into attack_simulator.ATTACKS.
SCENARIOS = {
    "mqtt-brute-force": (mqtt_brute_force, "IOT-002"),
    "unauthorized-publish": (unauthorized_publish, "IOT-002"),
    "botnet-beaconing": (botnet_beaconing, "IOT-003"),
    "port-scan": (port_scan, "IOT-001"),
    "data-exfiltration": (data_exfiltration, "IOT-003"),
    "5g-auth-attack": (g5_auth_attack, "IOT-002"),
    "config-tampering": (config_tampering, "IOT-001"),
    "gnss-jamming": (gnss_jamming, "IOT-001"),
    "gnss-spoofing": (gnss_spoofing, "IOT-003"),
}
