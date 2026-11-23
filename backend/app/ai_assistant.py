"""
AI security assistant (v1.1).

It reads the live state of the digital twin (devices, alerts, routes, failover,
quarantine, events) and helps the operator:

* chat:          answer questions such as "what is wrong right now?"
* explain alert: what an alert means, the likely cause and what to do
* report:        a short incident report of the current session

v2.6: the default AI is DeepSeek (api.deepseek.com, OpenAI-compatible API, key in
DEEPSEEK_API_KEY). Huawei Cloud MaaS (v2.5) and the older providers (Gemini, Groq,
OpenRouter, OmniRoute) still work from .env. Without a key,
or when the provider can't be reached, a built-in offline analyst answers from
rules, so the feature always works in a demo.

The assistant only ADVISES. It never changes anything by itself: it can suggest
console commands, and the operator decides whether to run them.
"""
import json
import re

import httpx
from sqlalchemy.orm import Session

from app import config
from app.models import Device, DeviceProfile, NetworkEvent, QuarantineRecord, SecurityAlert

PROVIDERS = {
    # v2.6: DeepSeek's own API (platform.deepseek.com -> API keys). OpenAI-compatible.
    "deepseek": (config.DEEPSEEK_URL, config.DEEPSEEK_MODEL),
    # v2.5: Huawei Cloud ModelArts Studio (MaaS). Address and model name come from the
    # MaaS console (Model Inference -> API call description), saved in the dashboard or .env.
    "huawei": (None, config.HUAWEI_MAAS_MODEL),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "meta-llama/llama-3.3-70b-instruct:free"),
    # v1.5: OmniRoute (github.com/cheaper-inference/OmniRoute) is a free gateway you run yourself.
    # It forwards to free tiers of many providers (you still connect your own free accounts in it).
    # Any other OpenAI-compatible server (Ollama, LM Studio...) works the same way with its own address.
    "omniroute": (None, "auto"),
}
KEY_OPTIONAL = {"omniroute"}  # a local gateway may not need a key
NEEDS_URL = {"omniroute", "huawei"}  # address set by the user
NAMES = {"deepseek": "DeepSeek", "huawei": "Huawei Cloud MaaS"}


def base_url(provider: str | None = None) -> str:
    """API address saved in the dashboard, else HUAWEI_MAAS_URL / OMNIROUTE_URL in .env."""
    from app.database import SessionLocal
    from app.models import AppFlag

    try:
        with SessionLocal() as db:
            row = db.get(AppFlag, "ai_base_url")
            if row is not None and row.value:
                return row.value
    except Exception:
        pass
    if (provider or active()["provider"]) == "huawei":
        return config.HUAWEI_MAAS_URL
    return config.OMNIROUTE_URL


def endpoint(provider: str) -> str:
    url = PROVIDERS[provider][0]
    if url:
        return url
    b = base_url(provider).rstrip("/")
    return b if b.endswith("/chat/completions") else b + "/chat/completions"

# Console commands the assistant may suggest (the dashboard shows a Run button for them).
COMMAND_RE = re.compile(
    r"`((?:status|devices|device|alerts|events|routes|links|nodes|quarantine|release|resolve|fix|failover|"
    r"node|link|config|identify|ping|export|autoquarantine)(?: [^`\n]{0,60})?)`")

SYSTEM_PROMPT = """You are the AI security analyst inside "CyberShield SatCom 3D", a university project:
a 4D digital twin of a SIMULATED satellite-5G IoT network. All devices, attacks, quarantine,
handover and the 5G core are simulated on one computer; never claim they are real.

You get the current state as JSON. Answer the operator's question using only that state.
Be short and practical (at most about 150 words), use simple English and bullet points.
When you recommend an action, write the exact console command in backticks, chosen from:
`status`, `alerts`, `routes`, `device <ID>`, `quarantine <ID>`, `release <ID>`, `resolve <alert-id>`,
`fix <ID>`, `fix network`, `node <NODE> auto`, `link <LINK> auto`, `failover drill 30`,
`config <ID> temp <min> <max>`, `export alerts`.
The operator decides whether to run them; you never act yourself."""


# ------------------------------------------------------------------ state
def build_context(db: Session) -> dict:
    from app.failover_service import failover
    from app.motion_service import motion
    from app.network_simulator import network

    profiles = {p.node_id: p for p in db.query(DeviceProfile).all()}
    devices = []
    for d in db.query(Device).order_by(Device.device_id):
        p = profiles.get(d.device_id)
        row = {"id": d.device_id, "name": d.device_name, "type": d.device_type, "status": d.status,
               "security": d.security_status, "temperature": d.temperature, "humidity": d.humidity,
               "battery": d.battery, "allowed_temperature": [d.temp_min, d.temp_max],
               "allowed_humidity": [d.humidity_min, d.humidity_max], "connection": d.connection_type,
               "place": (p.address or p.place_type) if p else d.location}
        if p and p.has_motion:
            row["motion"] = motion.state(db, d.device_id)
        devices.append(row)
    alerts = (db.query(SecurityAlert).filter(SecurityAlert.status == "open")
              .order_by(SecurityAlert.id.desc()).limit(15).all())
    snap = network.latest or {}
    routes = {k: {"mode": r.get("mode"), "connected": r.get("connected"), "path": r.get("path"),
                  "latency_ms": r.get("latency_ms")} for k, r in snap.get("routes", {}).items()}
    bad_links = [{"id": l["link_id"], "status": l["status"]} for l in snap.get("links", []) if l["status"] != "online"]
    bad_nodes = [{"id": n["node_id"], "status": n["status"]} for n in snap.get("nodes", [])
                 if n["node_type"] != "iot_device" and n["status"] != "online"]
    quarantined = [q.to_dict() for q in db.query(QuarantineRecord).filter(QuarantineRecord.released_at.is_(None))]
    events = db.query(NetworkEvent).order_by(NetworkEvent.id.desc()).limit(10).all()
    context = {
        "devices": devices,
        "open_alerts": [{"id": a.id, "type": a.alert_type, "severity": a.severity, "device": a.device_id,
                         "description": a.description, "time": a.to_dict()["timestamp"]} for a in alerts],
        "availability_percent": snap.get("availability", {}).get("current"),
        "routes": routes,
        "links_not_online": bad_links,
        "nodes_not_online": bad_nodes,
        "failover": {"enabled": failover.enabled, **failover.summary(db).get("stats", {})},
        "quarantined": [{"device": q["device_id"], "reason": q["reason"]} for q in quarantined],
        "recent_events": [e.description for e in events],
    }
    # v1.2: a company user's assistant only knows that company's devices.
    from app import tenancy
    return tenancy.scrub(context, tenancy.current_hidden())


# ----------------------------------------------------- offline analyst
ALERT_GUIDE = {
    "excessive_message_rate": ("The device sends far more messages than normal (Rule A).",
                               "a flooding / DoS attempt or a stuck firmware loop",
                               ["quarantine {d}", "device {d}", "release {d}"]),
    "unauthorized_device": ("An unknown device ID tried to send data (Rule B).",
                            "a rogue or cloned device trying to join the network",
                            ["alerts", "export alerts"]),
    "abnormal_sensor_value": ("A reading is outside the allowed range for this device (Rule C).",
                              "a faulty sensor, a real environmental problem or injected false data",
                              ["device {d}", "config {d} temp <min> <max>", "fix {d}"]),
    "suspicious_connections": ("The device reconnected many times in a short time (Rule D).",
                               "a connection storm, credential guessing or an unstable link",
                               ["quarantine {d}", "routes"]),
    "device_id_spoofing": ("Two sources use the same device ID.",
                           "an attacker cloning a registered device",
                           ["quarantine {d}", "device {d}"]),
    "link_failure": ("A network link is offline or badly degraded (Rule E).",
                     "rain fade, equipment failure or a simulated outage",
                     ["routes", "failover drill 30", "fix network"]),
    "node_failure": ("A network node (satellite, ground station, tower) is down (Rule E).",
                     "equipment failure or a simulated outage",
                     ["routes", "fix network"]),
    "ml_anomaly": ("The machine-learning detector says the reading doesn't match the learned normal pattern.",
                   "an unusual combination of values, even inside the allowed ranges",
                   ["device {d}", "resolve {a}"]),
    "movement_detected": ("The motion sensor saw movement at night (Rule F).",
                          "an intruder, or animals escaping from the farm",
                          ["device {d}", "resolve {a}"]),
}


def _cmds(templates, alert) -> list[str]:
    out = []
    for t in templates:
        if "{d}" in t and not alert.get("device"):
            continue
        out.append(t.format(d=alert.get("device") or "", a=alert.get("id")))
    return out


def offline_explain(alert: dict) -> str:
    what, cause, cmds = ALERT_GUIDE.get(alert["type"], ("A security alert was raised.", "unknown", ["alerts"]))
    lines = [f"**Alert #{alert['id']} · {alert['type'].replace('_', ' ')} · {alert['severity']}**",
             f"- What it means: {what}", f"- Likely cause: {cause}.", "- What to do:"]
    lines += [f"  - `{c}`" for c in _cmds(cmds, alert)]
    return "\n".join(lines)


def offline_answer(question: str, ctx: dict) -> str:
    q = question.lower()
    alerts = ctx["open_alerts"]
    for a in alerts:  # "explain alert 12"
        if re.search(rf"\b#?{a['id']}\b", q) and "alert" in q:
            return offline_explain(a)
    for d in ctx["devices"]:
        if d["id"].lower() in q:
            lines = [f"**{d['id']} · {d['name']}** ({d['place']})",
                     f"- status {d['status']}, security {d['security']}",
                     f"- {d['temperature']} °C (allowed {d['allowed_temperature'][0]} to {d['allowed_temperature'][1]}), "
                     f"{d['humidity']} % humidity, battery {d['battery']} %"]
            if "motion" in d:
                lines.append(f"- motion now: {'yes' if d['motion']['motion_now'] else 'no'}, "
                             f"{d['motion']['motion_24h']} movements in 24 h")
            mine = [a for a in alerts if a["device"] == d["id"]]
            lines.append(f"- {len(mine)} open alert(s)" + (f": {', '.join(a['type'] for a in mine)}" if mine else ""))
            if d["security"] != "normal":
                lines.append(f"- Suggested: `device {d['id']}` then `fix {d['id']}` once you are sure it is safe")
            return "\n".join(lines)
    # general situation report
    crit = [a for a in alerts if a["severity"] in ("critical", "high")]
    lines = ["**Situation now (offline analyst):**",
             f"- Network availability: {ctx['availability_percent']} %",
             f"- Open alerts: {len(alerts)} ({len(crit)} high/critical)"]
    if ctx["quarantined"]:
        lines.append("- Quarantined: " + ", ".join(f"{q['device']} ({q['reason']})" for q in ctx["quarantined"]))
    if ctx["nodes_not_online"] or ctx["links_not_online"]:
        lines.append("- Network problems: " + ", ".join(f"{x['id']} {x['status']}"
                                                         for x in ctx["nodes_not_online"] + ctx["links_not_online"]))
    backup = [k for k, r in ctx["routes"].items() if r["mode"] == "backup"]
    if backup:
        lines.append(f"- On backup 5G after failover: {', '.join(backup)}")
    if crit:
        lines.append("**Most urgent:**")
        for a in crit[:3]:
            lines.append(f"- #{a['id']} {a['type'].replace('_', ' ')} on {a['device'] or 'network'}: "
                         + ", ".join(f"`{c}`" for c in _cmds(ALERT_GUIDE.get(a["type"], ("", "", ["alerts"]))[2], a)[:2]))
    elif not alerts:
        lines.append("- Everything looks normal. Try a drill: `failover drill 30`")
    lines.append("Free-form answers: add a DeepSeek API key in **Admin → AI assistant**.")
    return "\n".join(lines)


def offline_report(ctx: dict) -> str:
    alerts = ctx["open_alerts"]
    by_type: dict[str, int] = {}
    for a in alerts:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
    lines = ["**Incident report (offline analyst)**",
             f"- Devices: {len(ctx['devices'])}, online "
             f"{sum(1 for d in ctx['devices'] if d['status'] == 'online')}",
             f"- Availability now: {ctx['availability_percent']} %",
             f"- Open alerts: {len(alerts)}" + (" (" + ", ".join(f"{k.replace('_', ' ')} ×{v}"
                                                               for k, v in by_type.items()) + ")" if by_type else ""),
             f"- Failovers: {ctx['failover'].get('failovers', 0)}, readings lost: {ctx['failover'].get('readings_lost', 0)}",
             f"- Quarantined now: {', '.join(q['device'] for q in ctx['quarantined']) or 'none'}",
             "**Recommendations:**"]
    if by_type:
        for t in by_type:
            lines.append(f"- {t.replace('_', ' ')}: {ALERT_GUIDE.get(t, ('', 'check the alert', []))[1]}")
    else:
        lines.append("- No open incidents. Keep auto-quarantine and failover on.")
    return "\n".join(lines)


# ------------------------------------------------------------- the LLM
def active() -> dict:
    """The AI key in use: the one saved in the dashboard (Admin -> AI assistant), else the one in .env."""
    from app.database import SessionLocal
    from app.models import AiSettings

    try:
        with SessionLocal() as db:
            row = db.get(AiSettings, 1)
            if row is not None and (row.api_key or row.provider in KEY_OPTIONAL):
                return {"provider": row.provider, "key": row.api_key, "model": row.model or None, "from": "dashboard"}
    except Exception:
        pass
    return {"provider": config.AI_PROVIDER, "key": config.AI_API_KEY, "model": config.AI_MODEL,
            "from": ".env" if config.AI_API_KEY else None}


def is_configured() -> bool:
    a = active()
    return a["provider"] in PROVIDERS and (bool(a["key"]) or a["provider"] in KEY_OPTIONAL)


def status() -> dict:
    a = active()
    url, default_model = PROVIDERS.get(a["provider"], PROVIDERS["deepseek"])
    on = is_configured()
    return {"provider": a["provider"] if on else "offline", "configured": on,
            "model": (a["model"] or default_model) if on else "built-in rules",
            "key_from": a["from"], "supported": list(PROVIDERS),
            "provider_name": NAMES.get(a["provider"], a["provider"]) if on else "offline",
            "base_url": base_url(a["provider"]) if a["provider"] in NEEDS_URL else None}


async def ask_llm(messages: list[dict], settings: dict | None = None) -> str:
    a = settings or active()
    default_model = PROVIDERS[a["provider"]][1]
    url = endpoint(a["provider"])
    headers = {"Content-Type": "application/json"}
    if a["key"]:
        headers["Authorization"] = f"Bearer {a['key']}"
    if a["provider"] == "openrouter":
        headers["X-Title"] = "CyberShield SatCom 3D"
    body = {"model": a["model"] or default_model, "messages": messages, "temperature": 0.3, "max_tokens": 600}
    async with httpx.AsyncClient(timeout=config.AI_TIMEOUT) as client:
        r = await client.post(url, headers=headers, json=body)
    if r.status_code != 200:
        text = r.text[:200].replace(a["key"], "***") if a["key"] else r.text[:200]
        raise RuntimeError(f"{a['provider']} answered HTTP {r.status_code}: {text}")
    return r.json()["choices"][0]["message"]["content"].strip()


async def answer(db: Session, question: str, history: list[dict] | None = None, task: str = "chat") -> dict:
    ctx = build_context(db)
    if is_configured():
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "system", "content": "Current state:\n" + json.dumps(ctx, default=str)[:12000]}]
        for h in (history or [])[-6:]:
            if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
                messages.append({"role": h["role"], "content": h["content"][:2000]})
        messages.append({"role": "user", "content": question})
        try:
            text = await ask_llm(messages)
            return {"answer": text, "source": active()["provider"], "commands": commands_in(text)}
        except Exception as exc:  # network down, bad key, quota: fall back
            fallback = _offline(task, question, ctx)
            return {"answer": fallback + f"\n\n*(AI provider unavailable: {str(exc)[:120]}. Offline analyst answered.)*",
                    "source": "offline", "commands": commands_in(fallback)}
    text = _offline(task, question, ctx)
    return {"answer": text, "source": "offline", "commands": commands_in(text)}


def _offline(task: str, question: str, ctx: dict) -> str:
    if task == "report":
        return offline_report(ctx)
    if task.startswith("explain:"):
        alert_id = int(task.split(":")[1])
        alert = next((a for a in ctx["open_alerts"] if a["id"] == alert_id), None)
        if alert:
            return offline_explain(alert)
    return offline_answer(question, ctx)


def commands_in(text: str) -> list[str]:
    seen = []
    for c in COMMAND_RE.findall(text):
        if "<" not in c and c not in seen:
            seen.append(c)
    return seen[:6]
