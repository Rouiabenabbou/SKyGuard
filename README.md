# Cybersheild

**AI that guards IoT devices across satellite and 5G links.**

 the CyberShield SOC project: an MQTT security operations platform with explainable rules, link-aware flood detection, learned anomaly detectors, an AI analyst, and a 3D dashboard. All satellite and 5G links in the experiments are emulated; no real satellite or 5G system was used.

- `experiments/` holds the scripts and result files of experiments X1-X5 (link-aware detection, anomaly detectors under drift, failover, link emulation, scalability) and the backend patch (`backend-patch-v2.8`).
- Secrets are never committed: copy `.env.example` to `.env` and `iot/esp32/cybershield_esp32/config.example.h` to `config.h`, then fill in your own values.

---

# CyberShield SatCom 3D

**A 4D Digital Twin for Cybersecurity and Resilience in Satellite–5G IoT Networks**

> **Headline (v2.2):** CyberShield SOC is an AI security operations center for satellite-5G IoT networks.
> It detects attacks, has an AI analyst explain them with cited evidence, and isolates a device only after
> a human approves. It runs on Huawei Cloud (ECS + RDS), takes real devices through Huawei IoTDA, and uses an
> anomaly model trained on ModelArts with MindSpore. Competition guide: `docs/HUAWEI_INNOVATION.md`.

University IoT final project (v1.2: all 12 phases plus login, secure MQTT, motion sensors, real map, an AI assistant, and many companies on one system). CyberShield
SatCom 3D monitors a **simulated satellite–5G telecom network** that carries
data from IoT sensors. It detects cyberattacks and network failures, isolates
compromised devices, and switches traffic from satellite to 5G when the
satellite fails. Everything is shown live in an interactive **3D digital twin**
of the network, and a **timeline** replays any past moment. Time is the fourth
dimension that makes the twin "4D".

> **Safety and honesty note.** All devices, attacks, failures, quarantine
> actions and handovers are **simulated on your own computer**. The project does
> not attack or isolate real devices, real telecom networks or real satellites.
> It does not implement a real satellite handover protocol or a real 5G core
> network. All measured values are simulated. The only real hardware is the
> optional ESP32 sensor on your own Wi-Fi.

---

## Contents

1. [Problem and objectives](#1-problem-and-objectives)
2. [Features](#2-features)
3. [System architecture](#3-system-architecture)
4. [Technology stack](#4-technology-stack)
5. [Project structure](#5-project-structure)
6. [Installation](#6-installation)
7. [Running the project](#7-running-the-project)
8. [Using the dashboard](#8-using-the-dashboard)
9. [IoT devices](#9-iot-devices)
10. [MQTT communication](#10-mqtt-communication)
11. [Satellite–5G network model and failover](#11-satellite5g-network-model-and-failover)
12. [Cybersecurity detection](#12-cybersecurity-detection)
13. [Device quarantine](#13-device-quarantine)
14. [3D digital twin and 4D timeline](#14-3d-digital-twin-and-4d-timeline)
15. [Database](#15-database)
16. [REST API and WebSocket](#16-rest-api-and-websocket)
17. [Configuration](#17-configuration)
18. [Testing and results](#18-testing-and-results)
19. [Troubleshooting](#19-troubleshooting)
20. [Limitations and future work](#20-limitations-and-future-work)
21. [Documentation index](#21-documentation-index)
22. [Version 1.1: login, secure MQTT, motion, real map, AI](#22-version-11-login-secure-mqtt-motion-real-map-ai)
23. [Version 1.2: many companies on one system](#23-version-12-many-companies-on-one-system)
24. [Phone alarm](#24-phone-alarm)

---

## 1. Problem and objectives

IoT devices increasingly reach the internet through both **terrestrial (5G)**
and **satellite** links. These networks face:

* cyberattacks on IoT devices (flooding, spoofing, rogue devices),
* abnormal device behaviour and unauthorized devices,
* excessive traffic that hurts network performance,
* satellite or terrestrial link failures,
* difficulty understanding how an incident evolves over time.

**Objectives:**

1. Collect IoT data over MQTT.
2. Simulate a satellite–5G network.
3. Detect suspicious behaviour and raise alerts.
4. Quarantine suspicious devices.
5. Simulate link failures and automatic failover.
6. Visualise it all in 3D with a time-based replay.

---

## 2. Features

| Feature | Phase |
|---|---|
| FastAPI backend + React dashboard over REST and WebSocket | 1 |
| SQLite database (11 tables), created automatically | 2 |
| Built-in simulator for 3 IoT devices (temperature, humidity, battery) | 2 |
| MQTT through a Mosquitto broker, with validation and auto-reconnect; standalone attack simulator | 3 |
| Satellite, ground station, 5G tower, core and security server with live latency, loss and bandwidth; rain fade | 4 |
| Rule-based detection: flood, unauthorized device, abnormal values, connection storm, link/node failure, ID spoofing, malformed messages | 5 |
| Logical quarantine (automatic and manual), traffic blocking, release, history | 6 |
| **Interactive 3D digital twin:** Earth, orbiting satellite, ground station, 5G tower, servers, devices, animated links, click to inspect | 7 |
| **Satellite → 5G failover** with measured handover time, interruption and lost readings; outage drill | 8 |
| **4D timeline:** full-state snapshots every 2 s, replay in 3D with play, pause, speed and event markers | 9 |
| **Dashboard** with 5 tabs, Recharts charts, CSV exports and a printable session report | 10 |
| **Real ESP32 + DHT22** device (Arduino firmware) and an emulator | 11 |
| **30 automated tests**, optional **machine-learning** anomaly detector (Local Outlier Factor), final docs | 12 |

---

## 3. System architecture

```
 IoT devices                                ┌──────────────────────┐
 built-in simulator ─┐                      │  Mosquitto broker    │
 MQTT simulator ─────┼──── MQTT ──────────► │  :1883               │ ◄── command topic ──┐
 ESP32 + DHT22 ──────┘   (telemetry/status) └──────────┬───────────┘                     │
                                                       ▼                                 │
 ┌───────────────────────────────── FastAPI backend (Python) ───────────────────────────┼──┐
 │ mqtt_client ─► telemetry_service ─► detection_engine (rules) ─► quarantine_service ───┘  │
 │                       │             ml_detector (optional)                               │
 │ network_simulator ─► failover_service (primary / backup paths)                           │
 │        │                                                                                 │
 │        └──► timeline_service (frame every 2 s)        event_log (every event)            │
 │                       │                                      │                           │
 │                       ▼                                      ▼                           │
 │                         SQLite  database/cybershield.db                                  │
 └──────────────────────────┬─────────────────────────────────────┬─────────────────────────┘
                   REST API │                                     │ WebSocket /ws (live push)
                            ▼                                     ▼
 ┌─────────────────────────── React + Vite dashboard ─────────────────────────────────────┐
 │ Overview · 4D Twin (Three.js scene + timeline) · Network (map, failover, link charts)  │
 │ Security (attacks, alerts, quarantine, ML, statistics) · Data & Reports (CSV, report)  │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

**Why each part exists**

* **MQTT broker:** the standard publish/subscribe transport for IoT. Devices
  never talk to the backend directly, so a real ESP32 can replace a simulated
  device without changes.
* **telemetry_service:** the single entry point for every reading. It
  validates, checks registration, blocks quarantined devices, stores the
  reading and pushes it live.
* **detection_engine:** explainable rules that turn suspicious behaviour into
  alerts. **ml_detector** gives an optional learned second opinion.
* **network_simulator + failover_service:** realistic, changing link numbers,
  failures, routing, and the satellite → 5G failover state machine.
* **timeline_service:** records the full state, which makes the twin replayable (4D).
* **WebSocket:** the server pushes changes instantly instead of the browser polling.
* **Modular design:** each part is its own file and is tested on its own.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 4. Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn, SQLAlchemy 2, SQLite, Pydantic, Paho-MQTT 2 |
| IoT messaging | MQTT, Mosquitto 2 |
| Frontend | React 19, Vite 8, plain CSS (dark theme) |
| 3D | Three.js, React Three Fiber, Drei |
| Charts | Recharts |
| Hardware | ESP32 + DHT22 (Arduino: PubSubClient, Adafruit DHT, ArduinoJson) |
| Optional ML | scikit-learn (LocalOutlierFactor), NumPy |
| Testing | pytest, FastAPI TestClient, Playwright (manual UI checks) |
| Tools | VS Code, Git, Node.js 22 LTS, npm, Arduino IDE 2 |

---

## 5. Project structure

```
CyberShield-SatCom-3D/
├── backend/
│   ├── requirements.txt          core dependencies
│   ├── requirements-ml.txt       optional: scikit-learn, numpy
│   ├── requirements-dev.txt      tests: pytest, httpx
│   ├── pytest.ini
│   ├── tests/                    30 automated tests
│   └── app/
│       ├── main.py               start-up, CORS, WebSocket /ws, routers
│       ├── config.py             all settings (from .env, with defaults)
│       ├── database.py · models.py · schemas.py · seed.py
│       ├── websocket_manager.py · event_log.py
│       ├── telemetry_service.py  single entry point for readings
│       ├── device_simulator.py · simulation_controller.py
│       ├── mqtt_topics.py · mqtt_client.py
│       ├── network_simulator.py  links, failures, routes, availability
│       ├── failover_service.py   satellite → 5G failover state machine
│       ├── timeline_service.py   4D snapshots
│       ├── detection_engine.py · attack_simulator.py · ml_detector.py
│       ├── quarantine_service.py
│       └── routes/               system, devices, simulation, network, alerts,
│                                 quarantine, failover, timeline, reports, ml
├── frontend/
│   ├── package.json · vite.config.js (proxy /api and /ws to :8000)
│   └── src/
│       ├── App.jsx               tabs
│       ├── three/                3D twin: Earth, satellite, nodes, links, labels, scene
│       ├── components/           panels, cards, map, timeline, failover, report…
│       ├── components/charts/    Recharts charts + shared theme
│       ├── hooks/                live data, WebSocket, timeline, summary
│       ├── services/             api.js, timeline.js
│       └── styles/global.css
├── iot/
│   ├── simulator/mqtt_simulator.py   MQTT devices + attack scenarios
│   ├── simulator/esp32_emulator.py   behaves like the real ESP32
│   ├── esp32/cybershield_esp32/      Arduino firmware + config.h
│   └── mosquitto/mosquitto.conf      broker config for the ESP32
├── database/                     cybershield.db is created here
├── docs/                         phase guides, architecture, testing, demo, report outline
├── .env.example                  every setting you can change
└── README.md
```

---

## 6. Installation

### Software

| Software | Version | Check with |
|---|---|---|
| Python | 3.10 or newer | `python --version` |
| Node.js | 22 LTS (20.19+ also works) | `node --version` |
| Mosquitto | 2.x (recommended; the app also works without it) | `& "C:\Program Files\mosquitto\mosquitto.exe" -h` |
| Git, VS Code | any recent | `git --version` |
| Arduino IDE 2 | only for the real ESP32 | — |

On Windows, tick **"Add python.exe to PATH"** when installing Python. If you
installed Mosquitto on D:, use `D:\Program Files\mosquitto` wherever this
README says `C:\Program Files\mosquitto`.

### Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
# optional
pip install -r requirements-ml.txt     # ML detector
pip install -r requirements-dev.txt    # automated tests
```

### Frontend

```powershell
cd frontend
npm install
```

---

## 7. Running the project

1. **MQTT broker.** On Windows Mosquitto usually runs as a service already. Otherwise:
   `& "C:\Program Files\mosquitto\mosquitto.exe" -v`
2. **Backend (terminal 1)**, with the venv active:
   ```
   uvicorn app.main:app --reload --port 8000
   ```
   Expected: `[mqtt] connected ...` and `[startup] CyberShield SatCom 3D v1.2.0 ready`.
3. **Frontend (terminal 2):** `npm run dev`
4. Open the dashboard at **http://localhost:5173** and the API docs at **http://127.0.0.1:8000/docs**.
5. **Log in** (v1.1). First-start accounts: `admin` / `Admin@2026`, `operator` / `Operator@2026`,
   `viewer` / `Viewer@2026`. Change the passwords in **Admin → Users** (or the account menu).

The database is created on the first start and the simulation starts automatically.

---

## 8. Using the dashboard

| Tab | What it shows / does |
|---|---|
| **Overview** | Status cards, Start / Pause / Reset, temperature and humidity charts, availability chart, latest events, device cards (with **⚙ Configure**) |
| **4D Twin** | 3D scene (drag, zoom, click to inspect, Quarantine / Identify / Degrade / Take offline) and the **timeline**: Live / Replay, slider, event markers, play at 1–30×, previous/next event |
| **Network** | 2D map + routes with path badges, **failover panel** (on/off, outage drill, statistics), availability and battery charts, link latency and packet-loss history, link table |
| **Security** | Attack buttons (Rules A–D), quarantine panel and auto switch, ML detector, alerts (Resolve / Quarantine), alert statistics |
| **Data & Reports** | Session report (print / save as PDF), CSV downloads, **Save all to project folder** (writes the CSVs into `exports/`, for browsers that block downloads such as the VS Code preview), telemetry table, event log |
| **Real map** | Satellite photo / street map with every device at its real place (farm, company, desert, lab…), live values in the pins, place search, admin can move a pin (needs internet) |
| **AI assistant** | Ask about the live system, incident report, explain the latest alert, run suggested commands with one click |
| **Console** | Terminal-style **operator console**: type commands instead of clicking (see below) |
| **Admin** | (admin only) users and roles, security **audit log** with CSV export |

### Operator console

The **Console** tab is a terminal for the network security operator. Every
command uses the same REST API as the buttons, so it can only act on the
simulation. Type `help` to see all commands. Use ↑/↓ for history, Tab to
complete a command name, and Ctrl+L to clear the screen.

| Command | What it does |
|---|---|
| `status` | backend, simulation, MQTT, network, failover, quarantine and alert summary |
| `devices` · `device IOT-001` | device list / details |
| `config IOT-002 temp 15 30` · `config IOT-002 humidity 20 80` · `config IOT-002 location Lab 3` | configure a device |
| `quarantine IOT-002 [reason]` · `release IOT-002` · `autoquarantine on\|off` | quarantine control |
| `identify ESP32-001` · `ping ESP32-001` | harmless MQTT commands to the device |
| `alerts [n]` · `resolve 7` · `events [n]` | alerts and events |
| `routes` · `links` · `link L-SAT-GS offline` · `node SAT-1 auto` | network status and simulated failures |
| `failover on\|off` · `failover drill 30` | satellite → 5G failover |
| `attack flood\|unauth\|abnormal\|storm [id]` | start a simulated attack |
| `adddevice IOT-004 satellite [via SAT-2] [name]` · `removedevice IOT-004` | add / remove IoT devices |
| `addnode SAT-2 satellite\|ground\|tower` · `addlink SAT-2 GS-2 satellite [backup]` · `removenode` · `removelink` · `nodes` | network builder |
| `fix IOT-001` · `fix network` · `fix all` | undo it: release the device and resolve its alerts, bring links and nodes back to normal |
| `export alerts` · `export all` | save CSV files into the project's `exports` folder |
| `sim start\|pause\|reset` · `ml status\|train\|on\|off` | simulator and ML detector |
| `motion IOT-003 [day]` · `sensor IOT-001 motion on\|off` | simulate movement at a PIR sensor / add or remove the sensor (v1.1) |
| `where IOT-003` | real place, address, coordinates and an OpenStreetMap link (v1.1) |
| `ai is the farm safe tonight?` | ask the AI assistant (v1.1) |
| `whoami` | your account and role (v1.1) |

**Demo in 5 minutes:** see [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

---

## 9. IoT devices

| ID | Name | Type | Connection | Typical climate | Allowed range |
|---|---|---|---|---|---|
| IOT-001 | Remote Sensor 01 | Environmental | Satellite (backup 5G) | desert ~34 °C, ~22 % | 0–50 °C, 5–70 % |
| IOT-002 | Smart Building 02 | Smart building | 5G | office ~23 °C, ~45 % | 15–32 °C, 25–70 % |
| IOT-003 | Agri Field 03 | Agricultural | Satellite (backup 5G) | farm ~19 °C, ~68 % | −5–45 °C, 20–95 % |
| ESP32-001 | ESP32 Lab Sensor | **Real** ESP32 + DHT22 (optional) | Wi-Fi, modelled as 5G access | real room | 5–40 °C, 10–90 % |

Each simulated device sends a reading every 5 s. Values follow a slow
day/night wave plus noise. A device silent for more than 15 s is shown offline.
The ESP32 is enabled with `ESP32_ENABLED=true` (see [Phase 11 guide](docs/PHASE11_GUIDE.md)).

**Configuring a device (network security operator).** On any device card, click
**⚙ Configure**. The operator can change the name, type, location and the allowed
temperature and humidity range, then click **Save**. The change is:

* checked first (the minimum must be lower than the maximum, humidity must be 0–100 %),
* saved in SQLite, so it survives a restart,
* used by the detection engine from the next reading (a reading outside the new
  range raises an *abnormal sensor value* alert),
* written to the event log, showing which values changed.

The device ID and its connection (satellite or 5G) can't be edited, because
they are part of the network topology. The same action is available as an API call:
`PUT /api/devices/{id}/config`.

**Adding a new IoT device.** On the Overview tab, click the **➕ Add device** card
(or type `adddevice IOT-004 satellite Water Tank 04` in the Console). Choose an ID,
name, type, location, connection (satellite or 5G), which satellite or 5G tower it
uses, and its allowed ranges. The system creates everything in one step:

* the device row in SQLite and a network node (2D map and 3D twin),
* access links: satellite devices get a primary satellite link **and** a backup 5G
  link, so failover works for them too; 5G devices get one 5G link,
* a simulated twin whose climate stays inside the allowed ranges. Untick
  *Simulate its readings* for a real board that publishes to
  `cybershield/iot/<ID>/telemetry` itself.

From then on every detection rule, quarantine, failover, the timeline and the
CSV exports include it. Devices you added get a **🗑 Remove** button. The four
built-in devices can't be removed.

### Network builder (design your own architecture)

The **Network** tab has a **Network builder** panel, and the same actions are
available as Console commands. The operator can:

1. **Add a node:** a satellite, a ground station or a 5G base station
   (`addnode SAT-2 satellite`, `addnode GS-2 ground`, `addnode BS-5G-2 tower`).
2. **Connect two nodes** with a satellite, 5G, fiber or LAN link, as primary or
   backup (`addlink SAT-2 GS-2 satellite`, `addlink GS-2 CORE fiber`).
3. **Attach devices** to the new satellite or tower
   (`adddevice IOT-005 satellite via SAT-2 Ship Tracker 05`).

Traffic is routed automatically over any working path to the telecom core
(`CORE`), so the new paths are used at once. Failures (`node SAT-2 offline`),
failover, rain fade and the 3D twin all work on the new topology. Only the
nodes and links you added can be removed (`removenode`, `removelink`). A node
can't be removed while a device still connects through it. The original
network stays, so the demo always has a working base.

**Standalone simulators** (run from the project root with a venv active):

```powershell
python iot\simulator\mqtt_simulator.py --scenario flood --device IOT-002 --rate 20
python iot\simulator\mqtt_simulator.py --scenario unauthorized
python iot\simulator\mqtt_simulator.py --scenario abnormal --device IOT-001
python iot\simulator\mqtt_simulator.py --scenario connstorm --device IOT-002
python iot\simulator\mqtt_simulator.py --scenario disconnect --device IOT-003
python iot\simulator\esp32_emulator.py          # pretends to be the ESP32
```

---

## 10. MQTT communication

| Topic | Direction | Payload |
|---|---|---|
| `cybershield/iot/<id>/telemetry` | device → backend | `{"device_id":"IOT-001","temperature":26.5,"humidity":58.2,"battery":87,"source":"simulator"}` |
| `cybershield/iot/<id>/status` | device → backend | `online` / `offline` (also the MQTT "last will") |
| `cybershield/iot/<id>/command` | backend → device | `{"action":"quarantine"}` · `release` · `identify` · `ping` |
| `cybershield/security/alerts` | backend → anyone | each new alert (JSON) |
| `cybershield/network/events` | backend → anyone | each event-log entry (JSON) |

Every message is checked: valid JSON, ID matches the topic, device registered,
fields present and physically possible. If the broker is down, the built-in
simulator delivers directly and the backend reconnects by itself.

---

## 11. Satellite–5G network model and failover

```
                 SAT-1 (LEO satellite)
               /    |       \
         IOT-001  IOT-003    GS-1 (ground station)
            :  \     :          |
     backup :   \    : backup   | fiber
            :    \   :          |
          BS-5G ─── fiber ───── CORE ── LAN ── SEC (security server)
            |   \
          IOT-002  ESP32-001 (optional)
```

| Link type | Typical latency | Typical loss | Typical bandwidth |
|---|---|---|---|
| Satellite (LEO) | ~35 ms | ~0.3 % | ~120 Mbps |
| 5G radio | ~12 ms | ~0.1 % | ~500 Mbps |
| Fiber | ~3 ms | ~0.01 % | ~10 Gbps |
| LAN | ~0.5 ms | 0 % | ~1 Gbps |

* Every 2 s each link gets new values with noise. A link is **degraded** above 2 % loss or 2.5× normal latency.
* Random **rain fade** weakens a satellite link for 15–30 s, about every 3 minutes.
* Nodes and links can be degraded or taken offline from the 2D map or the 3D inspector.
* **Network availability** = % of non-quarantined devices with a path to the core.

**Failover (Phase 8).** Each device has a primary path and, for IOT-001 and
IOT-003, a backup 5G path. A per-device state machine does the following:

* **primary → switching → backup** when the satellite path is lost, or stays
  degraded for 6 s. The handover is simulated and takes 1.5 to 3 s.
* **backup → primary** (failback) once the satellite has been healthy for 10 s.
* **down** when no path exists.

A break-before-make switch loses connectivity during the handover. A
make-before-break switch (degraded primary, or failback) loses nothing. Readings
made without a path are **lost** and counted. The **outage drill** takes SAT-1
offline for 30 s.

---

## 12. Cybersecurity detection

| Rule | Alert | Trigger (default) | Severity |
|---|---|---|---|
| A | Excessive message rate | > 10 msg/s over 5 s (normal: 0.2 msg/s) | high |
| B | Unauthorized device | message from an unregistered device ID | high |
| C | Abnormal sensor value | outside the device's allowed range | medium, or high if 15+ units outside |
| D | Suspicious connections | > 5 connections in 30 s | high |
| E | Link / node failure | link or node offline | high / critical |
| — | Device ID spoofing | ID in message ≠ ID in MQTT topic | high |
| — | Malformed message | invalid JSON or fields | low |
| ML | Unusual reading (optional) | Local Outlier Factor says the reading doesn't fit the learned normal pattern | medium (advisory) |

* The same alert for the same device or link is not repeated within 30 s.
* A device involved in a high or critical alert becomes **suspicious**.
* The **ML detector** is optional (`requirements-ml.txt`, `ML_ENABLED=true`).
  It trains itself on stored normal readings, and its alerts are marked
  `detection_method = "ml"`.

---

## 13. Device quarantine

* **Automatic** on flood, connection-storm and spoofing alerts (switch on the dashboard). **Manual** with the Quarantine buttons.
* A quarantined device's messages are **blocked**: counted, never stored.
* The device turns red with a 🔒 on the dashboard and a rotating red cage in 3D. It is isolated from routing and receives a `quarantine` MQTT command, and the real ESP32 stops sending and blinks.
* **Release** brings it back. **Mark safe** clears a *suspicious* flag.
* Abnormal sensor values never auto-quarantine (a real fire is not an attack). ML alerts never auto-quarantine either.

---

## 14. 3D digital twin and 4D timeline

* **3D (Phase 7):** a globe with a code-drawn texture (no downloads), a LEO
  satellite sweeping along its orbit, and equipment placed by latitude and
  longitude (positions are illustrative). Links are curved and animated, with
  moving "packets" where traffic flows. Colours come from the live state:
  green online, amber degraded, red offline, grey standby, dark red blocked.
  Click any object to inspect it.
* **4D (Phase 9):** every 2 s the backend stores a ~1.5 KB frame of the whole
  twin: node and link states, routes, device readings, availability and open
  alerts. The timeline downloads the frames and replays them in the same 3D
  scene. Use it to analyse an incident after it happened.

---

## 15. Database

SQLite file `database/cybershield.db`, created automatically on the first start.

| Table | Content |
|---|---|
| `devices` | registered devices, latest values, status, security status, allowed ranges |
| `telemetry` | every accepted sensor reading |
| `security_alerts` | every alert (`detection_method`: rule or ml) |
| `quarantine_records` | every quarantine and release, with blocked message counts |
| `network_nodes` / `network_links` | topology with live status, latency, loss, bandwidth, primary/backup |
| `link_metrics` | link performance history (every ~6 s) |
| `failover_events` | every failover, failback and outage with handover time, interruption and lost readings |
| `state_snapshots` | 4D timeline frames (every 2 s, oldest pruned) |
| `device_settings` | devices added by the operator (simulated or real board) |
| `topology_additions` | nodes and links added with the network builder |
| `network_events` | everything that happened, in time order |
| `simulation_sessions` | each run from Start/Reset to the next Reset |

**Reset** on the dashboard clears readings, events, alerts, quarantine,
failover and timeline data. After upgrading from an older phase, delete
`database\cybershield.db` if you see database errors.

---

## 16. REST API and WebSocket

Interactive documentation: **http://127.0.0.1:8000/docs**

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/info`, `/api/mqtt/status` | system status |
| GET | `/api/devices`, `/api/devices/{id}`, `/api/telemetry`, `/api/events` | devices, readings, events |
| POST | `/api/devices/{id}/command` | `{"action":"identify" \| "ping"}` over MQTT |
| PUT | `/api/devices/{id}/config` | operator edits name, type, location, allowed temperature/humidity range |
| POST / DELETE | `/api/devices`, `/api/devices/{id}` | add a new IoT device / remove one you added |
| POST / DELETE | `/api/network/nodes`, `/api/network/nodes/{id}`, `/api/network/links`, `/api/network/links/{id}` | network builder |
| POST | `/api/simulation/start` · `/pause` · `/reset`; GET `/status` | simulation control |
| POST | `/api/simulation/attack/{excessive-traffic \| unauthorized-device \| abnormal-reading \| connection-storm}` | simulated attacks |
| GET | `/api/network/topology`, `/status`, `/links/{id}/history` | network |
| POST | `/api/network/links/{id}/state`, `/api/network/nodes/{id}/state` | `{"state": "auto" \| "degraded" \| "offline"}` |
| GET / POST | `/api/alerts`, `/api/alerts/stats`, `/api/alerts/{id}/resolve` | alerts |
| POST | `/api/devices/{id}/quarantine`, `/release`; GET/POST `/api/quarantine`, `/settings` | quarantine |
| GET / POST | `/api/failover/status`, `/history`, `/settings`, `/drill?seconds=` | failover |
| GET | `/api/timeline/range`, `/frames?minutes=&max=`, `/at?t=` | 4D timeline |
| GET | `/api/export/{telemetry\|alerts\|events\|quarantine\|failover}.csv`, `/api/report/summary` | exports and report |
| POST | `/api/export/{name\|all}/save` | write the CSV(s) into the project's `exports/` folder |
| GET / POST | `/api/ml/status`, `/train`, `/settings` | optional ML detector |

**WebSocket** `ws://localhost:5173/ws` (proxied). The messages look like
`{"type": ..., "data": ...}`. The types are `telemetry`, `device`, `event`,
`simulation`, `mqtt`, `network`, `alert`, `alert_update`, `quarantine`,
`failover`, `reset` and `heartbeat`. The browser sends `ping` and gets `pong`
back, which is used to measure latency.

---

## 17. Configuration

Copy `.env.example` to `.env` in the project root, change values, and restart
the backend. The main settings:

| Setting | Default | Meaning |
|---|---|---|
| `SIM_INTERVAL` / `OFFLINE_AFTER` | 5 / 15 | reading interval, seconds of silence before "offline" |
| `MQTT_HOST` / `MQTT_PORT` | localhost / 1883 | broker address |
| `NET_RANDOM_EVENTS` | true | random rain fades (false for a calm demo) |
| `RATE_THRESHOLD_PER_SEC` / `CONN_THRESHOLD` | 10 / 5 | Rule A and D thresholds |
| `ALERT_COOLDOWN_SECONDS` | 30 | no duplicate alerts within this time |
| `AUTO_QUARANTINE` | true | auto-quarantine on serious alerts |
| `FAILOVER_ENABLED` | true | automatic satellite → 5G failover |
| `HANDOVER_DELAY_MIN` / `MAX` | 1.5 / 3.0 | simulated handover time |
| `FAILBACK_STABLE_SECONDS` | 10 | satellite must be healthy this long before failback |
| `TIMELINE_MAX_SNAPSHOTS` | 5400 | ~3 h of 4D history |
| `ESP32_ENABLED` / `ESP32_DEVICE_ID` | false / ESP32-001 | the real board |
| `ML_ENABLED` | false | optional ML detector |

---

## 18. Testing and results

**Automated tests** (backend, 88 tests, about 15 s; they also pass on PostgreSQL):

```powershell
cd backend
venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest
```

They cover the API, all detection rules through the real ingest path,
auto-quarantine and traffic blocking, the failover state machine (with fixed
times), timeline recording, CSV exports, the report, the ML detector
(skipped if scikit-learn is missing), and in v1.1 login, roles, brute-force
lock, user management, the audit log, motion alerts, device locations and the
AI assistant (offline answers and a mocked LLM).

**Measured results** (simulated network, from the test runs):

| Metric | Result |
|---|---|
| False alerts during normal traffic | 0 in 45 s with 3 devices |
| Flood detection time (20 msg/s) | about 2.5 s |
| Alert → auto-quarantine | same second |
| Attacker messages stored after quarantine | 0 (100 % blocked) |
| Service interruption, satellite outage, failover ON | about 2.6–4 s (detection + handover) |
| Service interruption, satellite outage, failover OFF | the whole outage (25–30 s) |
| Readings lost per device in a 25 s outage | ~1 with failover, ~5 without |
| Failback interruption | 0 s (make-before-break) |

The full test plan, with the manual UI tests, is in [docs/TESTING.md](docs/TESTING.md).

---

## 19. Troubleshooting

| Problem | Fix |
|---|---|
| `cd backend` fails | Check the Explorer; if there's a `CyberShield-SatCom-3D` folder, `cd CyberShield-SatCom-3D\backend` |
| "running scripts is disabled" | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
| `uvicorn` / `fastapi` not found | Activate the venv, `pip install -r requirements.txt` |
| "Cannot reach the backend" / Vite `ECONNREFUSED` | Start the backend first |
| MQTT card "Offline" | Mosquitto isn't running; the app still works in "direct" mode |
| Mosquitto "Only one usage of each socket address" | Already running as a service, which is fine |
| "3D view needs WebGL" | Use Chrome/Edge with hardware acceleration on |
| `Failed to resolve import "three"` / `"recharts"` | `npm install` in the frontend folder |
| Database errors after an upgrade | Stop the backend, delete `database\cybershield.db`, start again |
| ESP32 problems | See the troubleshooting table in [docs/PHASE11_GUIDE.md](docs/PHASE11_GUIDE.md) |
| "Method Not Allowed" / new tabs missing | An old backend is still running. Close every old terminal, start the backend from the new folder |
| Forgot the admin password | Stop the backend, delete `database\cybershield.db`, start again (default accounts come back) |
| `No module named httpx` | `pip install -r requirements.txt` again (v1.1 added httpx) |
| `Failed to resolve import "leaflet"` | `npm install` again in the frontend folder (v1.1 added leaflet) |
| Real map is grey | The map tiles need internet |
| AI says "offline analyst" | Normal without a key; see section 22 to add a free key |

---

## 20. Limitations and future work

* The network, attacks, failover timings and 3D positions are **simulated** and simplified. They are not a model of a real 3GPP network.
* Detection is mostly rule-based with fixed thresholds. The optional ML detector is basic (unsupervised, per-reading).
* Login uses local accounts and simple tokens; secure MQTT is optional (see docs/SECURE_MQTT.md). Good for a university demo, not a hardened production system.
* There is one satellite. Real LEO networks hand over between many satellites.
* The AI assistant only advises; it never runs a command by itself. An online model can be wrong, so check its advice.
* **Future work:** two-factor login, more satellites with real orbit data, ML on traffic patterns (not only values), deployment with Docker.

---

## 21. Documentation index

| File | Content |
|---|---|
| `docs/PHASE1_GUIDE.md` … `PHASE12_GUIDE.md` | Step-by-step guide and test table for every phase |
| `docs/ARCHITECTURE.md` | Components, data flow, design decisions |
| `docs/TESTING.md` | Test plan, automated and manual tests, results |
| `docs/DEMO_SCRIPT.md` | 5-minute live demo, step by step |
| `docs/REPORT_OUTLINE.md` | Suggested chapters for the written report and the presentation |
| `docs/SECURE_MQTT.md` | Passwords, ACL and TLS for Mosquitto (v1.1) |
| `docs/PHONE_ALARM.md` | Phone alarm with ntfy / Telegram, alarm sound (v1.2) |
| `docs/CLOUD_DEPLOY.md` | Run it on Huawei Cloud (ECS + Docker, optional RDS) (v1.3) |
| `docs/CLOUD_MQTT.md` | Use a cloud MQTT broker (HiveMQ Cloud / EMQX Cloud, TLS) instead of Mosquitto (v2.4) |
| `docs/DEEPSEEK_AI.md` | AI analyst on DeepSeek: get a key, dashboard or `.env` (v2.6) |
| `docs/HUAWEI_AI.md` | AI analyst on Huawei Cloud ModelArts Studio (MaaS) + Huawei technology map (v2.5) |
| `docs/COMPETITION_CHECKLIST.md` | Huawei competition: deploy, IoTDA, ModelArts, benchmark, video checklist (v2.5.2) |
| `tools/benchmark.py` | Measures detection time, false alarms and failover times (v2.5.2) |
| `docs/SOC_ROADMAP.md` | SOC audit and the four stages (v2.0, v2.1) |
| `docs/HUAWEI_INNOVATION.md` | Huawei ICT Competition (Innovation): pitch, Huawei Cloud / IoTDA / ModelArts setup, lab test (v2.2) |
| `docs/FINAL_REPORT.md` | Final implementation report: architecture, real vs simulated, roles, demo, limits (v2.1) |

---

## 22. Version 1.1: login, secure MQTT, motion, real map, AI

After updating, run once: `pip install -r requirements.txt` (backend) and
`npm install` (frontend). The new database tables are created automatically.

### Login, roles and audit log

| Role | Can |
|---|---|
| **viewer** | see everything, ask the AI, change own password |
| **operator** | + attacks, quarantine / release, failover, drills, resolve alerts, exports, console actions |
| **admin** | + add / remove devices and nodes, configure devices and locations, auto-quarantine, reset, users, audit log |

* Passwords are stored as PBKDF2-SHA256 hashes; tokens are random and stored only as SHA-256 hashes.
* 5 wrong passwords lock the account name for 60 s (`LOGIN_MAX_FAILURES`, `LOGIN_LOCK_SECONDS`).
* Every login, failed login, denied request and change is written to the **audit log** (Admin tab, CSV export).
* The rules are checked by the backend for every API call and the WebSocket, not only hidden in the UI.
* `AUTH_ENABLED=false` in `.env` switches login off (everyone is admin), e.g. for quick tests.

### Secure MQTT

Per-device passwords, an ACL that stops a device from writing to another
device's topics (spoofing), and TLS on port 8883. Steps: [docs/SECURE_MQTT.md](docs/SECURE_MQTT.md).

### Motion sensors (PIR, e.g. HC-SR501)

* A device with `has_motion` sends `"motion": true/false` in its readings.
  IOT-003 (the farm) has one in the simulation. Turn it on for any device in **⚙ Configure** or with `sensor <id> motion on`.
* **Rule F:** movement at night (22:00–06:00, `MOTION_NIGHT_START/END`) raises a
  **high** `movement_detected` alert (intruder or animals escaping). `MOTION_ALERT_ALWAYS=true` alerts day and night.
  Movement is a physical event, so the device is not marked as hacked.
* Try it: the **Simulate night movement** button on the device card, or `motion IOT-003`.
* Real ESP32: wire HC-SR501 OUT → GPIO 27, VCC → 5V (VIN), GND → GND, and set `PIR_PIN 27` in `config.h`.

### Real locations: 3D Earth and Real map

* Every device and node has a latitude / longitude, a place type (farm, company,
  desert, lab, tower, data centre…) and an address. The example network is in Morocco:

| Node | Place |
|---|---|
| IOT-001 | desert sensor, Erg Chebbi near Merzouga |
| IOT-002 | office tower, Casablanca (Maarif) |
| IOT-003 | livestock farm, Saïss plain near Meknès (motion sensor) |
| ESP32-001 | university lab, Rabat |
| GS-1 | satellite ground station, Benguerir |
| BS-5G, CORE | 5G tower and telecom core, Casablanca |
| SEC | security operations centre, Rabat |

* Change them in **⚙ Configure**, when adding a device, or on the **Real map** (admin: choose the device, click the new place).
* The **4D Twin** now uses a real NASA Blue Marble Earth with relief and water shine, and puts the equipment at its real coordinates (close nodes are spread a little so labels stay readable).
* The **Real map** uses Esri satellite photos or OpenStreetMap, both free, no key. It needs internet.

### AI assistant (free API)

Works **without any key** (built-in offline analyst that reads the live state).
For free-form answers, add a free key:

1. Open **https://aistudio.google.com/apikey**, sign in with Google, click **Create API key** (free tier).
2. In `.env`: `AI_PROVIDER=gemini` and `AI_API_KEY=<your key>`.
3. Restart the backend. The AI tab shows `gemini · gemini-2.5-flash`.

Other free choices: `AI_PROVIDER=groq` (key from console.groq.com) or
`AI_PROVIDER=openrouter` (key from openrouter.ai, free models). If the online
API fails, the offline analyst answers instead. The AI only sees a summary of
the simulated system (devices, alerts, routes) and **never runs commands by
itself**: it suggests console commands, and you click to run them.

### New API endpoints

| Method | Path | Role |
|---|---|---|
| POST | `/api/auth/login`, `/api/auth/logout`, `/api/auth/password` | public / any |
| GET | `/api/auth/me`, `/api/auth/config` | any / public |
| GET POST PUT DELETE | `/api/auth/users[/{name}]` | admin |
| GET | `/api/audit`, `/api/audit/export.csv` | admin |
| PUT | `/api/profiles/{node_id}` (location, place, address, motion sensor) | admin |
| POST | `/api/devices/{id}/motion?night=true` | operator |
| GET | `/api/ai/status` | viewer |
| POST | `/api/ai/chat`, `/api/ai/explain-alert/{id}`, `/api/ai/report` | viewer |

New tables: `users`, `auth_sessions`, `audit_log`, `motion_readings`, `device_profiles`.

---

## 23. Version 1.2: many companies on one system

One installation can now serve **many companies** at the same time (multi-tenant,
like a SaaS). Think of the platform owner as a telecom / satellite provider, and
the companies as its customers.

| Shared by everyone (the provider's network) | Owned by one company |
|---|---|
| satellites, ground station, 5G tower, telecom core, security server | IoT devices: their readings, alerts, events, quarantine, routes, reports, CSV exports, AI answers, users and audit entries |

**Two kinds of users**

* **Platform users** (no company): `admin`, `operator`, `viewer`. They see every company.
  The platform admin creates companies, their first admin, and decides which company owns each device (**Admin → Companies**).
  Only the platform can change the shared network: start / pause / reset the simulation, failover and drills,
  link and node failures, the network builder, auto-quarantine and the ML detector.
* **Company users**: they see **only their company's devices** everywhere (cards, charts, 4D twin, real map,
  alerts, console, reports, AI). A company admin adds devices (they belong to the company automatically),
  manages the company's users, and sees the company's audit log. Company operators can quarantine,
  release, resolve alerts and run simulated attacks **on their own devices only**.

**Demo companies** (created on the first start of v1.2; change the passwords):

| Company | Devices | Admin login |
|---|---|---|
| Atlas Dairy Farms (farm) | IOT-003 | `farm_admin` / `Farm@2026` |
| Casa Business Center (offices) | IOT-002 | `offices_admin` / `Offices@2026` |
| Sahara Solar (energy) | IOT-001 | `solar_admin` / `Solar@2026` |

ESP32-001 stays a platform device (the university lab). `SEED_DEMO_COMPANIES=false` in `.env` starts with no companies.

**Try it:** log in as `farm_admin` in one browser and `admin` in another (or a private window).
The farm sees only IOT-003; `device IOT-001` in its console says "unknown device".

**How it is enforced** (`backend/app/tenancy.py`), by the backend, not only by hiding buttons:

1. The middleware refuses any request that names another company's device, or a shared-network change (403, written to the audit log).
2. Every JSON reply to a company user is cleaned: items about other companies' devices are removed.
3. Every live WebSocket message is filtered per browser in the same way.
4. CSV exports, the session report and the AI assistant only read the company's own devices.

Network-wide numbers (availability, failover counters) describe the **shared** network and are the same for everyone.

**New API** (platform admin): `GET/POST /api/companies`, `PUT/DELETE /api/companies/{id}`,
`PUT /api/companies/devices/{device_id}` `{"company_id": "atlas-farms"}` (or `null` = platform).
`POST /api/devices` and `POST /api/auth/users` accept `company_id` from a platform admin.
New tables: `companies`, `company_members`, `company_devices`.

---

## 24. Phone alarm

When an **attack** is detected (flood, unauthorized device, abnormal reading, connection storm, spoofing,
movement at night...), the backend automatically sends a **push alarm to your phone** through the free **ntfy** app (and/or Telegram), so it rings
even when the dashboard is closed. The dashboard itself can also play a **siren** (🔔 button in the header).

Set it up in **Admin → Phone alarm** (platform admin): make a secret topic, subscribe to it in the ntfy app,
save (this switches the automatic alarm on) and press **Send test alarm**. After that every attack rings the phone by itself. Step by step: [docs/PHONE_ALARM.md](docs/PHONE_ALARM.md).

API (platform admin): `GET/PUT /api/notify/settings`, `POST /api/notify/test`. New table: `notify_settings`.

---

## 25. Version 1.3: big data analytics and cloud

**Big data (Analytics tab).** Every reading is kept in a long-term store, and the backend
summarises it into **hourly tables** every 5 minutes, so charts over months stay fast.

* **Generate history** (platform admin): fills the database with up to 365 days of realistic
  simulated readings for every device: day/night cycle, seasons, battery drain, and attack
  incidents (more at night and at weekends). 90 days × 5 min × 7 devices ≈ 180,000 readings in
  about 5 s; the analytics queries then take well under a second.
* **Charts:** temperature / humidity / battery per day, alerts per day by severity, a
  **weekday × hour heatmap** of attacks (with the busiest time), and the top alert types.
* **Forecast:** the next 24 h for one device, from the average day-shape of the last 7 days plus
  the trend of the last 14 days, with a 95 % band.
* Company users see only their own devices here too. Data & Reports can export the hourly
  summaries as CSV.

**Cloud-ready.** `Dockerfile` (one image: React dashboard + FastAPI) and `docker-compose.yml`
(app + PostgreSQL 16 + Mosquitto). PostgreSQL is used when `DATABASE_URL` is set (SQLite stays
the default on a PC). Step by step for a Huawei Cloud ECS server, with optional RDS for
PostgreSQL: [docs/CLOUD_DEPLOY.md](docs/CLOUD_DEPLOY.md).

```bash
cp .env.cloud.example .env     # set POSTGRES_PASSWORD
docker compose up -d --build   # then open http://<server IP>
```

**New API:** `GET /api/analytics/summary`, `/trends?days=30&bucket=day`, `/alerts?days=30`,
`/forecast?device_id=IOT-001&hours=24`; platform admin: `POST /api/analytics/history`
`{"days": 90, "interval_minutes": 5}`, `GET/DELETE /api/analytics/history`, `POST /api/analytics/rollup`.
New tables: `telemetry_archive`, `telemetry_hourly`, `alert_hourly`.

---

## 26. Version 1.4: real 3D models, bigger customers, tools for operators and engineers

**Realistic 3D twin.** Every piece of equipment now has a detailed model: a communications satellite
(gold-foil body, solar wings, Earth-facing dish), a ground station with a tracking dish and shelter,
a lattice 5G tower with sector antennas, the 5G core data centre and the SOC server racks.
Each IoT device has a model of its real kind of hardware: the ESP32 + DHT22 breadboard, a solar
environmental station, a farm sensor stake, a wall sensor, a vaccine fridge, a reefer container,
a vibration sensor on a conveyor motor. A green/amber/red light on each model shows its status.

**3D model viewer.** Click a device (4D Twin → 🔍 View 3D model, or 🔍 3D on a device card):
a close-up that turns slowly, with numbered parts, the spec sheet (sensor, radio, power), live
values and quick actions. All hardware is simulated; the parts are typical real components.

**Bigger customers.** Added once on the first start of v1.4 (set `SEED_BIG_COMPANIES=false` to skip):

| Company | Devices | Login |
|---|---|---|
| Atlas Mining Corp | IOT-101 pit air monitor (satellite), IOT-102 conveyor vibration (5G) | mining_admin / Mining@2026 |
| Medina Health Hospital | IOT-201 vaccine fridge 2–8 °C, IOT-202 operating room | hospital_admin / Hospital@2026 |
| Tangier Cold Chain Logistics | IOT-301 reefer container at sea (satellite), IOT-302 freezer warehouse | logistics_admin / Logistics@2026 |

**For operators: Incidents tab.** Turn an alert into an incident (+ Incident on the alert), take it,
change status (open → investigating → resolved) and severity, and write notes; everything is kept as
a timeline. Company users only see their own incidents.

**For engineers: Engineering tab.** Health of every device (signal in dBm, latency, packet loss,
battery, last data), simulated **reboot**, simulated **firmware update** (1.0.0 → 1.2.0, one by one
or all at once), and **maintenance mode** (alerts still show, but the phone does not ring while an
engineer works on the device). Platform users also see **System and cloud**: PC or Docker container,
database engine and size, stored readings, uptime, MQTT.

**Cloud monitoring.** Set `METRICS_TOKEN` and point Prometheus / Huawei Cloud AOM at `/metrics`
(with `Authorization: Bearer <token>`): availability, devices, quarantined, open alerts, readings,
battery per device.

**Free AI from the dashboard.** Admin → AI assistant: choose Gemini / Groq / OpenRouter, paste a free
key, press **Save and test**. No `.env` editing needed (the key in `.env` still works too).

**New API:** `GET /api/engineering/devices`, `GET /api/engineering/system`, `POST /api/devices/{id}/reboot`,
`POST /api/devices/{id}/firmware`, `POST /api/devices/{id}/maintenance`, `GET/POST /api/incidents`,
`GET/PUT /api/incidents/{id}`, `POST /api/incidents/{id}/notes`, `GET/PUT /api/ai/settings`, `POST /api/ai/test`, `GET /metrics`.
New tables: `device_ops`, `incidents`, `incident_notes`, `ai_settings`, `app_flags`.

## 27. Version 1.5: bigger network, 16 more devices, network investigation graph

**A more resilient network** (added once on the first start of v1.5, all simulated):

* second satellite **SAT-2** and second ground station **GS-2** (Agadir), with backup downlinks
  SAT-1 → GS-2 and SAT-2 → GS-1 and an inter-satellite link. If GS-1 fails, satellite traffic is
  rerouted through GS-2 automatically.
* four regional 5G towers: **BS-5G-RBT** (Rabat), **BS-5G-FES** (Fès), **BS-5G-TNG** (Tangier),
  **BS-5G-KHO** (Khouribga), each on fibre to the core with a backup fibre to the Casablanca tower.

**16 more IoT devices** (29 in total), for every company: mining (crusher, explosives store, haul truck),
hospital (blood bank freezer, ICU, pharmacy fridge), cold chain (second reefer container, reefer truck,
loading dock), farm (greenhouse soil, milk tank), offices (server room, lobby air), solar (weather station,
inverter room) and two platform devices (port weather station, highway air monitor).

**Analytics → Network investigation.** An interactive graph of the whole system, like a security
investigation tool:

* nodes: satellites, ground stations, towers, core, SOC, IoT devices, companies, alert types
  (observables) and unknown device IDs; edges: network links (solid primary, dashed backup, blue = carrying
  traffic), ownership and alerts (red arrows)
* colours by disposition: Malicious, Suspicious, Common, Unknown, Clean, Asset
* zoom (＋ － or the mouse wheel), drag the background to pan, drag nodes, **Fit**, **Reset**, layouts
  Force / Layered / Radial, filter box, Sources and Disposition filters, **Affected only**, **Hide**
* side lists: **Assets and observables** with counts, **Indicators** (alert types), details of the
  clicked node or link, and a **Timeline** of alerts per hour
* **Save layout** keeps your node positions (per user)
* **Edit network** (platform admin): ＋ Satellite / ＋ Ground station / ＋ 5G tower, 🔗 **Connect** two
  nodes (fibre, satellite, 5G or LAN; primary or backup), 🗑 remove what you added, and **Re-wire** a
  device through another satellite or tower. Changes show at once in the 2D map, the 4D twin and the routes.

**Free AI through OmniRoute.** Admin → AI assistant → *OmniRoute (self-hosted gateway)*. OmniRoute
(github.com/cheaper-inference/OmniRoute, MIT) is a free gateway that you install and run yourself; it
forwards to the free tiers of many AI providers. It is not a free hosted API: you still connect your own
free accounts (Gemini, Groq...) inside OmniRoute. Default address `http://localhost:20128/v1`, model `auto`,
key optional. Any other OpenAI-compatible server works too (e.g. Ollama at `http://localhost:11434/v1`).

**Charts:** with many devices the live charts show 6 devices by default; choose "All" or one device.

**New API:** `GET /api/analytics/graph`, `GET/PUT /api/analytics/graph/layout`,
`POST /api/network/devices/{id}/access` (re-wire, platform admin). New table: `graph_layouts`.


## 28. Version 2.0 (stage 1): CyberShield SOC

The dashboard is now a Security Operations Center console. See `docs/SOC_ROADMAP.md` for the audit, the
four stages and what is real or simulated.

**New look.** Dark navy theme, a sidebar with grouped modules (Operations, Infrastructure, Intelligence,
Management) and counters, line icons, global search (devices, alerts, incidents, modules; Enter opens the
result), a notification bell with open high/critical alerts, a live connection indicator and SIM / LAB
badges on every alert and reading. Old links (`#security`, `#data`, `#map`, `#engineering`) still work.

**SOC Overview.** Open incidents by severity, active alerts, alerts in 24 h (chart by severity),
**MTTD** (simulated attack start → first alert), **MTTA** (alert → first analyst action), **MTTR**
(incident opened → resolved), devices online / suspicious / quarantined, availability, traffic,
satellite / 5G / fibre link status, detection engine and data ingestion health, most targeted assets and
top detections. All values come from the database; "—" means no data yet.

**Alert Center.** Filters (status, severity, investigation state, rule, time range) and search (ID,
device, rule, MITRE ID such as `T1498`, analyst), CSV export, "×N similar" duplicates and correlated
alerts. Each alert has a rule ID, MITRE ATT&CK technique, confidence, data source and SIM/LAB label.
The alert page shows the rule logic and explanation, evidence (device events and readings around the
alert), related alerts, incidents and the investigation history, with **Acknowledge, Investigate, Assign,
Escalate to incident, Quarantine, Close, Reopen** and analyst notes.

**Detection Rules.** The 10 rules with logic, MITRE technique, confidence, hits in 24 h and last hit.
A platform admin can switch a rule off (the engine stops raising it) and an operator can press **Test**
to run the simulated attack the rule must catch.

**IoT Asset Management** (inventory with filters, device card, configure, recent alerts),
**Satellite & 5G Security** (space segment, ground stations, RAN/core health, failover, link faults),
**Network Topology** (the investigation graph and the real map).

**3D Digital Twin.** Scroll zooms where the mouse points and goes much closer; right-drag moves the
view; **Zoom to** flies to the selected node; **Full screen**. Clicking a device opens tabs **Overview,
Security** (alerts and incidents), **Network** (links, re-wire to another satellite or tower) and
**Configure** (name, ranges, location). **Design network** opens the network builder under the twin.

**New API:** `GET /api/soc/overview`, `GET /api/soc/rules`, `PUT /api/soc/rules/{id}`,
`POST /api/soc/rules/{id}/test`, `GET /api/soc/alerts`, `GET /api/soc/alerts/{id}`,
`POST /api/soc/alerts/{id}/action`. New tables: `alert_triage`, `alert_activity`, `rule_settings`.

## 29. Version 2.1 (stages 2 to 4): hunting, intelligence, AI analyst, roles

Full write-up for a supervisor or report: `docs/FINAL_REPORT.md`. Everything below runs on simulated data;
no real device, network or satellite is ever attacked, and quarantine stays a simulated isolation.

**Security event store and Threat Hunting.** Every login, publish, connection, 5G and GNSS event is stored
with source/destination address and port, protocol, MQTT client, topic, outcome and a SIM / LAB label
(normal MQTT traffic is summarised as one flow record per device per minute). The **Threat Hunting** page
searches it with a small query language (`type:mqtt_auth_failure src:203.0.113.* -outcome:success
bytes:>1000000 "text"`), time ranges, a timeline, top values, saved (and shared) queries, ready-made hunts
and CSV / JSON export.

**New simulated scenarios and rules CS-011..CS-021.** MQTT brute force, credential compromise, unauthorized
publish, port scan, botnet beaconing (regular intervals), data exfiltration, 5G authentication attack,
config tampering, GNSS jamming and GNSS spoofing. All use RFC 5737 documentation addresses
(203.0.113.x, 198.51.100.x) so nothing real is ever named. **Satellite & 5G Security** has a GNSS panel.
The top bar has an **environment selector** (Simulation / Lab / Production; Production shows that no
production source is connected).

**Threat Intelligence.** Local IOC list (address, domain, hash, URL) with sightings, and look-ups through
VirusTotal, AbuseIPDB and AlienVault OTX when their keys are set in `.env` (cached 24 h, keys never reach the
browser, private and documentation addresses are never sent out).

**AI SOC Analyst.** Pick an alert or incident (or ask a question). The analyst calls read-only tools
(`search_security_events`, `get_device_information`, `get_network_connections`, `analyze_alert`,
`correlate_events`, `get_threat_intelligence`, `recommend_response`, `generate_incident_report`), and every
claim cites evidence `[E1]`, `[E2]` ... that you can click. With an AI key the language model writes the
answer from that evidence only (answers without valid citations are rejected); without a key a built-in
analyst writes it. `create_incident` and `request_device_isolation` are only **proposed**: a person
presses Confirm, and isolation still waits for approval.

**Incident Management.** Seven phases Detection → Triage → Investigation → Containment → Eradication →
Recovery → Closure (one step at a time, closure needs a note), MITRE ATT&CK mapping, an evidence panel,
playbooks PB-01..PB-05 whose steps run in order, AI investigations, the timeline and a Markdown report.

**Roles, 2FA, approvals, audit.** New roles SOC analyst L1 / L2 / L3 and SOC manager (table in the final
report). Device isolation requested by L2, a playbook, the AI or the demo waits on the **Approvals** page
(optional two-person rule). Two-factor login with any authenticator app (TOTP), needed again to approve a
containment. The audit log is hash-chained: **Audit Logs → Verify integrity** shows any edited or deleted
row.

**End-to-end demo** (Operations → Demo Scenario): attack → events → detection → incident → AI analysis →
**your approval** → containment → eradication → recovery → closure and a downloadable report.

**New accounts:** `analyst_l1 / AnalystL1@2026`, `analyst_l2 / AnalystL2@2026`, `analyst_l3 / AnalystL3@2026`,
`soc_manager / Manager@2026`. New `.env` keys are listed at the end of `.env.example`.

## 30. Version 2.2: Huawei Cloud, IoTDA, ModelArts and the lab test

Step-by-step guide: `docs/HUAWEI_INNOVATION.md`.

* **Huawei IoTDA.** The ESP32 can connect to Huawei Cloud IoTDA (`USE_IOTDA 1` in `config.h`). An IoTDA data
  forwarding rule pushes each reading to `POST /api/iotda/push?token=...` (`IOTDA_PUSH_TOKEN` in `.env`), and
  it then follows the normal path: validation, detection, ML, dashboard. Readings are labelled LAB.
* **ModelArts / MindSpore anomaly model.** `ml/modelarts/train.py` trains an autoencoder on normal readings
  (exported `telemetry.csv`) as a ModelArts training job and writes `anomaly_ae.json`. Put it in
  `backend/models/` and press **Reload model file**. The app runs the model in plain Python (no MindSpore on the
  server). The shipped starter model was trained locally with the NumPy version of the same network on
  simulated data: replace it with your ModelArts model.
* **Lab test report.** System Health → **Huawei Cloud and lab test** measures real boards only: delivery %,
  send interval, outages, value ranges and alerts. **Report** downloads it as Markdown (`GET /api/lab/report`).
* **Fix:** real ESP32 readings (`esp32/mqtt`) are now counted as LAB everywhere (they were counted as
  simulation in the SOC overview).

## 31. Version 2.6: AI analyst on DeepSeek

Step-by-step guide: `docs/DEEPSEEK_AI.md`.

* **DeepSeek is the default AI.** Provider `deepseek` calls `https://api.deepseek.com/chat/completions`
  (OpenAI-compatible) with model `deepseek-chat`. Put the key in **Administration -> AI assistant** or in
  `.env` as `DEEPSEEK_API_KEY`.
* **Same safety as before.** No key or an error -> the offline analyst answers. The key is never sent to the
  browser. The analyst only suggests commands.
* Huawei Cloud MaaS (`AI_PROVIDER=huawei`) and Gemini/Groq/OpenRouter/OmniRoute still work from `.env`.
* New tests: `backend/tests/test_v26.py`.
