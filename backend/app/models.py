"""
Database tables (SQLAlchemy models).

Phase 2 uses devices, telemetry, network_events and simulation_sessions.
Phase 4 fills network_nodes and network_links and adds link_metrics (history
of link performance for the charts). security_alerts is used from Phase 5.
Phase 6 adds quarantine_records (history of every quarantine and release).
Phase 8 adds failover_events (every failover, failback and outage).
Phase 9 adds state_snapshots (the whole twin every 2 s, for the 4D timeline).

Times are stored in UTC.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    """Turn a stored UTC time into text like 2026-11-02T09:00:00Z for the browser."""
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


class Device(Base):
    """One registered IoT device and its latest known state."""

    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    device_name: Mapped[str] = mapped_column(String(100))
    device_type: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(String(100), default="")
    connection_type: Mapped[str] = mapped_column(String(20), default="5g")  # satellite | 5g
    status: Mapped[str] = mapped_column(String(20), default="offline")  # online | offline
    security_status: Mapped[str] = mapped_column(String(20), default="normal")  # normal | suspicious | quarantined
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery: Mapped[float | None] = mapped_column(Float, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Acceptable sensor ranges, used by the detection engine in Phase 5.
    temp_min: Mapped[float] = mapped_column(Float, default=-10)
    temp_max: Mapped[float] = mapped_column(Float, default=50)
    humidity_min: Mapped[float] = mapped_column(Float, default=5)
    humidity_max: Mapped[float] = mapped_column(Float, default=95)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "location": self.location,
            "connection_type": self.connection_type,
            "status": self.status,
            "security_status": self.security_status,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "battery": self.battery,
            "message_count": self.message_count,
            "last_seen": iso(self.last_seen),
            "ranges": {
                "temperature": [self.temp_min, self.temp_max],
                "humidity": [self.humidity_min, self.humidity_max],
            },
        }


class Telemetry(Base):
    """One sensor reading received from a device."""

    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(32), index=True)
    temperature: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    battery: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="simulator")  # simulator | mqtt | esp32
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "battery": self.battery,
            "source": self.source,
            "timestamp": iso(self.timestamp),
        }


class SecurityAlert(Base):
    """A cybersecurity alert (Phase 5)."""

    __tablename__ = "security_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(10))  # low | medium | high | critical
    description: Mapped[str] = mapped_column(Text)
    detection_method: Mapped[str] = mapped_column(String(20), default="rule")  # rule | ml
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | resolved
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "description": self.description,
            "detection_method": self.detection_method,
            "status": self.status,
            "timestamp": iso(self.timestamp),
        }


class NetworkNode(Base):
    """A piece of the telecom network: satellite, ground station, 5G tower... (Phase 4)."""

    __tablename__ = "network_nodes"

    node_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    node_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="online")  # online | offline | degraded | quarantined

    def to_dict(self) -> dict:
        return {"node_id": self.node_id, "name": self.name, "node_type": self.node_type, "status": self.status}


class NetworkLink(Base):
    """A connection between two network nodes (Phase 4)."""

    __tablename__ = "network_links"

    link_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_node: Mapped[str] = mapped_column(String(32), ForeignKey("network_nodes.node_id"))
    target_node: Mapped[str] = mapped_column(String(32), ForeignKey("network_nodes.node_id"))
    link_type: Mapped[str] = mapped_column(String(20))  # satellite | terrestrial
    status: Mapped[str] = mapped_column(String(20), default="online")
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    packet_loss: Mapped[float] = mapped_column(Float, default=0)  # percent
    bandwidth_mbps: Mapped[float] = mapped_column(Float, default=0)
    is_active_path: Mapped[bool] = mapped_column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "link_id": self.link_id,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "link_type": self.link_type,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "packet_loss": self.packet_loss,
            "bandwidth_mbps": self.bandwidth_mbps,
            "is_active_path": self.is_active_path,
        }


class NetworkEvent(Base):
    """Anything that happened, in time order. Powers the 4D timeline (Phase 9)."""

    __tablename__ = "network_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_sessions.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50))  # e.g. simulation_started, device_online
    category: Mapped[str] = mapped_column(String(20), default="system")  # system | device | security | network
    device_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "category": self.category,
            "device_id": self.device_id,
            "description": self.description,
            "timestamp": iso(self.timestamp),
        }


class SimulationSession(Base):
    """One run of the simulation, from Start/Reset until the next Reset."""

    __tablename__ = "simulation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | paused | ended

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_at": iso(self.started_at),
            "ended_at": iso(self.ended_at),
            "status": self.status,
        }


class LinkMetric(Base):
    """A snapshot of one link's performance, recorded every few seconds (Phase 4)."""

    __tablename__ = "link_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    link_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20))
    latency_ms: Mapped[float] = mapped_column(Float)
    packet_loss: Mapped[float] = mapped_column(Float)
    bandwidth_mbps: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "link_id": self.link_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "packet_loss": self.packet_loss,
            "bandwidth_mbps": self.bandwidth_mbps,
            "timestamp": iso(self.timestamp),
        }


class QuarantineRecord(Base):
    """One quarantine of one device, from start until release (Phase 6)."""

    __tablename__ = "quarantine_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String(20))  # operator | auto
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocked_messages: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "alert_id": self.alert_id,
            "blocked_messages": self.blocked_messages,
            "started_at": iso(self.started_at),
            "released_at": iso(self.released_at),
            "active": self.released_at is None,
        }


class FailoverEvent(Base):
    """One failover, failback or outage of one device (Phase 8)."""

    __tablename__ = "failover_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # failover | failback | outage
    from_mode: Mapped[str] = mapped_column(String(20))
    to_mode: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="")
    from_path: Mapped[str] = mapped_column(String(200), default="")
    to_path: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handover_ms: Mapped[float | None] = mapped_column(Float, nullable=True)  # simulated switch time
    interruption_ms: Mapped[float | None] = mapped_column(Float, nullable=True)  # no connectivity, total
    readings_lost: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "kind": self.kind,
            "from_mode": self.from_mode,
            "to_mode": self.to_mode,
            "reason": self.reason,
            "from_path": self.from_path,
            "to_path": self.to_path,
            "started_at": iso(self.started_at),
            "completed_at": iso(self.completed_at),
            "handover_ms": self.handover_ms,
            "interruption_ms": self.interruption_ms,
            "readings_lost": self.readings_lost,
        }


class StateSnapshot(Base):
    """The whole digital twin at one moment, stored as compact JSON (Phase 9).

    Recorded every network tick (2 s) while the simulation runs. The 4D timeline
    replays these frames in the 3D scene."""

    __tablename__ = "state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    data: Mapped[str] = mapped_column(Text)  # JSON, see timeline_service.build_frame()


class DeviceSetting(Base):
    """Extra facts about devices added by the operator from the dashboard.

    A separate table (instead of new columns on `devices`), so databases created
    by earlier phases keep working."""

    __tablename__ = "device_settings"

    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)  # False = a real board sends its own data
    added_by_operator: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "simulated": self.simulated,
                "added_by_operator": self.added_by_operator, "created_at": iso(self.created_at)}


class TopologyAddition(Base):
    """Network nodes and links added by the operator with the network builder.
    Only these can be removed again; the original topology stays."""

    __tablename__ = "topology_additions"

    item_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # node_id or link_id
    kind: Mapped[str] = mapped_column(String(10))  # node | link
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ======================================================================= v1.1
class User(Base):
    """A person who can log in to the dashboard."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(200))  # PBKDF2-SHA256, salted (never the password)
    role: Mapped[str] = mapped_column(String(20))  # viewer | operator | admin
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {"username": self.username, "role": self.role, "active": self.active,
                "created_at": iso(self.created_at), "last_login": iso(self.last_login)}


class AuthSession(Base):
    """A login token. Only its SHA-256 hash is stored."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLog(Base):
    """Who did what, and when: every change made through the API, plus logins."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(50), default="-")
    role: Mapped[str] = mapped_column(String(20), default="-")
    action: Mapped[str] = mapped_column(String(80))  # short, human readable
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(200))
    status_code: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(10))  # ok | denied | failed
    ip: Mapped[str] = mapped_column(String(64), default="")

    def to_dict(self) -> dict:
        return {"id": self.id, "timestamp": iso(self.timestamp), "username": self.username, "role": self.role,
                "action": self.action, "method": self.method, "path": self.path,
                "status_code": self.status_code, "outcome": self.outcome, "ip": self.ip}


class MotionReading(Base):
    """One reading of a motion (PIR) sensor: movement detected or not."""

    __tablename__ = "motion_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(32), index=True)
    motion: Mapped[bool] = mapped_column(Boolean)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "device_id": self.device_id, "motion": self.motion, "timestamp": iso(self.timestamp)}


class DeviceProfile(Base):
    """Where a node really is (latitude / longitude, kind of place) and which
    extra sensors a device has. Used by the real map, the 3D globe and motion."""

    __tablename__ = "device_profiles"

    node_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # device or network node
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    place_type: Mapped[str] = mapped_column(String(30), default="")  # farm | company | desert | lab | ...
    address: Mapped[str] = mapped_column(String(150), default="")
    has_motion: Mapped[bool] = mapped_column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {"latitude": self.latitude, "longitude": self.longitude, "place_type": self.place_type,
                "address": self.address, "has_motion": self.has_motion}


# ======================================================================= v1.2
class Company(Base):
    """A customer company that owns IoT devices (multi-tenant, see tenancy.py)."""

    __tablename__ = "companies"

    company_id: Mapped[str] = mapped_column(String(40), primary_key=True)  # short id, e.g. atlas-farms
    name: Mapped[str] = mapped_column(String(100))
    sector: Mapped[str] = mapped_column(String(40), default="")  # farm | offices | energy | ...
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {"company_id": self.company_id, "name": self.name, "sector": self.sector,
                "created_at": iso(self.created_at)}


class CompanyMember(Base):
    """User -> company. A user without a row here is a platform (provider) user."""

    __tablename__ = "company_members"

    username: Mapped[str] = mapped_column(String(50), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(40), index=True)


class CompanyDevice(Base):
    """IoT device -> company. A device without a row here belongs to the platform."""

    __tablename__ = "company_devices"

    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(40), index=True)


class NotifySettings(Base):
    """v1.2: where to send the phone alarm (one row, id=1). See notifier.py."""

    __tablename__ = "notify_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ntfy_server: Mapped[str] = mapped_column(String(200), default="https://ntfy.sh")
    ntfy_topic: Mapped[str] = mapped_column(String(100), default="")
    min_severity: Mapped[str] = mapped_column(String(10), default="high")  # low | medium | high | critical
    telegram_token: Mapped[str] = mapped_column(String(100), default="")
    telegram_chat_id: Mapped[str] = mapped_column(String(50), default="")


# ================================================== v1.3: long-term data (big data)
class TelemetryArchive(Base):
    """Raw readings of the long-term history (imported or generated months of data).
    Kept apart from `telemetry`, which holds the live session and is cleared by Reset."""

    __tablename__ = "telemetry_archive"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(32), index=True)
    temperature: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    battery: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)


class TelemetryHourly(Base):
    """One row per device per hour: the data warehouse used by Analytics.
    Fed by the live readings (every few minutes) and by the history archive; never
    cleared by Reset, so months of data stay available."""

    __tablename__ = "telemetry_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(32), index=True)
    hour: Mapped[datetime] = mapped_column(DateTime, index=True)  # start of the hour (UTC)
    readings: Mapped[int] = mapped_column(Integer, default=0)
    temp_avg: Mapped[float] = mapped_column(Float)
    temp_min: Mapped[float] = mapped_column(Float)
    temp_max: Mapped[float] = mapped_column(Float)
    hum_avg: Mapped[float] = mapped_column(Float)
    battery_avg: Mapped[float] = mapped_column(Float)

    def to_dict(self) -> dict:
        return {"id": self.id, "device_id": self.device_id, "hour": iso(self.hour), "readings": self.readings,
                "temp_avg": round(self.temp_avg, 2), "temp_min": round(self.temp_min, 2),
                "temp_max": round(self.temp_max, 2), "hum_avg": round(self.hum_avg, 2),
                "battery_avg": round(self.battery_avg, 1)}


class AlertHourly(Base):
    """Number of alerts per device, type and hour (for trends and the attack heatmap)."""

    __tablename__ = "alert_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(32), index=True, default="-")
    hour: Mapped[datetime] = mapped_column(DateTime, index=True)
    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(10))
    count: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {"id": self.id, "device_id": self.device_id, "hour": iso(self.hour), "alert_type": self.alert_type,
                "severity": self.severity, "count": self.count}


# ------------------------------------------------------------------ v1.4
class DeviceOps(Base):
    """v1.4 engineer tools: firmware, maintenance mode and last (simulated) reboot of a device.
    Its own table, so older databases upgrade by themselves."""

    __tablename__ = "device_ops"

    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    firmware: Mapped[str] = mapped_column(String(20), default="1.0.0")
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    maintenance_reason: Mapped[str] = mapped_column(String(200), default="")
    maintenance_by: Mapped[str] = mapped_column(String(64), default="")
    maintenance_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_reboot: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reboots: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "firmware": self.firmware, "maintenance": self.maintenance,
                "maintenance_reason": self.maintenance_reason, "maintenance_by": self.maintenance_by,
                "maintenance_since": iso(self.maintenance_since), "last_reboot": iso(self.last_reboot),
                "reboots": self.reboots}


class Incident(Base):
    """v1.4: an incident case that operators work on (made from one or more alerts)."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160))
    device_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="high")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | investigating | resolved
    assignee: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "device_id": self.device_id, "alert_id": self.alert_id,
                "severity": self.severity, "status": self.status, "assignee": self.assignee,
                "created_by": self.created_by, "created_at": iso(self.created_at),
                "updated_at": iso(self.updated_at), "resolved_at": iso(self.resolved_at)}


class IncidentNote(Base):
    """v1.4: one entry in an incident's timeline (a note, a status change, an assignment)."""

    __tablename__ = "incident_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(20), default="note")  # note | status | assign | created
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "incident_id": self.incident_id, "username": self.username, "kind": self.kind,
                "text": self.text, "created_at": iso(self.created_at)}


class AppFlag(Base):
    """v1.4: one-time facts about this database, e.g. "big demo companies were added once"."""

    __tablename__ = "app_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AiSettings(Base):
    """v1.4: the free AI key set from the dashboard (Admin -> AI assistant). One row, id=1.
    When the key here is empty, the values from .env are used."""

    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default="gemini")
    api_key: Mapped[str] = mapped_column(String(300), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ======================================================================= v1.5
class GraphLayout(Base):
    """Where each node sits in Analytics -> Network investigation, saved per user."""

    __tablename__ = "graph_layouts"

    owner: Mapped[str] = mapped_column(String(64), primary_key=True)  # username ("" when login is off)
    positions: Mapped[str] = mapped_column(Text, default="{}")  # JSON {node_id: [x, y]}
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ======================================================================= v2.0 SOC
class AlertTriage(Base):
    """Where an analyst is with one alert (separate table: no new columns on security_alerts)."""

    __tablename__ = "alert_triage"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(20), default="new")  # new | acknowledged | investigating | escalated | closed
    assignee: Mapped[str] = mapped_column(String(64), default="")
    first_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # for MTTA
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AlertActivity(Base):
    """History of what analysts did on an alert."""

    __tablename__ = "alert_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "alert_id": self.alert_id, "username": self.username, "action": self.action,
                "text": self.text, "created_at": iso(self.created_at)}


class RuleSetting(Base):
    """A detection rule switched on or off by an admin (default: on)."""

    __tablename__ = "rule_settings"

    rule_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ======================================================================= v2.1 SOC stages 2-4
class SecurityEvent(Base):
    """Stage 2: one security-relevant event (connection, login, publish, 5G auth, GNSS sample, config change).
    This is what a broker log, a firewall or a 5G core would record. In this project the events come from
    the simulator (source "simulation") or the lab board ("lab"); "production" is never used."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(20), default="network")  # auth|network|mqtt|5g|gnss|config|flow
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info|low|medium|high|critical
    source: Mapped[str] = mapped_column(String(12), default="simulation")  # simulation|lab|production
    device_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    src_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    src_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dst_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    dst_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol: Mapped[str] = mapped_column(String(16), default="")
    mqtt_client: Mapped[str] = mapped_column(String(64), default="")
    mqtt_topic: Mapped[str] = mapped_column(String(160), default="")
    username: Mapped[str] = mapped_column(String(64), default="")
    outcome: Mapped[str] = mapped_column(String(16), default="observed")  # success|failure|denied|observed
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[str] = mapped_column(Text, default="{}")  # JSON

    def to_dict(self) -> dict:
        import json
        try:
            details = json.loads(self.details or "{}")
        except ValueError:
            details = {}
        return {"id": self.id, "timestamp": iso(self.timestamp), "event_type": self.event_type, "category": self.category,
                "severity": self.severity, "source": self.source, "device_id": self.device_id,
                "src_ip": self.src_ip, "src_port": self.src_port, "dst_ip": self.dst_ip, "dst_port": self.dst_port,
                "protocol": self.protocol, "mqtt_client": self.mqtt_client, "mqtt_topic": self.mqtt_topic,
                "username": self.username, "outcome": self.outcome, "bytes": self.bytes, "message": self.message,
                "details": details}


class SavedQuery(Base):
    """Stage 2: a Threat Hunting query saved by an analyst (optionally shared with the team)."""

    __tablename__ = "saved_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(80))
    query: Mapped[str] = mapped_column(Text, default="")
    hours: Mapped[int] = mapped_column(Integer, default=24)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "owner": self.owner, "name": self.name, "query": self.query, "hours": self.hours,
                "shared": self.shared, "created_at": iso(self.created_at)}


class Ioc(Base):
    """Stage 3: an indicator of compromise in the local threat-intelligence list."""

    __tablename__ = "iocs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(10))  # ip | domain | hash | url
    value: Mapped[str] = mapped_column(String(300), index=True)
    threat: Mapped[str] = mapped_column(String(80), default="")
    confidence: Mapped[int] = mapped_column(Integer, default=50)  # 0-100
    tags: Mapped[str] = mapped_column(String(200), default="")
    origin: Mapped[str] = mapped_column(String(40), default="analyst")  # analyst | demo seed | playbook
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "value": self.value, "threat": self.threat,
                "confidence": self.confidence, "tags": [t for t in self.tags.split(",") if t], "origin": self.origin,
                "description": self.description, "active": self.active, "created_by": self.created_by,
                "created_at": iso(self.created_at), "expires_at": iso(self.expires_at)}


class IntelCache(Base):
    """Stage 3: answers of VirusTotal / AbuseIPDB / OTX, kept 24 h to save the free API quota."""

    __tablename__ = "intel_cache"

    key: Mapped[str] = mapped_column(String(340), primary_key=True)  # provider:value
    data: Mapped[str] = mapped_column(Text, default="{}")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IncidentPhase(Base):
    """Stage 3: where an incident is in the 7-phase workflow, and its MITRE ATT&CK mapping."""

    __tablename__ = "incident_phases"

    incident_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(20), default="detection")
    mitre: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of technique IDs added by analysts
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IncidentEvidence(Base):
    """Stage 3: one piece of evidence attached to an incident (alert, security event, IOC, AI analysis, note)."""

    __tablename__ = "incident_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # alert | security_event | ioc | ai_analysis | approval | note | intel
    ref: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[str] = mapped_column(Text, default="{}")
    added_by: Mapped[str] = mapped_column(String(64), default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        import json
        try:
            data = json.loads(self.data or "{}")
        except ValueError:
            data = {}
        return {"id": self.id, "incident_id": self.incident_id, "kind": self.kind, "ref": self.ref,
                "summary": self.summary, "data": data, "added_by": self.added_by, "added_at": iso(self.added_at)}


class ApprovalRequest(Base):
    """Stage 4: a sensitive response action that waits for a human with approval rights."""

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(30))  # isolate_device | release_device
    target: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(64), default="")
    requested_via: Mapped[str] = mapped_column(String(20), default="analyst")  # analyst | ai | playbook | demo
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|approved|rejected|executed|failed
    decided_by: Mapped[str] = mapped_column(String(64), default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "action": self.action, "target": self.target, "reason": self.reason,
                "requested_by": self.requested_by, "requested_via": self.requested_via,
                "incident_id": self.incident_id, "alert_id": self.alert_id, "status": self.status,
                "decided_by": self.decided_by, "decided_at": iso(self.decided_at),
                "decision_note": self.decision_note, "result": self.result, "created_at": iso(self.created_at)}


class UserMfa(Base):
    """Stage 4: TOTP two-factor login (RFC 6238) for one user."""

    __tablename__ = "user_mfa"

    username: Mapped[str] = mapped_column(String(50), primary_key=True)
    secret: Mapped[str] = mapped_column(String(64))  # base32
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_step: Mapped[int] = mapped_column(Integer, default=0)  # a code is accepted only once
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditChain(Base):
    """Stage 4: SHA-256 hash chain over audit_log rows, so an edited or deleted row is detected."""

    __tablename__ = "audit_chain"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class PlaybookRun(Base):
    """Stage 4: a response playbook run on one incident, with the state of each step."""

    __tablename__ = "playbook_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playbook_id: Mapped[str] = mapped_column(String(20))
    incident_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | completed | cancelled
    steps: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{id, state, by, at, note}]
    started_by: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AiInvestigation(Base):
    """Stage 3: one AI SOC analyst investigation: the tools it ran, the evidence and the answer."""

    __tablename__ = "ai_investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    tools: Mapped[str] = mapped_column(Text, default="[]")
    actions: Mapped[str] = mapped_column(Text, default="[]")
    provider: Mapped[str] = mapped_column(String(40), default="offline")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DemoRun(Base):
    """Stage 4: the end-to-end demo scenario (attack -> detection -> incident -> AI -> approval -> report)."""

    __tablename__ = "demo_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | waiting | completed | failed
    steps: Mapped[str] = mapped_column(Text, default="[]")
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_by: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
