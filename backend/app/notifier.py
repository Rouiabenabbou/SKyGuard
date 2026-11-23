"""
Phone alarm (v1.2): when a serious alert is raised, send a push notification
to the operator's phone so it rings even when the dashboard is closed.

Two free channels (both optional, both can be on):
* ntfy  - free app for Android and iPhone (https://ntfy.sh). No account needed:
          the phone subscribes to a topic name and gets a loud "urgent" alarm.
          The topic name works like a password, so make it long and secret.
* Telegram - a message from your own Telegram bot.

Only the alert text of the SIMULATED system is sent (type, severity, device,
description). Sending happens in the background, so a slow or missing internet
connection never slows down detection.
"""
import asyncio

import httpx
from sqlalchemy.orm import Session

from app import config
from app.models import NotifySettings, SecurityAlert

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
# Network faults (a link or node going down) are not attacks: they are shown on the
# dashboard and handled by failover, but they don't ring the phone.
NOT_ATTACKS = {"link_failure", "node_failure", "malformed_message"}
EMOJI = {"low": "ℹ️", "medium": "⚠️", "high": "🚨", "critical": "🚨🚨"}


def get_settings(db: Session) -> NotifySettings:
    s = db.get(NotifySettings, 1)
    if s is None:  # first use: start from the .env values
        s = NotifySettings(id=1, enabled=config.NOTIFY_ENABLED, ntfy_server=config.NTFY_SERVER,
                           ntfy_topic=config.NTFY_TOPIC, min_severity=config.NOTIFY_MIN_SEVERITY,
                           telegram_token=config.TELEGRAM_BOT_TOKEN, telegram_chat_id=config.TELEGRAM_CHAT_ID)
        db.add(s)
        db.commit()
    return s


def public_settings(s: NotifySettings) -> dict:
    """Settings for the dashboard. The Telegram token is never sent back, only whether it is set."""
    return {"enabled": s.enabled, "ntfy_server": s.ntfy_server, "ntfy_topic": s.ntfy_topic,
            "min_severity": s.min_severity, "telegram_chat_id": s.telegram_chat_id,
            "telegram_token_set": bool(s.telegram_token)}


def message_for(alert: dict) -> tuple[str, str]:
    sev = alert.get("severity", "high")
    title = f"{EMOJI.get(sev, '🚨')} CyberShield: {sev.upper()} {alert.get('alert_type', 'alert').replace('_', ' ')}"
    body = (f"{alert.get('description', '')}\nDevice: {alert.get('device_id') or '-'} · alert #{alert.get('id', '-')}"
            "\n(simulated system)")
    return title, body


class Notifier:
    def __init__(self) -> None:
        self.last_result: dict = {"sent": 0, "failed": 0, "last_error": None, "last_sent_at": None}
        self._tasks: set[asyncio.Task] = set()

    @staticmethod
    def has_channel(s: NotifySettings) -> bool:
        return bool(s.ntfy_topic) or bool(s.telegram_token and s.telegram_chat_id)

    def wants(self, s: NotifySettings, severity: str, alert_type: str = "") -> bool:
        if alert_type in NOT_ATTACKS:
            return False
        return s.enabled and self.has_channel(s) and SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(s.min_severity, 2)

    def alert(self, db: Session, alert: SecurityAlert) -> None:
        """Called by the detection engine for every new alert: sends it automatically, in the
        background, when it is an attack at or above the chosen severity (no button needed)."""
        s = get_settings(db)
        if not self.wants(s, alert.severity, alert.alert_type):
            return
        from app.routes.engineering import in_maintenance
        if in_maintenance(db, alert.device_id):  # an engineer is working on it: no phone alarm
            return
        snapshot = public_settings(s) | {"telegram_token": s.telegram_token}
        task = asyncio.get_running_loop().create_task(self.send(snapshot, alert.to_dict()))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def send(self, s: dict, alert: dict) -> list[dict]:
        """Send one alert to every configured channel. Returns one result per channel."""
        from app.models import utcnow, iso

        title, body = message_for(alert)
        urgent = alert.get("severity") in ("high", "critical")
        results = []
        async with httpx.AsyncClient(timeout=10) as client:
            if s.get("ntfy_topic"):
                try:
                    r = await client.post(s.get("ntfy_server") or "https://ntfy.sh", json={
                        "topic": s["ntfy_topic"], "title": title, "message": body,
                        "priority": 5 if urgent else 3, "tags": ["rotating_light" if urgent else "warning", "shield"]})
                    r.raise_for_status()
                    results.append({"channel": "ntfy", "ok": True})
                except Exception as exc:
                    results.append({"channel": "ntfy", "ok": False, "error": str(exc)[:160]})
            if s.get("telegram_token") and s.get("telegram_chat_id"):
                try:
                    r = await client.post(f"https://api.telegram.org/bot{s['telegram_token']}/sendMessage",
                                          json={"chat_id": s["telegram_chat_id"], "text": f"{title}\n{body}"})
                    r.raise_for_status()
                    results.append({"channel": "telegram", "ok": True})
                except Exception as exc:
                    # never log the token (it is part of the URL)
                    results.append({"channel": "telegram", "ok": False,
                                    "error": str(exc).replace(s["telegram_token"], "***")[:160]})
        for res in results:
            if res["ok"]:
                self.last_result["sent"] += 1
                self.last_result["last_sent_at"] = iso(utcnow())
            else:
                self.last_result["failed"] += 1
                self.last_result["last_error"] = f"{res['channel']}: {res['error']}"
        return results


notifier = Notifier()
