# Phase 2 — Database and IoT Simulator

**Goal:** store everything in SQLite, simulate three IoT devices with
realistic readings, and show them live on the dashboard.

**Status:** tested end to end (Python 3.13, Node 22). The three devices sent
readings every 5 s. Pause made them go offline after 15 s. Reset cleared the
data and started a new session. No browser errors, and the page fits a phone
screen.

---

## 1. What you are building and why

```
 Built-in simulator ──► telemetry_service ──► SQLite (database/cybershield.db)
   (3 virtual devices)    validate · store          │
                          update device             │
                          log events                ▼
                              │               REST: /api/devices, /api/telemetry, /api/events
                              └──► WebSocket push ──► Dashboard: device cards, table, event log
```

* **Database:** the digital twin needs memory. Every reading, event and
  (later) alert is saved so it can be charted and replayed on the timeline.
* **Simulator:** the project must work without hardware. Each virtual device
  has its own climate (desert, office, farm). Its values follow a slow
  day/night wave plus random noise, and its battery drains and recharges.
* **One entry point for data (`telemetry_service.ingest_telemetry`):** every
  reading is validated, stored, and pushed to browsers by the same function.
  In Phase 3 the MQTT client calls this same function, so nothing else changes.

> All devices and readings are simulated and are labelled that way on the dashboard.

---

## 2. Update your project from Phase 1

1. Stop both servers (press **Ctrl+C** in each terminal).
2. Unzip **CyberShield-SatCom-3D-phase2.zip**. Open the `CyberShield-SatCom-3D`
   folder inside it and copy **everything in it** into your project folder
   (`D:\CyberShield-SatCom-3D-phase1\ResearchCyberShield-SatCom-3D`).
   Choose **Replace** when Windows asks. Your `venv` and `node_modules`
   folders are kept.
3. Delete `frontend\src\components\ComponentList.jsx` (no longer used; harmless if you forget).

New and changed files:

```
backend/
├── requirements.txt               CHANGED  adds sqlalchemy
└── app/
    ├── config.py                  CHANGED  database path, simulator settings
    ├── main.py                    CHANGED  creates DB + starts simulator at startup
    ├── database.py                NEW      SQLite connection, init_db()
    ├── models.py                  NEW      the 7 database tables
    ├── seed.py                    NEW      the 3 registered (authorized) devices
    ├── schemas.py                 NEW      checks every reading is valid
    ├── telemetry_service.py       NEW      validate → store → update → push
    ├── event_log.py               NEW      records events (for the 4D timeline)
    ├── device_simulator.py        NEW      realistic sensor values
    ├── simulation_controller.py   NEW      start / pause / reset + background loop
    └── routes/
        ├── system.py              CHANGED  phase number, component status
        ├── devices.py             NEW      /api/devices, /api/telemetry, /api/events
        └── simulation.py          NEW      /api/simulation/start|pause|reset|status
frontend/src/
├── App.jsx                        CHANGED  new dashboard layout
├── services/api.js                CHANGED  new API calls
├── hooks/useBackendSocket.js      CHANGED  passes every message on; no more proxy warning on load
├── hooks/useLiveData.js           NEW      loads data once, then keeps it live
├── hooks/useNow.js                NEW      "last seen 3s ago" clock
├── components/Header.jsx          CHANGED  shows latency in the pill
├── components/SimulationControls.jsx NEW   Start / Pause / Reset buttons
├── components/DeviceCard.jsx      NEW      one card per device
├── components/Sparkline.jsx       NEW      tiny SVG temperature chart
├── components/TelemetryTable.jsx  NEW      latest readings
├── components/EventLog.jsx        NEW      what happened, newest first
└── styles/global.css              CHANGED  styles for the above
```

---

## 3. Install and run

**Terminal 1 (backend):**

```
cd backend
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

On macOS/Linux, activate with `source venv/bin/activate`.

The first time, this creates the file `database\cybershield.db` automatically.
You should see `[startup] CyberShield SatCom 3D v0.2.0 ready`.

**Terminal 2 (frontend):**

```
cd frontend
npm run dev
```

(No `npm install` is needed: Phase 2 adds no new npm packages.)

Open **http://localhost:5173**.

---

## 4. The database tables

| Table | What it stores | Used from |
|---|---|---|
| `devices` | Each registered device and its latest values, status, message count, allowed ranges | Phase 2 |
| `telemetry` | Every sensor reading (device, temp, humidity, battery, source, time) | Phase 2 |
| `network_events` | Everything that happened, in time order | Phase 2 (timeline in 9) |
| `simulation_sessions` | Each run from Start/Reset until the next Reset | Phase 2 |
| `security_alerts` | Cybersecurity alerts | Phase 5 |
| `network_nodes` | Satellite, ground station, 5G tower, core, security server | Phase 4 |
| `network_links` | Links between nodes with latency, packet loss, bandwidth | Phase 4 |

**To look inside the database:** install the VS Code extension **"SQLite Viewer"**
(by Florian Klampfer), then click `database/cybershield.db`. Or use the free
**DB Browser for SQLite** (https://sqlitebrowser.org).

**The three devices:**

| ID | Name | Type | Link | Typical climate |
|---|---|---|---|---|
| IOT-001 | Remote Sensor 01 | Environmental | Satellite | Desert: ~34 °C, ~22 % |
| IOT-002 | Smart Building 02 | Smart Building | 5G | Office: ~23 °C, ~45 % |
| IOT-003 | Agri Field 03 | Agricultural | Satellite | Farm: ~19 °C, ~68 % |

---

## 5. New API endpoints

| Method | URL | Returns |
|---|---|---|
| GET | `/api/devices` | All devices with latest values |
| GET | `/api/devices/IOT-001` | One device + its last 20 readings (404 if unknown) |
| GET | `/api/telemetry?limit=50&device_id=IOT-001` | Recent readings, newest first |
| GET | `/api/events?limit=50` | Recent events, newest first |
| GET | `/api/simulation/status` | Running or paused, session number |
| POST | `/api/simulation/start` | Starts or resumes |
| POST | `/api/simulation/pause` | Pauses (devices go offline after 15 s) |
| POST | `/api/simulation/reset` | Clears readings and events, starts a new session |

You can try all of them at **http://127.0.0.1:8000/docs**: click an
endpoint, then **Try it out**, then **Execute**.

New WebSocket message types: `telemetry`, `device`, `event`, `simulation`, `reset`.

---

## 6. Test Phase 2

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | DB auto-created | Start backend, look in `database/` | `cybershield.db` exists |
| 2 | Devices listed | Open http://127.0.0.1:8000/api/devices | `"count": 3` and three devices |
| 3 | Live readings | Watch the dashboard for 15 s | All 3 cards **Online**, values and message counts change every ~5 s |
| 4 | Trend chart | Wait about 1 minute | The blue line on each card fills up |
| 5 | Telemetry table | Look at "Live telemetry" | New row at the top every ~1–2 s |
| 6 | Pause | Click **Pause** | Readings stop; after ~15 s all cards turn **Offline** (faded); "stopped responding" events appear |
| 7 | Start | Click **Start** | Cards come back **Online**; "resumed" and "connected" events |
| 8 | Reset | Click **Reset** | Message count goes back to ~0, table and events clear, new session number |
| 9 | Data is saved | Stop the backend, start it again | Old readings still in `/api/telemetry` (until you press Reset) |
| 10 | Bad request | Open http://127.0.0.1:8000/api/devices/XYZ | `{"detail": "Device 'XYZ' not found"}` |

If all 10 pass, Phase 2 is done.

---

## 7. Settings you can change

Add these lines to a `.env` file in the project root (copy `.env.example`):

| Setting | Default | Meaning |
|---|---|---|
| `SIM_INTERVAL` | 5 | Seconds between readings per device |
| `SIM_AUTOSTART` | true | Start the simulator when the backend starts |
| `OFFLINE_AFTER` | 15 | Seconds of silence before a device is "offline" |

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'sqlalchemy'` | Venv not active, or you skipped `pip install -r requirements.txt` |
| Cards show "—" and stay Offline | Simulation is paused: click **Start** |
| `sqlite3.OperationalError: no such column` | You have an old database from your own experiments. Stop the backend, delete `database\cybershield.db`, start again |
| `database is locked` | Close DB Browser / the SQLite viewer tab, then try again |
| Page looks like Phase 1 still | Files weren't replaced. Check that `frontend\src\components\DeviceCard.jsx` exists, then refresh the browser (Ctrl+F5) |
| Red banner "Cannot reach the backend" | Backend isn't running, or crashed. Read the error in Terminal 1 |

---

## Next: Phase 3 — MQTT integration

Install Mosquitto. The simulator becomes a separate program that publishes
readings over MQTT (`cybershield/iot/<id>/telemetry`). The backend subscribes
and sends every message through the same `ingest_telemetry` function.
