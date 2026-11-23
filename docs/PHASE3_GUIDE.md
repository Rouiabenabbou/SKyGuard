# Phase 3 — MQTT Integration

**Goal:** IoT data travels the way it does in real IoT systems: devices publish
to an **MQTT broker** (Mosquitto), and the backend subscribes.

**Status:** tested with a real Mosquitto 2 broker. The following were all checked:
* the built-in and standalone simulators both publish through the broker
* bad JSON, an unknown device, a device-ID mismatch and an out-of-range field are each rejected and logged
* a device that vanishes is announced offline by the broker ("last will")
* stopping the broker switches the app to direct mode; restarting it reconnects by itself

---

## 1. What MQTT is and why we use it

MQTT is a lightweight **publish/subscribe** protocol designed for IoT:

* A **broker** (Mosquitto) sits in the middle.
* Devices **publish** messages to a **topic**, like a channel name.
* Anyone interested **subscribes** to that topic.
* Devices and the backend never talk to each other directly, so you can add
  devices, or replace the simulator with a real ESP32, without changing the backend.

```
 IOT-001 ─┐  publish                           subscribe ┌──────────────┐
 IOT-002 ─┼──────────► ┌────────────────────┐ ─────────► │ FastAPI      │──► SQLite
 IOT-003 ─┘            │ Mosquitto broker   │            │ backend      │──► WebSocket ──► Dashboard
 (ESP32 later)         │ localhost:1883     │ ◄───────── │              │
                       └────────────────────┘  publish   └──────────────┘
                                               network/events
```

### Topics

| Topic | Direction | Content |
|---|---|---|
| `cybershield/iot/<device_id>/telemetry` | device → backend | JSON reading |
| `cybershield/iot/<device_id>/status` | device → backend | `online` / `offline` |
| `cybershield/network/events` | backend → anyone | every event from the event log |
| `cybershield/security/alerts` | backend → anyone | security alerts (Phase 5) |

The backend subscribes to `cybershield/iot/+/telemetry`. The `+` is a wildcard
that matches any device ID.

Example telemetry message:

```json
{"device_id": "IOT-001", "temperature": 34.2, "humidity": 21.5, "battery": 88.0, "source": "simulator"}
```

### What the backend checks on every message

1. Is it valid JSON? If not: `invalid_message` event.
2. Does the `device_id` in the message match the topic? If not: `device_id_mismatch` (security) event.
3. Is the device registered? If not: `unknown_device_message` (security) event. Phase 5 turns this into an alert.
4. Are all fields present and physically possible (humidity 0–100 %…)? If not: `invalid_message` event.
5. Otherwise: store, update the device, push to the dashboard.

### "Last will": detecting dead devices

When a device connects, it gives the broker a **last will** message
(`offline`). If the device disappears without saying goodbye (power cut,
crash, out of range), the broker publishes that message for it, and the
dashboard marks the device offline.

### Works without the broker too

If Mosquitto isn't running, the backend keeps retrying in the background, and
the built-in simulator sends readings **directly** instead. The dashboard
shows which path is in use.

---

## 2. Install Mosquitto (Windows)

1. Download the **64-bit Windows installer** from https://mosquitto.org/download/
2. Run it with the default options. It installs to `C:\Program Files\mosquitto`.
3. Check it:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -h
```

You should see `mosquitto version 2.x` and a list of options.

(macOS: `brew install mosquitto`. Ubuntu: `sudo apt install mosquitto mosquitto-clients`.)

---

## 3. Set up the Phase 3 project

Same as last time:

1. Stop all running servers (**Ctrl+C** in each terminal).
2. Unzip **CyberShield-SatCom-3D-phase3.zip** to a new folder, for example `D:\PROJECT\CyberShield-SatCom-3D-phase3`.
3. In VS Code: **File → Open Folder**, and pick the folder that contains `backend` and `frontend`.

Changed and new files:

```
backend/
├── requirements.txt          CHANGED  adds paho-mqtt
└── app/
    ├── config.py             CHANGED  MQTT settings
    ├── main.py               CHANGED  starts the MQTT client
    ├── mqtt_topics.py        NEW      all topic names in one place
    ├── mqtt_client.py        NEW      connect, subscribe, validate, reconnect, publish
    ├── event_log.py          CHANGED  also publishes events to MQTT
    ├── device_simulator.py   CHANGED  source label "builtin"
    ├── simulation_controller.py CHANGED sends through MQTT if connected, else direct
    └── routes/system.py      CHANGED  GET /api/mqtt/status
iot/simulator/
├── mqtt_simulator.py         NEW      standalone devices + test scenarios
└── requirements.txt          NEW
frontend/src/
├── App.jsx                   CHANGED  MQTT broker card
├── services/api.js           CHANGED  mqttStatus()
├── hooks/useLiveData.js      CHANGED  tracks MQTT status
├── components/SimulationControls.jsx CHANGED shows the data path
├── components/TelemetryTable.jsx     CHANGED "builtin via mqtt" labels
└── styles/global.css         CHANGED
```

---

## 4. Run it (three terminals)

Click **+** in the terminal panel to open each new terminal.

**Terminal 1: MQTT broker**

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -v
```

You should see `Opening ipv4 listen socket on port 1883`. Leave it open.
`-v` (verbose) prints every connection, which is handy for learning.

> If it says **"Only one usage of each socket address"**, Mosquitto is already
> running as a Windows service. That's fine: skip this terminal.

**Terminal 2: backend**

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

You should see:

```
[mqtt] connecting to localhost:1883 ...
[startup] CyberShield SatCom 3D v0.3.0 ready
[mqtt] connected, subscribed to cybershield/iot/+/telemetry and cybershield/iot/+/status
```

**Terminal 3: frontend**

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The **MQTT broker** card should say
**Connected**, and the data path should show
`Built-in simulator → MQTT broker → Backend → SQLite + Dashboard`.

---

## 5. The standalone simulator (`iot/simulator/mqtt_simulator.py`)

A separate program that behaves like real devices: each one has its own MQTT
connection and last will. Open a **4th terminal** in the project root folder:

```powershell
backend\venv\Scripts\Activate.ps1
python iot\simulator\mqtt_simulator.py --help
```

| Scenario | Command | What happens |
|---|---|---|
| Normal | `python iot\simulator\mqtt_simulator.py` | 3 devices, a reading every 5 s each (Ctrl+C to stop) |
| Excessive traffic (A) | `... --scenario flood --device IOT-002 --rate 20` | 20 msg/s for 15 s |
| Unauthorized device (B) | `... --scenario unauthorized` | IOT-999 publishes; rejected and logged 🛡️ |
| Abnormal readings (C) | `... --scenario abnormal --device IOT-001` | ~85 °C, ~2 % humidity |
| Connection storm (D) | `... --scenario connstorm --device IOT-002 --count 20` | 20 quick connect/disconnects |
| Silent disconnect | `... --scenario disconnect --device IOT-003` | Sends for 15 s, then vanishes; broker announces it offline |

> **Before the "normal" scenario, click Pause on the dashboard.** Otherwise the
> built-in simulator and this one send for the same device IDs at the same
> time. The other scenarios are short and can run alongside it.

These scenarios only produce data and events in Phase 3. The **detection
engine (Phase 5)** will turn them into security alerts.

All scenarios run only on your own computer's broker. They are simulations
for testing, not tools for attacking real systems.

---

## 6. Test Phase 3

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Broker running | Terminal 1 | `Opening ipv4 listen socket on port 1883` |
| 2 | Backend connects | Terminal 2 | `[mqtt] connected, subscribed to ...` |
| 3 | Dashboard | Browser | MQTT card **Connected**; data path shows **MQTT broker** |
| 4 | Data goes through MQTT | Live telemetry table | Source column says **builtin via mqtt** |
| 5 | Watch raw MQTT traffic | `& "C:\Program Files\mosquitto\mosquitto_sub.exe" -t "cybershield/#" -v` | JSON messages scroll by every ~2 s |
| 6 | Publish by hand | `& "C:\Program Files\mosquitto\mosquitto_pub.exe" -t cybershield/iot/IOT-002/telemetry -m '{\"temperature\":21,\"humidity\":50,\"battery\":90}'` | New IOT-002 row, source **device via mqtt** |
| 7 | Bad message rejected | Same, with `-m "hello"` | Event: *Invalid JSON on cybershield/iot/IOT-002/telemetry*; "rejected" count goes up |
| 8 | Unauthorized device | Run the `unauthorized` scenario | 🛡️ *Message from unregistered device IOT-999* events |
| 9 | Standalone devices | Pause, then run the `normal` scenario | Source **simulator via mqtt** |
| 10 | Last will | Run the `disconnect` scenario | ~8 s after it goes silent: *Agri Field 03 (IOT-003) reported offline via MQTT* |
| 11 | Broker failure | Press Ctrl+C in Terminal 1 | MQTT card **Offline**; path shows *(broker offline, sending direct)*; data keeps coming (**builtin via direct**) |
| 12 | Broker recovery | Start Mosquitto again | Within ~10 s: card **Connected**, source back to **builtin via mqtt** |

Test 6 tip: Windows PowerShell 5 needs `\"` inside the JSON, as shown. If you get an *Invalid JSON* event instead, you have PowerShell 7: use plain quotes, `-m '{"temperature":21,"humidity":50,"battery":90}'`.

If all 12 pass, Phase 3 is done.

---

## 7. Optional: MQTT Explorer

**MQTT Explorer** (https://mqtt-explorer.com) is a free GUI that shows every
topic as a tree with live values. Connect it to `localhost`, port `1883`.
It makes a nice screenshot for your report.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `mosquitto.exe` is not recognized | Use the full path in quotes with `&` in front, as shown above |
| "Only one usage of each socket address" | Mosquitto already runs as a service. That's fine, skip Terminal 1 |
| MQTT card stays **Offline** | Broker not running, or a firewall blocks port 1883. Check Terminal 1 |
| `ModuleNotFoundError: No module named 'paho'` | Activate the venv, then `pip install -r requirements.txt` (in `backend`) |
| Simulator: "Cannot connect to the MQTT broker" | Start Mosquitto first |
| Readings appear twice as often as expected | Built-in and standalone simulators both running. Click **Pause** on the dashboard |
| Lots of 🛡️ events | Expected after the unauthorized or bad-message tests. **Reset** clears them |

---

## Next: Phase 4 — Network simulation

The satellite–5G topology: satellite, ground station, 5G base station, telecom
core and security server, connected by links with latency, packet loss and
bandwidth that change over time.
