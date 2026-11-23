"""v2.4: cloud MQTT broker settings."""
import importlib


def _config(monkeypatch, host):
    monkeypatch.setenv("MQTT_HOST", host)
    from app import config
    return importlib.reload(config)


def test_mqtt_mode_local_and_cloud(monkeypatch):
    try:
        for host in ("localhost", "127.0.0.1", "mqtt", "192.168.1.20"):
            assert _config(monkeypatch, host).MQTT_MODE == "local"
        for host in ("abc123.s1.eu.hivemq.cloud", "x1.ala.eu-central-1.emqxsl.com"):
            assert _config(monkeypatch, host).MQTT_MODE == "cloud"
    finally:
        monkeypatch.delenv("MQTT_HOST")
        _config(monkeypatch, "localhost")
        monkeypatch.delenv("MQTT_HOST")


def test_mqtt_status_reports_mode():
    from app.mqtt_client import mqtt_service as mqtt_bridge
    status = mqtt_bridge.status()
    assert status["mode"] in ("local", "cloud")
    assert "tls" in status


def test_huawei_maas_is_default_ai(fresh):
    """v2.5: Huawei Cloud ModelArts Studio (MaaS) is the AI provider."""
    from app import ai_assistant
    assert "huawei" in ai_assistant.PROVIDERS
    r = fresh.put("/api/ai/settings", json={"provider": "huawei", "api_key": "test-key-123456",
                                            "model": "DeepSeek-V3", "base_url": "https://api-ap-southeast-1.modelarts-maas.com/v1"})
    assert r.status_code == 200
    s = r.json()
    assert s["configured"] and s["provider"] == "huawei" and s["provider_name"] == "Huawei Cloud MaaS"
    assert ai_assistant.endpoint("huawei") == "https://api-ap-southeast-1.modelarts-maas.com/v1/chat/completions"
    fresh.put("/api/ai/settings", json={"provider": "huawei", "api_key": "", "base_url": ""})
    assert fresh.get("/api/ai/settings").json()["configured"] is False
