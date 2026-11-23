"""Quarantine and release through the API."""


def test_manual_quarantine_and_release(fresh):
    r = fresh.post("/api/devices/IOT-001/quarantine", json={"reason": "manual test"})
    assert r.status_code == 200 and r.json()["changed"] is True
    active = fresh.get("/api/quarantine").json()["active"]
    assert [q["device_id"] for q in active] == ["IOT-001"]
    assert active[0]["triggered_by"] == "operator"

    # quarantined devices are cut out of routing
    route = fresh.get("/api/network/topology").json()["routes"]["IOT-001"]
    assert route["quarantined"] is True and route["connected"] is False

    r = fresh.post("/api/devices/IOT-001/release")
    assert r.json()["device"]["security_status"] == "normal"
    assert fresh.get("/api/quarantine").json()["active"] == []


def test_quarantine_twice_is_harmless(fresh):
    fresh.post("/api/devices/IOT-002/quarantine")
    assert fresh.post("/api/devices/IOT-002/quarantine").json()["changed"] is False


def test_auto_quarantine_switch(fresh):
    assert fresh.post("/api/quarantine/settings", json={"auto_quarantine": False}).json()["auto_quarantine"] is False
    assert fresh.get("/api/quarantine/settings").json()["auto_quarantine"] is False


def test_unknown_device_quarantine_404(fresh):
    assert fresh.post("/api/devices/NOPE/quarantine").status_code == 404
