"""
Shapes of incoming data, checked with Pydantic.

Every reading - from the built-in simulator now, from MQTT in Phase 3, from
the ESP32 in Phase 11 - must match TelemetryIn before it is stored.
Bad messages are rejected instead of corrupting the database.
"""
from pydantic import BaseModel, Field


class TelemetryIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=32)
    temperature: float = Field(ge=-100, le=150)  # physically possible range only
    humidity: float = Field(ge=0, le=100)
    battery: float = Field(ge=0, le=100)
    source: str = "simulator"
    motion: bool | None = None  # v1.1: PIR motion sensor (true = movement detected), optional
