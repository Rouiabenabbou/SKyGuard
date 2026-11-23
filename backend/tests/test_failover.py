"""Failover state machine (Phase 8), tested with fixed times instead of waiting."""
import pytest

from app import config
from app.failover_service import FailoverManager
from tests.conftest import run

PRIMARY = {"path": ["IOT-001", "SAT-1", "GS-1", "CORE"], "links": ["a"], "access": "satellite", "latency_ms": 70, "degraded": False}
BACKUP = {"path": ["IOT-001", "BS-5G", "CORE"], "links": ["b"], "access": "5g", "latency_ms": 15, "degraded": False}
DEGRADED = {**PRIMARY, "degraded": True}


@pytest.fixture()
def fm(fresh, monkeypatch):
    monkeypatch.setattr(config, "HANDOVER_DELAY_MIN", 2.0)
    monkeypatch.setattr(config, "HANDOVER_DELAY_MAX", 2.0)
    m = FailoverManager()
    m.enabled = True
    return m


def test_stays_on_primary_when_healthy(fm, db):
    route = run(fm.decide(db, "IOT-001", PRIMARY, BACKUP, now=100))
    assert route["mode"] == "primary" and route["connected"]


def test_failover_then_failback(fm, db):
    run(fm.decide(db, "IOT-001", PRIMARY, BACKUP, now=100))
    # satellite lost: break-before-make -> no connectivity during the handover
    r = run(fm.decide(db, "IOT-001", None, BACKUP, now=102))
    assert r["mode"] == "switching" and r["connected"] is False
    r = run(fm.decide(db, "IOT-001", None, BACKUP, now=105))
    assert r["mode"] == "backup" and r["path"] == BACKUP["path"]
    # satellite back, but failback waits for FAILBACK_STABLE_SECONDS of health
    r = run(fm.decide(db, "IOT-001", PRIMARY, BACKUP, now=106))
    assert r["mode"] == "backup"
    r = run(fm.decide(db, "IOT-001", PRIMARY, BACKUP, now=106 + config.FAILBACK_STABLE_SECONDS))
    assert r["mode"] == "switching" and r["connected"] is True  # make-before-break
    r = run(fm.decide(db, "IOT-001", PRIMARY, BACKUP, now=120 + config.FAILBACK_STABLE_SECONDS))
    assert r["mode"] == "primary"
    stats = fm.summary(db)["stats"]
    assert stats["failovers"] == 1 and stats["failbacks"] == 1
    assert stats["avg_handover_ms"] == 2000


def test_failover_disabled_means_outage(fm, db):
    fm.enabled = False
    run(fm.decide(db, "IOT-001", PRIMARY, BACKUP, now=100))
    r = run(fm.decide(db, "IOT-001", None, BACKUP, now=102))
    assert r["mode"] == "down" and r["connected"] is False
    fm.count_lost("IOT-001")
    r = run(fm.decide(db, "IOT-001", PRIMARY, BACKUP, now=130))
    assert r["mode"] == "primary"
    assert fm.summary(db)["stats"]["readings_lost"] == 1


def test_degraded_primary_fails_over_without_interruption(fm, db):
    run(fm.decide(db, "IOT-001", DEGRADED, BACKUP, now=100))
    r = run(fm.decide(db, "IOT-001", DEGRADED, BACKUP, now=100 + config.DEGRADED_FAILOVER_SECONDS))
    assert r["mode"] == "switching" and r["connected"] is True  # still on the degraded primary
    r = run(fm.decide(db, "IOT-001", DEGRADED, BACKUP, now=110 + config.DEGRADED_FAILOVER_SECONDS))
    assert r["mode"] == "backup"


def test_no_backup_means_down(fm, db):
    run(fm.decide(db, "IOT-002", PRIMARY, None, now=100))
    assert run(fm.decide(db, "IOT-002", None, None, now=102))["mode"] == "down"


def test_drill_endpoint_moves_satellite_devices_to_backup(fresh):
    r = fresh.post("/api/failover/drill?seconds=60")
    assert r.status_code == 200
    routes = fresh.get("/api/network/topology").json()["routes"]
    assert routes["IOT-001"]["mode"] in ("switching", "down")
    assert routes["IOT-002"]["mode"] == "primary"  # 5G device is not affected
    fresh.post("/api/network/nodes/SAT-1/state", json={"state": "auto"})
