"""Phone alarm (v1.2): push notifications for serious alerts (ntfy / Telegram), with the network mocked."""
import asyncio

import httpx

from app.notifier import notifier
from tests.conftest import run


class FakeResponse:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


def test_settings_and_validation(client):
    r = client.get("/api/notify/settings")
    assert r.status_code == 200 and "telegram_token" not in r.json()
    assert client.put("/api/notify/settings", json={"enabled": True, "ntfy_topic": "short"}).status_code == 400
    assert client.put("/api/notify/settings", json={"ntfy_topic": "bad topic!"}).status_code == 422
    r = client.put("/api/notify/settings", json={"enabled": True, "ntfy_topic": "cybershield-test-topic-123",
                                                 "telegram_token": "123:SECRET", "telegram_chat_id": "42"})
    body = r.json()
    assert r.status_code == 200 and body["telegram_token_set"] is True and "SECRET" not in r.text
    client.put("/api/notify/settings", json={"enabled": False, "ntfy_topic": "", "telegram_token": "", "telegram_chat_id": ""})


def test_send_builds_ntfy_and_telegram_messages(monkeypatch):
    calls = []

    async def fake_post(self, url, json=None, **kw):
        calls.append((url, json))
        return FakeResponse(500 if "telegram" in url else 200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    settings = {"ntfy_server": "https://ntfy.sh", "ntfy_topic": "cybershield-test-topic-123",
                "telegram_token": "123:SECRET", "telegram_chat_id": "42"}
    alert = {"id": 7, "alert_type": "excessive_message_rate", "severity": "high", "device_id": "IOT-002",
             "description": "IOT-002 floods"}
    results = run(notifier.send(settings, alert))
    ntfy = next(j for u, j in calls if "ntfy" in u)
    assert ntfy["topic"] == "cybershield-test-topic-123" and ntfy["priority"] == 5 and "IOT-002" in ntfy["message"]
    assert results[0]["ok"] and not results[1]["ok"] and "SECRET" not in results[1]["error"]


def test_test_endpoint(client, monkeypatch):
    async def fake_post(self, url, json=None, **kw):
        return FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert client.post("/api/notify/test").status_code == 400  # nothing configured
    client.put("/api/notify/settings", json={"ntfy_topic": "cybershield-test-topic-123"})
    r = client.post("/api/notify/test")
    assert r.status_code == 200 and r.json()["ok"] is True
    client.put("/api/notify/settings", json={"ntfy_topic": ""})


def test_serious_alert_rings_the_phone(fresh, db, monkeypatch):
    from app.detection_engine import detector

    sent = []

    async def fake_send(settings, alert):
        sent.append(alert)
        return []

    monkeypatch.setattr(notifier, "send", fake_send)
    fresh.put("/api/notify/settings", json={"enabled": True, "ntfy_topic": "cybershield-test-topic-123",
                                            "min_severity": "high"})

    async def scenario():
        await detector.raise_alert(db, "notify_test_low", "low", "small thing", device_id="IOT-001")
        await detector.raise_alert(db, "notify_test_high", "high", "big thing", device_id="IOT-001")
        await asyncio.sleep(0.05)  # let the background task run

    run(scenario())
    assert [a["alert_type"] for a in sent] == ["notify_test_high"]
    fresh.put("/api/notify/settings", json={"enabled": False, "ntfy_topic": ""})


def test_attacks_ring_automatically(fresh, db, monkeypatch):
    """Saving a topic switches the alarm on; every attack then rings with no button, network faults don't."""
    from app.detection_engine import detector

    sent = []

    async def fake_send(settings, alert):
        sent.append(alert["alert_type"])
        return [{"channel": "ntfy", "ok": True}]

    monkeypatch.setattr(notifier, "send", fake_send)
    fresh.put("/api/notify/settings", json={"enabled": False, "ntfy_topic": ""})
    r = fresh.put("/api/notify/settings", json={"ntfy_topic": "cybershield-test-topic-456", "min_severity": "medium"})
    assert r.json()["enabled"] is True  # first topic -> automatic alarm on

    async def scenario():
        await detector.raise_alert(db, "abnormal_sensor_value", "medium", "odd value", device_id="IOT-002")
        await detector.raise_alert(db, "excessive_message_rate", "high", "flood", device_id="IOT-002")
        await detector.raise_alert(db, "link_failure", "high", "link down", subject="L-TEST")
        await asyncio.sleep(0.05)

    run(scenario())
    assert sent == ["abnormal_sensor_value", "excessive_message_rate"]

    # a successful test alarm also switches it on
    fresh.put("/api/notify/settings", json={"enabled": False})
    assert fresh.post("/api/notify/test").json()["enabled"] is True
    fresh.put("/api/notify/settings", json={"enabled": False, "ntfy_topic": ""})
