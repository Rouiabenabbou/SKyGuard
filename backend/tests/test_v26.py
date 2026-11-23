"""v2.6: DeepSeek is the AI analyst."""
import asyncio
import importlib


def test_deepseek_is_default(fresh):
    from app import ai_assistant, config
    assert config.AI_PROVIDER == "deepseek"
    assert ai_assistant.endpoint("deepseek") == "https://api.deepseek.com/chat/completions"
    r = fresh.put("/api/ai/settings", json={"provider": "deepseek", "api_key": "sk-test-123456789", "model": ""})
    assert r.status_code == 200
    s = r.json()
    assert s["configured"] and s["provider"] == "deepseek" and s["provider_name"] == "DeepSeek"
    assert s["model"] == "deepseek-chat" and s["base_url"] is None
    fresh.put("/api/ai/settings", json={"provider": "deepseek", "api_key": ""})
    assert fresh.get("/api/ai/settings").json()["configured"] is False


def test_deepseek_request_and_fallback(fresh, monkeypatch):
    """The request goes to DeepSeek with a Bearer key; an error falls back to the offline analyst."""
    import httpx
    from app import ai_assistant
    seen = {}

    class Resp:
        def __init__(self, code):
            self.status_code, self.text = code, "boom"

        def json(self):
            return {"choices": [{"message": {"content": "DeepSeek says hi `status`"}}]}

    code = {"v": 200}

    async def fake_post(self, url, headers=None, json=None):
        seen.update(url=url, auth=headers.get("Authorization"), model=json["model"])
        return Resp(code["v"])

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    fresh.put("/api/ai/settings", json={"provider": "deepseek", "api_key": "sk-test-123456789", "model": ""})
    try:
        r = fresh.post("/api/ai/chat", json={"message": "what is wrong?"}).json()
        assert r["source"] == "deepseek" and "DeepSeek says hi" in r["answer"] and "status" in r["commands"]
        assert seen == {"url": "https://api.deepseek.com/chat/completions",
                        "auth": "Bearer sk-test-123456789", "model": "deepseek-chat"}
        code["v"] = 401
        r = fresh.post("/api/ai/chat", json={"message": "what is wrong?"}).json()
        assert r["source"] == "offline" and "Offline analyst answered" in r["answer"]
        assert "sk-test-123456789" not in r["answer"]
    finally:
        fresh.put("/api/ai/settings", json={"provider": "deepseek", "api_key": ""})


def test_deepseek_api_key_env(monkeypatch):
    from app import config
    try:
        monkeypatch.delenv("AI_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-key")
        assert importlib.reload(config).AI_API_KEY == "sk-env-key"
    finally:
        monkeypatch.delenv("DEEPSEEK_API_KEY")
        importlib.reload(config)
