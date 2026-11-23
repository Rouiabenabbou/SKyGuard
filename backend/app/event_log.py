"""
Records events in the network_events table and pushes them to the dashboard.

Every important change (simulation started, device came online, later:
alerts, quarantine, link failure) goes through log_event(), which builds
the history used by the 4D timeline in Phase 9.

Since Phase 3 every event is also published on the MQTT topic
cybershield/network/events, so any MQTT client can follow what happens.
"""
from sqlalchemy.orm import Session

from app.models import NetworkEvent
from app.websocket_manager import manager


async def log_event(
    db: Session,
    event_type: str,
    description: str,
    category: str = "system",
    device_id: str | None = None,
    session_id: int | None = None,
) -> NetworkEvent:
    event = NetworkEvent(
        event_type=event_type,
        category=category,
        description=description,
        device_id=device_id,
        session_id=session_id,
    )
    db.add(event)
    db.commit()
    await manager.broadcast("event", event.to_dict())

    from app import mqtt_topics  # imported here to avoid a circular import
    from app.mqtt_client import mqtt_service

    mqtt_service.publish(mqtt_topics.NETWORK_EVENTS, event.to_dict())
    return event
