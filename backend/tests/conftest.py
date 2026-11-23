"""
Shared test setup.

Each test run uses its own temporary SQLite database and turns off everything
that depends on the outside world or on timing: MQTT broker, simulation
autostart, random rain fade. The settings must be in the environment BEFORE
the app is imported, because app/config.py reads them at import time.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="cybershield-test-")
# TEST_DATABASE_URL runs the tests on PostgreSQL instead (v1.3), e.g. postgresql://user@host/db
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["MQTT_ENABLED"] = "false"
os.environ["SIM_AUTOSTART"] = "false"
os.environ["NET_RANDOM_EVENTS"] = "false"
os.environ["ESP32_ENABLED"] = "false"
os.environ["ML_ENABLED"] = "false"
os.environ["SEED_BIG_COMPANIES"] = "false"  # tests use the 3 classic devices; test_v14.py seeds them itself
os.environ["AUTH_ENABLED"] = "false"  # most tests check features; test_auth.py switches login on
os.environ["AI_API_KEY"] = ""
os.environ["EXPORTS_DIR"] = str(Path(_tmp) / "exports")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "import app" works

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs the startup code (creates and seeds the database)
        yield c


@pytest.fixture()
def fresh(client):
    """Clean state for one test: reset the simulation and pause it, so no
    background readings arrive while the test runs."""
    from app.routes.simulation import _running_attacks
    for task in list(_running_attacks):  # a simulated attack of an earlier test must not leak into this one
        task.get_loop().call_soon_threadsafe(task.cancel)
    client.post("/api/simulation/pause")
    client.post("/api/simulation/reset?restart=false")  # wipe without restarting: no reading can slip in
    from app.quarantine_service import quarantine
    from app.failover_service import failover
    quarantine.auto_enabled = True
    failover.enabled = True
    return client


@pytest.fixture()
def db():
    from app.database import SessionLocal
    with SessionLocal() as session:
        yield session


def run(coro):
    """Run one coroutine (e.g. ingest_telemetry) from a normal test function."""
    return asyncio.run(coro)
