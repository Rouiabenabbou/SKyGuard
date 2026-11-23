"""4D timeline recording (Phase 9) and exports / report (Phase 10)."""
from app.network_simulator import network
from tests.conftest import run


def test_frames_are_recorded_and_replayable(fresh, db):
    for _ in range(3):
        run(network.tick(db, None, update_metrics=True))
    rng = fresh.get("/api/timeline/range").json()
    assert rng["count"] >= 3
    data = fresh.get("/api/timeline/frames?max=50").json()
    frame = data["frames"][-1]
    assert set(frame) >= {"t", "nodes", "links", "routes", "devices", "avail", "alerts"}
    assert frame["nodes"]["SAT-1"] == "online"
    assert frame["routes"]["IOT-001"]["p"][0] == "IOT-001"


def test_frames_thinned_to_max(fresh, db):
    for _ in range(25):
        run(network.tick(db, None, update_metrics=True))
    assert fresh.get("/api/timeline/frames?max=10").json()["count"] <= 11


def test_bad_time_is_400(client):
    assert client.get("/api/timeline/at?t=yesterday").status_code == 400


def test_csv_exports(fresh):
    for name in ("telemetry", "alerts", "events", "quarantine", "failover"):
        r = fresh.get(f"/api/export/{name}.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert r.text.splitlines()[0].startswith("id,")
    assert fresh.get("/api/export/passwords.csv").status_code == 404


def test_report_summary(fresh):
    s = fresh.get("/api/report/summary").json()
    assert s["simulated"] is True
    assert s["totals"]["devices"] == 3
    assert {d["device_id"] for d in s["devices"]} == {"IOT-001", "IOT-002", "IOT-003"}


def test_csv_saved_to_exports_folder(fresh):
    from pathlib import Path

    res = fresh.post("/api/export/all/save").json()
    assert {f["name"] for f in res["files"]} == {"telemetry", "alerts", "events", "failover", "quarantine", "hourly"}
    for f in res["files"]:
        path = Path(f["path"])
        assert path.parent == Path(res["folder"]) and path.exists()
        assert path.read_text(encoding="utf-8-sig").splitlines()[0].startswith("id,")
    assert fresh.post("/api/export/nope/save").status_code == 404
