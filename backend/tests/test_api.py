"""Basic API checks: the server answers and returns the expected shapes."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_info_lists_all_components(client):
    data = client.get("/api/info").json()
    assert data["phase"] == 12
    ids = {c["id"] for c in data["components"]}
    assert {"backend", "mqtt", "detection", "network", "twin", "failover", "timeline", "dashboard"} <= ids


def test_three_registered_devices(fresh):
    devices = fresh.get("/api/devices").json()["devices"]
    assert [d["device_id"] for d in devices] == ["IOT-001", "IOT-002", "IOT-003"]
    assert all(d["security_status"] == "normal" for d in devices)


def test_unknown_device_is_404(client):
    assert client.get("/api/devices/NOPE-1").status_code == 404


def test_simulation_start_pause(fresh):
    assert fresh.post("/api/simulation/start").json()["running"] is True
    assert fresh.post("/api/simulation/pause").json()["running"] is False


def test_network_topology_shape(fresh):
    snap = fresh.get("/api/network/topology").json()
    node_ids = {n["node_id"] for n in snap["nodes"]}
    assert {"SAT-1", "GS-1", "BS-5G", "CORE", "SEC", "IOT-001"} <= node_ids
    assert snap["routes"]["IOT-001"]["path"] == ["IOT-001", "SAT-1", "GS-1", "CORE"]
    assert snap["routes"]["IOT-002"]["path"] == ["IOT-002", "BS-5G", "CORE"]
