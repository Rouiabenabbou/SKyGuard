"""
Built-in IoT device simulator.

Generates realistic readings for each registered device so the project works
with no hardware at all:

* temperature and humidity follow a slow wave (like day and night) plus small
  random noise, and humidity moves opposite to temperature
* each device type has its own typical climate
* battery drains slowly and "recharges" when it gets low (solar panel)

Since Phase 3 its readings travel through the MQTT broker when it is running
(see simulation_controller.py). iot/simulator/mqtt_simulator.py is a separate
program with the same idea plus attack and failure scenarios.
"""
import math
import random
import time

# Typical climate per device: average value and how far the wave swings.
PROFILES = {
    "IOT-001": {"temp": 34.0, "temp_swing": 6.0, "hum": 22.0, "hum_swing": 8.0, "drain": 0.05},
    "IOT-002": {"temp": 23.0, "temp_swing": 1.5, "hum": 45.0, "hum_swing": 5.0, "drain": 0.02},
    "IOT-003": {"temp": 19.0, "temp_swing": 5.0, "hum": 68.0, "hum_swing": 12.0, "drain": 0.04},
}
DEFAULT_PROFILE = {"temp": 25.0, "temp_swing": 3.0, "hum": 50.0, "hum_swing": 8.0, "drain": 0.03}

# One full "day" of the wave lasts this many real seconds, so changes are visible in a demo.
CYCLE_SECONDS = 300


class SimulatedDevice:
    def __init__(self, device_id: str, battery: float | None = None):
        self.device_id = device_id
        self.profile = PROFILES.get(device_id, DEFAULT_PROFILE)
        self.battery = battery if battery is not None else random.uniform(75, 100)
        self.phase = random.uniform(0, 2 * math.pi)  # so devices don't move in sync
        self.has_motion = False  # v1.1: simulated PIR motion sensor
        self.motion_state: dict = {}

    def read(self) -> dict:
        p = self.profile
        wave = math.sin(2 * math.pi * time.time() / CYCLE_SECONDS + self.phase)

        temperature = p["temp"] + p["temp_swing"] * wave + random.gauss(0, 0.3)
        humidity = p["hum"] - p["hum_swing"] * wave + random.gauss(0, 0.8)
        humidity = max(0.0, min(100.0, humidity))

        self.battery -= p["drain"] * random.uniform(0.5, 1.5)
        if self.battery < 20:  # solar recharge
            self.battery = random.uniform(90, 100)

        reading = {
            "device_id": self.device_id,
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "battery": round(self.battery, 1),
            "source": "builtin",
        }
        if self.has_motion:
            from app.motion_service import MotionService
            reading["motion"] = MotionService.simulated_motion(self.motion_state)
        return reading
