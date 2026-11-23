# Architecture — CyberShield SatCom 3D

## 1. Layers

| Layer | Components | Responsibility |
|---|---|---|
| Device layer | Built-in simulator, `mqtt_simulator.py`, `esp32_emulator.py`, real ESP32 + DHT22 | Produce readings and status messages |
| Transport layer | Mosquitto MQTT broker | Publish/subscribe between devices and backend |
| Application layer | FastAPI backend | Validate, store, detect, isolate, simulate the network, record history |
| Data layer | SQLite (SQLAlchemy ORM) | 11 tables: devices, readings, alerts, quarantine, topology, metrics, failover, snapshots, events, sessions |
| Presentation layer | React dashboard, Three.js twin, Recharts | Live monitoring, 3D/4D visualisation, control, reports |

## 2. Data flow of one reading

```
device ──MQTT──► mqtt_client.handle_message()
                   ├─ topic/payload checks (spoofing, malformed)
                   ▼
          telemetry_service.ingest_telemetry()
                   ├─ Rule A: message rate
                   ├─ Pydantic validation (TelemetryIn)
                   ├─ registered? (else Rule B: unauthorized)
                   ├─ quarantined? → blocked (counted, not stored)
                   ├─ store Telemetry row, update Device
                   ├─ Rule C: allowed ranges
                   ├─ optional ML check
                   └─ WebSocket "telemetry" → dashboard
```

Every alert goes through `detection_engine.raise_alert()`. It applies the
cooldown, stores the alert, marks the device suspicious, broadcasts it,
publishes it on MQTT, logs an event, and asks `quarantine_service` whether to
auto-quarantine.

## 3. The network loop (every 2 s)

```
simulation_controller._tick()
   └─ network_simulator.tick()
         ├─ new latency / loss / bandwidth per link (+ overrides, rain fade)
         ├─ link status: online / degraded / offline   → events, Rule E alerts
         ├─ for each device: primary path & backup path (BFS to CORE)
         │     └─ failover_service.decide() → primary / switching / backup / down
         ├─ availability
         ├─ timeline_service.record()  → state_snapshots (4D)
         └─ WebSocket "network" snapshot → 2D map, 3D twin, charts
```

## 4. Key design decisions

| Decision | Why |
|---|---|
| One ingest function for every source | Simulated, MQTT and ESP32 data get exactly the same checks |
| MQTT in the middle, with a "direct" fallback | Realistic IoT architecture; the demo still works without a broker |
| Rule-based detection first, ML optional | Rules are explainable and testable; ML adds a second opinion without becoming a black box in charge |
| Logical quarantine (block in backend + command to device) | Shows the full response loop without touching any real network |
| Failover as a small state machine | Easy to explain, test with fixed times, and measure (handover, interruption, lost readings) |
| Full-state snapshots for the timeline | Replay needs no re-simulation; the same 3D scene renders live and past states |
| WebSocket push, REST for actions | Low latency for live data, simple and documented API for commands |
| SQLite | Zero setup for a student project; SQLAlchemy keeps the option to move to PostgreSQL |
| 3D scene lazy-loaded, labels drawn on canvases | Dashboard opens fast; works offline (no font or texture downloads) |

## 5. Main modules

| Module | Phase | Lines of responsibility |
|---|---|---|
| `telemetry_service.py` | 2 | Single entry point for readings |
| `mqtt_client.py` | 3 | Broker connection, subscriptions, topic checks, publish |
| `network_simulator.py` | 4 | Link metrics, failures, routes, availability, snapshot |
| `detection_engine.py` | 5 | Rules A–E, spoofing, malformed, cooldown, alerts |
| `quarantine_service.py` | 6 | Quarantine, release, blocking, auto mode, device command |
| `three/*` (frontend) | 7 | 3D twin |
| `failover_service.py` | 8 | Primary/backup state machine, timing, lost readings |
| `timeline_service.py` | 9 | 4D frames, thinning, pruning |
| `routes/reports.py`, `components/charts/*` | 10 | Exports, report, charts |
| `iot/esp32/*`, `esp32_emulator.py` | 11 | Real device |
| `ml_detector.py`, `tests/*` | 12 | Optional ML, automated tests |
