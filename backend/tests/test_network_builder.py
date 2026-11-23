"""Network builder: the operator adds satellites, ground stations, towers and links."""
from app.models import NetworkLink, NetworkNode

NEW_DEV = {"device_id": "IOT-005", "device_name": "Ship Tracker 05", "device_type": "Asset Tracker",
           "location": "At sea", "connection_type": "satellite", "access_node": "SAT-2",
           "temp_min": -10, "temp_max": 45, "humidity_min": 10, "humidity_max": 95}


def test_build_second_satellite_path_and_attach_device(fresh, db, client):
    try:
        assert client.post("/api/network/nodes", json={"node_id": "SAT-2", "node_type": "satellite"}).status_code == 201
        assert client.post("/api/network/nodes", json={"node_id": "GS-2", "name": "Ground Station Beta",
                                                       "node_type": "ground_station"}).status_code == 201
        for a, b, t in (("SAT-2", "GS-2", "satellite"), ("GS-2", "CORE", "fiber")):
            r = client.post("/api/network/links", json={"source_node": a, "target_node": b, "link_type": t})
            assert r.status_code == 201, r.text
        assert client.post("/api/devices", json=NEW_DEV).status_code == 201
        snap = client.get("/api/network/topology").json()
        assert snap["routes"]["IOT-005"]["path"] == ["IOT-005", "SAT-2", "GS-2", "CORE"]
        assert next(n for n in snap["nodes"] if n["node_id"] == "SAT-2")["added"] is True
        assert next(n for n in snap["nodes"] if n["node_id"] == "SAT-1")["added"] is False

        # SAT-2 fails -> IOT-005 can still reach the core over its backup 5G link
        client.post("/api/network/nodes/SAT-2/state", json={"state": "offline"})
        client.post("/api/network/nodes/SAT-2/state", json={"state": "auto"})

        assert client.delete("/api/network/nodes/SAT-2").status_code == 409  # IOT-005 still uses it

        # duplicates and bad input
        assert client.post("/api/network/links", json={"source_node": "GS-2", "target_node": "SAT-2",
                                                       "link_type": "satellite"}).status_code == 409
        assert client.post("/api/network/nodes", json={"node_id": "SAT-2", "node_type": "satellite"}).status_code == 409
        assert client.post("/api/network/nodes", json={"node_id": "X", "node_type": "satellite"}).status_code == 422
        assert client.post("/api/network/nodes", json={"node_id": "CORE-2", "node_type": "core"}).status_code == 422
        assert client.post("/api/devices", json={**NEW_DEV, "device_id": "IOT-006",
                                                 "access_node": "GS-2"}).status_code == 400  # not a satellite
    finally:
        client.delete("/api/devices/IOT-005")
        client.delete("/api/network/nodes/SAT-2")
        client.delete("/api/network/nodes/GS-2")
    assert db.get(NetworkNode, "SAT-2") is None
    assert db.query(NetworkLink).filter(NetworkLink.target_node == "CORE", NetworkLink.source_node == "GS-2").count() == 0


def test_original_topology_is_protected(fresh, client):
    assert client.delete("/api/network/nodes/SAT-1").status_code == 409
    assert client.delete("/api/network/links/L-SAT-GS").status_code == 409
    assert client.delete("/api/network/nodes/NOPE").status_code == 404
    r = client.post("/api/network/links", json={"source_node": "SAT-1", "target_node": "SAT-1", "link_type": "lan"})
    assert r.status_code == 400
