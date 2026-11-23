"""
v2.0 SOC layer: the detection rule catalogue (with MITRE ATT&CK mapping),
rule on/off switches, alert enrichment (rule, technique, confidence, source
designation, triage state, duplicates, correlation) and SOC metrics.

Everything here reads the real rows the backend stores (alerts, events,
telemetry, incidents). Nothing is invented: when there is no data the
metric is None and the dashboard shows "—".

Source designation of an event / alert:
  simulation   produced by the built-in simulator or the attack simulator
  lab          sent by a real test board (a device set as "real board")
  production   not used in this project (no authorised real infrastructure)
"""
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from app import config
from app.models import AlertTriage, DeviceSetting, RuleSetting, SecurityAlert, utcnow

ATTACK_URL = "https://attack.mitre.org/techniques/{}/"


def _mitre(tid, name, tactic):
    if not tid:
        return None
    return {"id": tid, "name": name, "tactic": tactic, "url": ATTACK_URL.format(tid.replace(".", "/"))}


def rule_catalog() -> list[dict]:
    """Every detection rule the engine runs. The logic text shows the live thresholds."""
    c = config
    return [
        {"id": "CS-001", "alert_type": "excessive_message_rate", "name": "Message flood / DDoS indicator",
         "kind": "threshold", "severity": "high", "confidence": 0.85, "data_source": "Telemetry message rate",
         "mitre": _mitre("T1498", "Network Denial of Service", "Impact"),
         "logic": f"messages from one device in {c.RATE_WINDOW_SECONDS:g} s / {c.RATE_WINDOW_SECONDS:g} > {c.RATE_THRESHOLD_PER_SEC:g} msg/s",
         "explanation": "A device normally sends one reading every few seconds. A rate far above that means a flood "
                        "(DoS), a compromised device used in a botnet, or a firmware loop.",
         "test_attack": "excessive-traffic"},
        {"id": "CS-002", "alert_type": "unauthorized_device", "name": "Unknown device discovery",
         "kind": "signature", "severity": "high", "confidence": 0.95, "data_source": "Device registry + telemetry",
         "mitre": _mitre("T1200", "Hardware Additions", "Initial Access"),
         "logic": "telemetry arrives with a device ID that is not in the registry",
         "explanation": "Only registered devices may send data. An unknown ID is a rogue or cloned device trying to "
                        "join the network, or a misconfigured new device.",
         "test_attack": "unauthorized-device"},
        {"id": "CS-003", "alert_type": "abnormal_sensor_value", "name": "Out-of-range sensor reading",
         "kind": "rule", "severity": "medium/high", "confidence": 0.6, "data_source": "Telemetry values",
         "mitre": _mitre("T0856", "Spoof Reporting Message (ICS)", "Impair Process Control"),
         "logic": f"temperature or humidity outside the device's allowed range (high if ≥ {c.ABNORMAL_MARGIN:g} outside)",
         "explanation": "A value outside the allowed range can be false data injected by an attacker, a tampered or "
                        "broken sensor, or a real physical problem (e.g. a fridge door left open).",
         "test_attack": "abnormal-reading"},
        {"id": "CS-004", "alert_type": "suspicious_connections", "name": "MQTT brute force / connection storm",
         "kind": "threshold", "severity": "high", "confidence": 0.7, "data_source": "MQTT connect / status messages",
         "mitre": _mitre("T1110", "Brute Force", "Credential Access"),
         "logic": f"more than {c.CONN_THRESHOLD} connections from one device in {c.CONN_WINDOW_SECONDS:g} s",
         "explanation": "Many reconnects in a short time look like password guessing against the broker or a "
                        "device that is being taken over; it can also be an unstable link.",
         "test_attack": "connection-storm"},
        {"id": "CS-005", "alert_type": "device_id_spoofing", "name": "Device identity spoofing",
         "kind": "signature", "severity": "high", "confidence": 0.8, "data_source": "MQTT topic vs payload",
         "mitre": _mitre("T1036", "Masquerading", "Defense Evasion"),
         "logic": "the device ID inside the message differs from the device ID in the MQTT topic",
         "explanation": "A publisher is claiming to be another device: unauthorized publishing on someone else's "
                        "identity.", "test_attack": None},
        {"id": "CS-006", "alert_type": "malformed_message", "name": "Malformed telemetry",
         "kind": "signature", "severity": "low", "confidence": 0.4, "data_source": "MQTT payload parser",
         "mitre": _mitre("T1499", "Endpoint Denial of Service", "Impact"),
         "logic": "payload is not valid JSON or misses required fields",
         "explanation": "Broken messages come from buggy firmware or from fuzzing the broker. Not paged to the phone.",
         "test_attack": None},
        {"id": "CS-007", "alert_type": "link_failure", "name": "Satellite / 5G link down",
         "kind": "availability", "severity": "high/critical", "confidence": 1.0, "data_source": "Link metrics",
         "mitre": None, "logic": "a link's status becomes offline",
         "explanation": "Observed outage (rain fade, equipment failure or a simulated fault). Not an attack by "
                        "itself; check for jamming if several satellite links fail together.",
         "test_attack": None},
        {"id": "CS-008", "alert_type": "node_failure", "name": "Network node down",
         "kind": "availability", "severity": "critical", "confidence": 1.0, "data_source": "Node status",
         "mitre": None, "logic": "a satellite, ground station or tower becomes offline",
         "explanation": "Observed outage of shared infrastructure. Traffic fails over to backup paths when they exist.",
         "test_attack": None},
        {"id": "CS-009", "alert_type": "movement_detected", "name": "Physical intrusion (motion at night)",
         "kind": "rule", "severity": "high", "confidence": 0.75, "data_source": "PIR motion sensor",
         "mitre": None, "logic": "motion sensor triggers between 22:00 and 06:00",
         "explanation": "Someone (or an animal) is near the device out of hours; possible physical tampering.",
         "test_attack": None},
        {"id": "CS-010", "alert_type": "ml_anomaly", "name": "Behavioural anomaly (machine learning)",
         "kind": "ml", "severity": "medium", "confidence": 0.5, "data_source": "Telemetry (Isolation Forest)",
         "mitre": None, "logic": "Isolation Forest score below the learned threshold for this device",
         "explanation": "The combination of values does not match what the model learned as normal, even inside "
                        "the allowed ranges. A hypothesis to check, not a proof of attack.",
         "test_attack": None},
        # ---- v2.1 (stage 2): network, MQTT, 5G and GNSS rules on the security event store
        {"id": "CS-011", "alert_type": "mqtt_bruteforce", "name": "MQTT password guessing",
         "kind": "threshold", "severity": "high", "confidence": 0.85, "data_source": "Broker authentication log",
         "mitre": _mitre("T1110.001", "Brute Force: Password Guessing", "Credential Access"),
         "logic": f"≥ {c.BRUTE_FORCE_THRESHOLD} failed MQTT logins from one address in {c.BRUTE_FORCE_WINDOW_SECONDS:g} s",
         "explanation": "Devices log in with one fixed password. Many failures from one address is someone guessing "
                        "passwords against the broker to take over a device account.",
         "test_attack": "mqtt-brute-force"},
        {"id": "CS-012", "alert_type": "c2_beaconing", "name": "Botnet / C2 beaconing",
         "kind": "rule", "severity": "high", "confidence": 0.75, "data_source": "Outbound connections",
         "mitre": _mitre("T1071.001", "Application Layer Protocol: Web Protocols", "Command and Control"),
         "logic": f"≥ {c.BEACON_MIN_CONNECTIONS} outbound connections from a device to the same external address:port in 5 min "
                  f"with interval jitter ≤ {c.BEACON_MAX_JITTER:g}",
         "explanation": "Malware on a device calls its command server at a regular rhythm. Sensors only talk to the "
                        "broker, so regular traffic to an outside address is a strong infection sign.",
         "test_attack": "botnet-beaconing"},
        {"id": "CS-013", "alert_type": "port_scan", "name": "Port scan / service discovery",
         "kind": "threshold", "severity": "medium", "confidence": 0.8, "data_source": "Connection attempts",
         "mitre": _mitre("T1046", "Network Service Discovery", "Discovery"),
         "logic": f"one address probes ≥ {c.PORT_SCAN_THRESHOLD} different ports on one host in {c.PORT_SCAN_WINDOW_SECONDS:g} s",
         "explanation": "Reconnaissance before an attack: the scanner looks for open services (Telnet, MQTT, Modbus…).",
         "test_attack": "port-scan"},
        {"id": "CS-014", "alert_type": "unauthorized_publish", "name": "Unauthorized MQTT publish / subscribe",
         "kind": "signature", "severity": "high", "confidence": 0.9, "data_source": "Broker ACL decisions",
         "mitre": _mitre("T0855", "Unauthorized Command Message (ICS)", "Impair Process Control"),
         "logic": "the broker ACL refuses a PUBLISH or SUBSCRIBE (e.g. a client that is not the backend writes to a command topic)",
         "explanation": "Only the backend may send commands to devices. A refused publish on a command topic is an attempt "
                        "to control a device; subscribing to '#' is an attempt to read everyone's data.",
         "test_attack": "unauthorized-publish"},
        {"id": "CS-015", "alert_type": "data_exfiltration", "name": "Abnormal outbound transfer",
         "kind": "threshold", "severity": "critical", "confidence": 0.8, "data_source": "Outbound connections (bytes)",
         "mitre": _mitre("T1048", "Exfiltration Over Alternative Protocol", "Exfiltration"),
         "logic": f"one device sends ≥ {c.EXFIL_BYTES_PER_MINUTE / 1048576:.0f} MB to external addresses in 60 s",
         "explanation": "A sensor sends a few kilobytes per minute to the broker. Megabytes to an outside server means "
                        "data is being stolen or the device is used as a relay.",
         "test_attack": "data-exfiltration"},
        {"id": "CS-016", "alert_type": "5g_auth_anomaly", "name": "Suspicious 5G authentication",
         "kind": "threshold", "severity": "high", "confidence": 0.7, "data_source": "5G core (AMF/AUSF) authentication log",
         "mitre": _mitre("T1110", "Brute Force", "Credential Access"),
         "logic": f"≥ {c.G5_AUTH_FAIL_THRESHOLD} failed 5G-AKA authentications for one subscriber (SUPI) in 60 s",
         "explanation": "Repeated authentication failures for one SIM point to a cloned SIM, a fake base station "
                        "replaying messages, or an attack on the subscriber's keys.",
         "test_attack": "5g-auth-attack"},
        {"id": "CS-017", "alert_type": "unauthorized_config_change", "name": "Configuration change outside the dashboard",
         "kind": "signature", "severity": "high", "confidence": 0.85, "data_source": "Device configuration messages",
         "mitre": _mitre("T0836", "Modify Parameter (ICS)", "Impair Process Control"),
         "logic": "a device configuration message comes from a client that is not an authenticated dashboard user",
         "explanation": "Changing alarm limits or the reporting interval can hide an attack or a real physical problem. "
                        "All legitimate changes go through the dashboard and the audit log.",
         "test_attack": "config-tampering"},
        {"id": "CS-018", "alert_type": "threat_intel_match", "name": "Known malicious indicator (threat intel)",
         "kind": "signature", "severity": "high/critical", "confidence": 0.9, "data_source": "Security events + IOC list",
         "mitre": None,
         "logic": "source or destination address of any security event is an active IOC in Threat Intelligence",
         "explanation": "Traffic to or from an address already known as malicious (C2 server, drop server). The ATT&CK "
                        "technique depends on the indicator, see the IOC's description.",
         "test_attack": "botnet-beaconing"},
        {"id": "CS-019", "alert_type": "gnss_jamming", "name": "GNSS jamming",
         "kind": "rule", "severity": "high/critical", "confidence": 0.7, "data_source": "GNSS receiver samples (simulated)",
         "mitre": _mitre("T1464", "Network Denial of Service (Mobile)", "Impact"),
         "logic": f"3 samples in a row with C/N0 < {c.GNSS_MIN_CN0:g} dB-Hz and no fix (critical when 2+ devices at once)",
         "explanation": "A jammer drowns the weak satellite signal: position and time are lost. Several nearby terminals "
                        "failing together rules out a single broken antenna.",
         "test_attack": "gnss-jamming"},
        {"id": "CS-020", "alert_type": "gnss_spoofing", "name": "GNSS spoofing",
         "kind": "rule", "severity": "high", "confidence": 0.65, "data_source": "GNSS receiver samples (simulated)",
         "mitre": None,
         "logic": f"a fixed device reports a position > 5 km from where it is installed or an implied speed > {c.GNSS_MAX_SPEED_MPS:g} m/s",
         "explanation": "A fake, strong GNSS signal moves the reported position or clock. ATT&CK has no technique for it; "
                        "space frameworks such as SPARTA describe it.",
         "test_attack": "gnss-spoofing"},
        {"id": "CS-021", "alert_type": "credential_compromise", "name": "Login after brute force",
         "kind": "rule", "severity": "critical", "confidence": 0.9, "data_source": "Broker authentication log",
         "mitre": _mitre("T1078", "Valid Accounts", "Initial Access"),
         "logic": "a successful MQTT login from an address that triggered CS-011 in the last 5 min",
         "explanation": "The guessing worked: the attacker now holds a valid device account and can publish fake data.",
         "test_attack": "mqtt-brute-force"},
    ]


RULES_BY_TYPE = {r["alert_type"]: r for r in rule_catalog()}

# ------------------------------------------------------------ rule switches
_disabled: set[str] = set()
_loaded_at = 0.0


def _load(db: Session | None = None) -> None:
    global _loaded_at
    from app.database import SessionLocal
    own = db is None
    db = db or SessionLocal()
    try:
        ids = {r.rule_id for r in db.query(RuleSetting).filter(RuleSetting.enabled.is_(False))}
        _disabled.clear()
        _disabled.update(ids)
        _loaded_at = time.time()
    finally:
        if own:
            db.close()


def rule_enabled(alert_type: str) -> bool:
    rule = RULES_BY_TYPE.get(alert_type)
    if rule is None:
        return True
    if time.time() - _loaded_at > 30:
        try:
            _load()
        except Exception:
            pass
    return rule["id"] not in _disabled


def set_rule(db: Session, rule_id: str, enabled: bool, username: str) -> None:
    row = db.get(RuleSetting, rule_id) or RuleSetting(rule_id=rule_id)
    row.enabled, row.updated_by, row.updated_at = enabled, username, utcnow()
    db.merge(row)
    db.commit()
    _load(db)


# ------------------------------------------------------------ enrichment
def confidence(alert: SecurityAlert) -> float:
    rule = RULES_BY_TYPE.get(alert.alert_type)
    base = rule["confidence"] if rule else 0.5
    if alert.alert_type == "abnormal_sensor_value":
        base = 0.75 if alert.severity == "high" else 0.55
    return base


def source_of(db: Session, device_id: str | None, cache: dict) -> str:
    """simulation | lab. A real board (DeviceSetting.simulated = False) is lab telemetry."""
    if not device_id:
        return "simulation"
    if device_id not in cache:
        s = db.get(DeviceSetting, device_id)
        simulated = s.simulated if s is not None else device_id not in config.PHYSICAL_DEVICES
        cache[device_id] = "simulation" if simulated else "lab"
    return cache[device_id]


def enrich(db: Session, alerts: list[SecurityAlert]) -> list[dict]:
    """Alert rows + rule, MITRE, confidence, source, triage, duplicates and correlation group."""
    ids = [a.id for a in alerts]
    triage = {t.alert_id: t for t in db.query(AlertTriage).filter(AlertTriage.alert_id.in_(ids))} if ids else {}
    cache: dict = {}
    # duplicates: same device + type within 30 min (counted among the given alerts)
    by_key: dict = {}
    for a in alerts:
        by_key.setdefault((a.device_id, a.alert_type), []).append(a.timestamp)
    out = []
    for a in alerts:
        rule = RULES_BY_TYPE.get(a.alert_type)
        t = triage.get(a.id)
        state = t.state if t else ("closed" if a.status == "resolved" else "new")
        dups = sum(1 for ts in by_key[(a.device_id, a.alert_type)] if abs((ts - a.timestamp).total_seconds()) <= 1800) - 1
        out.append({
            **a.to_dict(),
            "rule_id": rule["id"] if rule else None,
            "rule_name": rule["name"] if rule else a.alert_type,
            "mitre": rule["mitre"] if rule else None,
            "confidence": confidence(a),
            "source": source_of(db, a.device_id, cache),
            "state": state,
            "assignee": t.assignee if t else "",
            "duplicates": max(dups, 0),
            "correlation": f"{a.device_id or 'net'}-{a.timestamp.strftime('%Y%m%d%H')}",
        })
    # correlation: a group is only interesting when it has 2+ alerts of different types
    groups: dict = {}
    for row in out:
        groups.setdefault(row["correlation"], set()).add(row["alert_type"])
    for row in out:
        if len(groups[row["correlation"]]) < 2:
            row["correlation"] = None
    return out


# ------------------------------------------------------------ metrics
def avg_minutes(pairs) -> float | None:
    vals = [(b - a).total_seconds() / 60 for a, b in pairs if a and b and b >= a]
    return round(sum(vals) / len(vals), 1) if vals else None


def since(hours: float):
    return utcnow() - timedelta(hours=hours)
