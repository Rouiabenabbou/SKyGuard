"""
Satellite -> 5G failover (simulation).

Each IoT device has a PRIMARY path to the telecom core (for IOT-001/003: over
the satellite) and may have a BACKUP path (a terrestrial 5G access link).
Every network tick this manager decides, per device, which path carries its
traffic, using a small state machine:

    primary ──(primary path lost, or degraded too long)──► switching ──(handover done)──► backup
       ▲                                                                                   │
       └────────(primary healthy again for FAILBACK_STABLE_SECONDS: "failback")────────────┘

    any state ──(no usable path at all)──► down ──(a path comes back)──► primary / switching

While "switching" the device has no connectivity for a short, simulated
handover time (re-attaching to the 5G cell). Readings produced while a device
has no connectivity are counted as LOST, which lets you compare the outage with
failover on and off.

This is a teaching model. It is NOT a real 3GPP satellite/5G handover
procedure and does not control any real network.
"""
import random
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import config
from app.event_log import log_event
from app.models import FailoverEvent, utcnow
from app.websocket_manager import manager


@dataclass
class DeviceLinkState:
    mode: str = "primary"  # primary | switching | backup | down
    target: str | None = None  # path being switched to: "primary" | "backup"
    switch_started: float = 0.0
    switch_until: float = 0.0
    outage_started: float | None = None  # when connectivity was lost (for interruption time)
    degraded_since: float | None = None
    primary_ok_since: float | None = None
    keep_old: bool = False  # make-before-break: old path still carries traffic while switching
    lost_readings: int = 0
    event_id: int | None = None  # FailoverEvent row being filled in
    reason: str = ""
    history_modes: list = field(default_factory=list)


class FailoverManager:
    def __init__(self) -> None:
        self.enabled = config.FAILOVER_ENABLED
        self.states: dict[str, DeviceLinkState] = {}
        self.session_id_provider = lambda: None  # set by main.py
        self.drill_until: float | None = None
        self._pending_lost: dict[int, int] = {}  # FailoverEvent id -> readings lost so far

    # ----------------------------------------------------------- helpers
    def state(self, device_id: str) -> DeviceLinkState:
        return self.states.setdefault(device_id, DeviceLinkState())

    def reset(self, db: Session) -> None:
        self.states.clear()
        self._pending_lost.clear()
        self.drill_until = None
        db.query(FailoverEvent).delete()
        db.commit()

    def count_lost(self, device_id: str) -> None:
        """A reading was produced while the device had no path to the core."""
        st = self.state(device_id)
        st.lost_readings += 1
        if st.event_id is not None:
            self._pending_lost[st.event_id] = self._pending_lost.get(st.event_id, 0) + 1

    @staticmethod
    def _handover_delay() -> float:
        return random.uniform(config.HANDOVER_DELAY_MIN, config.HANDOVER_DELAY_MAX)

    async def _open_event(self, db: Session, device_id: str, kind: str, from_mode: str, to_mode: str,
                          reason: str, from_path, to_path) -> FailoverEvent:
        ev = FailoverEvent(session_id=self.session_id_provider(), device_id=device_id, kind=kind,
                           from_mode=from_mode, to_mode=to_mode, reason=reason,
                           from_path=" > ".join(from_path or []), to_path=" > ".join(to_path or []))
        db.add(ev)
        db.commit()
        return ev

    def _close_event(self, db: Session, ev_id: int | None, handover_ms: float | None, interruption_ms: float | None) -> FailoverEvent | None:
        if ev_id is None:
            return None
        ev = db.get(FailoverEvent, ev_id)
        if ev is None:
            return None
        ev.completed_at = utcnow()
        ev.handover_ms = round(handover_ms, 0) if handover_ms is not None else None
        ev.interruption_ms = round(interruption_ms, 0) if interruption_ms is not None else None
        ev.readings_lost = self._pending_lost.pop(ev_id, 0)
        db.commit()
        return ev

    # -------------------------------------------------------------- core
    async def decide(self, db: Session, device_id: str, primary: dict | None, backup: dict | None,
                     now: float, advance: bool = True) -> dict:
        """Pick the route for one device. `primary` / `backup` are candidate routes
        ({"path", "links", "latency_ms", "degraded", ...}) or None if unavailable.
        With advance=False (simulation paused) the state machine does not move."""
        st = self.state(device_id)
        if not advance:
            return self._route_for(st, primary, backup, now)
        sid = self.session_id_provider()
        primary_healthy = primary is not None and not primary["degraded"]

        # How long has the primary been degraded / healthy?
        if primary is not None and primary["degraded"]:
            st.degraded_since = st.degraded_since or now
        else:
            st.degraded_since = None
        if primary_healthy:
            st.primary_ok_since = st.primary_ok_since or now
        else:
            st.primary_ok_since = None

        degraded_too_long = (config.FAILOVER_ON_DEGRADED and st.degraded_since is not None
                             and now - st.degraded_since >= config.DEGRADED_FAILOVER_SECONDS
                             and backup is not None and not backup["degraded"])

        async def start_switch(target: str, kind: str, reason: str, from_route, to_route):
            """Begin a handover. If the old path still works (from_route given) traffic keeps
            flowing on it until the new one is ready ("make before break"). Otherwise the
            device is cut off during the handover ("break before make")."""
            from_mode = st.mode
            st.mode, st.target, st.reason = "switching", target, reason
            st.switch_started = now
            st.switch_until = now + self._handover_delay()
            st.keep_old = from_route is not None
            if st.outage_started is None and not st.keep_old:
                st.outage_started = now
            ev = await self._open_event(db, device_id, kind, from_mode, target, reason,
                                        (from_route or {}).get("path"), (to_route or {}).get("path"))
            st.event_id = ev.id
            label = "FAILOVER" if kind == "failover" else "FAILBACK"
            await log_event(db, f"{kind}_started",
                            f"{label} {device_id}: {reason}; switching to the {target} path "
                            f"({(to_route or {}).get('access', '?')} access)",
                            category="network", device_id=device_id, session_id=sid)

        async def go_down(reason: str):
            if st.mode == "down":
                return
            st.mode, st.target, st.reason = "down", None, reason
            st.outage_started = st.outage_started or now
            if st.event_id is None:
                ev = await self._open_event(db, device_id, "outage", "primary", "down", reason, None, None)
                st.event_id = ev.id
            await log_event(db, "connectivity_lost", f"{device_id} has NO path to the core: {reason}",
                            category="network", device_id=device_id, session_id=sid)

        async def finish(mode: str, route: dict):
            # handover time = the simulated re-attach time; interruption = how long the
            # device really had no path (detection delay + handover), 0 for make-before-break
            handover_ms = (st.switch_until - st.switch_started) * 1000 if st.mode == "switching" else None
            interruption_ms = (now - st.outage_started) * 1000 if st.outage_started else 0.0
            prev = st.mode
            st.mode, st.target = mode, None
            st.outage_started = None
            ev = self._close_event(db, st.event_id, handover_ms, interruption_ms)
            st.event_id = None
            if prev == "switching":
                await log_event(db, "failover_completed" if mode == "backup" else "failback_completed",
                                f"{device_id} now on the {mode} path ({route['access']}) after a "
                                f"{handover_ms / 1000:.1f} s handover; service interrupted "
                                f"{interruption_ms / 1000:.1f} s, {ev.readings_lost if ev else 0} readings lost",
                                category="network", device_id=device_id, session_id=sid)
            else:
                await log_event(db, "connectivity_restored",
                                f"{device_id} reaches the core again via the {mode} path after "
                                f"{(interruption_ms or 0) / 1000:.0f} s without connectivity "
                                f"({ev.readings_lost if ev else 0} readings lost)",
                                category="network", device_id=device_id, session_id=sid)
            if ev:
                await manager.broadcast("failover", {"event": ev.to_dict()})

        # ---------------- state machine
        if st.mode == "primary":
            if primary is None:
                if self.enabled and backup is not None:
                    await start_switch("backup", "failover", "primary path lost", None, backup)
                else:
                    if backup is None:
                        await go_down("primary path lost, no backup path")
                    else:
                        await go_down("primary path lost (failover disabled)")
            elif self.enabled and degraded_too_long:
                await start_switch("backup", "failover",
                                   f"primary path degraded for {config.DEGRADED_FAILOVER_SECONDS:.0f}+ s", primary, backup)

        elif st.mode == "switching":
            target_route = backup if st.target == "backup" else primary
            old_route = primary if st.target == "backup" else backup
            if st.keep_old and old_route is None:
                # the old path died during a make-before-break handover: now we are cut off
                st.keep_old = False
                st.outage_started = st.outage_started or now
            if not self.enabled and st.target == "backup":
                # operator switched failover off in the middle of a handover: abandon it
                if primary is not None:
                    await finish("primary", primary)
                else:
                    st.mode = "primary"  # so go_down() records the outage
                    await go_down("failover disabled during handover")
            elif now >= st.switch_until:
                if target_route is not None:
                    await finish(st.target, target_route)
                else:
                    other = primary if st.target == "backup" else backup
                    if other is not None:
                        st.target = "primary" if st.target == "backup" else "backup"
                        st.switch_until = now + self._handover_delay()
                    else:
                        await go_down("target path disappeared during handover")

        elif st.mode == "backup":
            if backup is None:
                if primary is not None:
                    await start_switch("primary", "failback", "backup path lost", None, primary)
                else:
                    await go_down("backup path lost too")
            elif (primary_healthy and st.primary_ok_since is not None
                  and now - st.primary_ok_since >= config.FAILBACK_STABLE_SECONDS):
                await start_switch("primary", "failback",
                                   f"primary path healthy for {config.FAILBACK_STABLE_SECONDS:.0f} s", backup, primary)
            elif not self.enabled and primary is not None:
                await start_switch("primary", "failback", "failover disabled by operator", backup, primary)

        elif st.mode == "down":
            if primary is not None:
                await finish("primary", primary)
            elif self.enabled and backup is not None:
                await start_switch("backup", "failover", "backup path available", None, backup)

        return self._route_for(st, primary, backup, now)

    @staticmethod
    def _route_for(st: DeviceLinkState, primary: dict | None, backup: dict | None, now: float) -> dict:
        """The route the rest of the app sees for the device's current mode."""
        if st.mode == "primary" and primary is not None:
            return {**primary, "connected": True, "mode": "primary"}
        if st.mode == "backup" and backup is not None:
            return {**backup, "connected": True, "mode": "backup"}
        base = {"connected": False, "path": [], "links": [], "access": None, "latency_ms": None, "degraded": False}
        if st.mode == "switching":
            remaining = max(0.0, st.switch_until - now)
            extra = {"mode": "switching", "switching_to": st.target, "handover_remaining_s": round(remaining, 1)}
            old = primary if st.target == "backup" else backup
            if st.keep_old and old is not None:
                return {**old, "connected": True, **extra}
            return {**base, **extra}
        return {**base, "mode": "down"}

    # ------------------------------------------------------------ status
    def summary(self, db: Session) -> dict:
        events = db.query(FailoverEvent).order_by(FailoverEvent.id.desc()).limit(200).all()
        done = [e for e in events if e.completed_at is not None]
        handovers = [e.handover_ms for e in done if e.handover_ms is not None and e.kind == "failover"]
        interruptions = [e.interruption_ms for e in done if e.interruption_ms is not None]
        return {
            "enabled": self.enabled,
            "settings": {
                "handover_delay_s": [config.HANDOVER_DELAY_MIN, config.HANDOVER_DELAY_MAX],
                "failback_stable_s": config.FAILBACK_STABLE_SECONDS,
                "failover_on_degraded": config.FAILOVER_ON_DEGRADED,
                "degraded_failover_s": config.DEGRADED_FAILOVER_SECONDS,
            },
            "devices": {
                d: {"mode": s.mode, "switching_to": s.target, "lost_readings": s.lost_readings, "reason": s.reason}
                for d, s in sorted(self.states.items())
            },
            "stats": {
                "failovers": sum(1 for e in events if e.kind == "failover"),
                "failbacks": sum(1 for e in events if e.kind == "failback"),
                "outages": sum(1 for e in events if e.kind == "outage"),
                "avg_handover_ms": round(sum(handovers) / len(handovers)) if handovers else None,
                "avg_interruption_ms": round(sum(interruptions) / len(interruptions)) if interruptions else None,
                "readings_lost": sum(s.lost_readings for s in self.states.values()),
            },
            "drill_active": self.drill_until is not None and self.drill_until > time.time(),
            "drill_seconds_left": round(self.drill_until - time.time()) if self.drill_until and self.drill_until > time.time() else 0,
        }


failover = FailoverManager()
