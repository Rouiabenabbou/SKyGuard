"""
Keeps track of every browser connected over WebSocket and lets the rest of
the backend broadcast a message to all of them.

In later phases this is how live telemetry, alerts and network changes reach
the dashboard. In Phase 1 it only carries a heartbeat.
"""
import json
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self.company: dict[WebSocket, str] = {}  # v1.2: socket -> company of the logged-in user

    async def connect(self, websocket: WebSocket, company_id: str | None = None) -> None:
        await websocket.accept()
        self.active.add(websocket)
        if company_id:
            self.company[websocket] = company_id

    def disconnect(self, websocket: WebSocket) -> None:
        self.active.discard(websocket)
        self.company.pop(websocket, None)

    @property
    def client_count(self) -> int:
        return len(self.active)

    async def send(self, websocket: WebSocket, message_type: str, data: Any) -> None:
        await websocket.send_text(json.dumps({"type": message_type, "data": data}))

    async def broadcast(self, message_type: str, data: Any) -> None:
        """Send one message to every connected client. Dead sockets are dropped.
        v1.2: a company user's browser gets the message without other companies'
        devices, or not at all if it is only about such a device."""
        from app import tenancy

        payload = json.dumps({"type": message_type, "data": data})
        per_company: dict[str, str | None] = {}
        dead = []
        for ws in list(self.active):
            text = payload
            cid = self.company.get(ws)
            if cid:
                if cid not in per_company:
                    hidden = tenancy.hidden_for(cid)
                    per_company[cid] = (None if tenancy.message_is_hidden(data, hidden) else
                                        json.dumps({"type": message_type, "data": tenancy.scrub(data, hidden)}))
                text = per_company[cid]
                if text is None:
                    continue
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# One shared instance for the whole app.
manager = WebSocketManager()
