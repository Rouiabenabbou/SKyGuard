# Phase 5 — Cybersecurity Detection

**Goal:** a detection engine that watches every message and every network
change, and raises **security alerts** with a severity level. The alerts are
stored in SQLite, published on MQTT and shown live on the dashboard.

**Status:** tested end to end:
* all four simulated attacks (flood, unauthorized device, abnormal reading, connection storm) were detected
* spoofed device IDs, malformed messages and link/node failures were detected
* **45 seconds of normal traffic produced 0 false alerts**
* no browser errors, and the page fits a phone screen

> All attacks are simulated inside this project. Nothing is sent to real
> devices, networks or satellites.

---

## 1. How detection works

```
 MQTT / simulator ──► telemetry_service ──► detection_engine ──► security_alerts (SQLite)
                         │  Rule A: rate          │                 │
                         │  Rule B: registered?   ├──► WebSocket "alert" ──► dashboard + pop-up
                         │  Rule C: ranges        ├──► MQTT cybershield/security/alerts
 MQTT status ───────────►│  Rule D: connections   └──► event log (category "security")
 network simulator ─────►│  Rule E: link/node offline
```

The engine is **rule-based**. Every decision can be explained in one
sentence, which matters for a security report. (Machine learning is an
optional extension, planned after Phase 12.)

### The rules

| Rule | Alert type | Fires when | Severity | Default threshold |
|---|---|---|---|---|
| A | `excessive_message_rate` | a device sends more than X msg/s over a 5 s window | high | 10 msg/s (normal is 0.2 msg/s) |
| B | `unauthorized_device` | a device ID not in the registry sends data | high | — |
| C | `abnormal_sensor_value` | temperature or humidity outside the device's allowed range | medium, or **high** if 15+ units outside | per device |
| D | `suspicious_connections` | a device connects more than N times in 30 s | high | 5 connections |
| E | `link_failure` / `node_failure` | a link or node goes offline | high / **critical** (satellite, core, nodes) | — |
| extra | `device_id_spoofing` | the ID in the message differs from the MQTT topic | high | — |
| extra | `malformed_message` | not valid JSON / missing or impossible fields | low | — |

Allowed ranges per device (Rule C):

| Device | Temperature | Humidity |
|---|---|---|
| IOT-001 (desert) | 0–50 °C | 5–70 % |
| IOT-002 (office) | 15–32 °C | 25–70 % |
| IOT-003 (farm) | −5–45 °C | 20–95 % |

### Anti-spam: cooldown

The same alert for the same device (or link) is **not repeated within 30 s**.
A 20 msg/s flood produces one clear alert, not 160.

### What an alert contains

`id`, `device_id`, `alert_type`, `severity` (low / medium / high / critical),
`description`, `timestamp`, `detection_method` (`rule`), `status` (`open` / `resolved`).

### Effect on devices

A registered device involved in a **high** or **critical** alert gets
`security_status = "suspicious"` (amber tag on its card). **Phase 6** adds
quarantine for suspicious devices.

---

## 2. Set up Phase 5

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase5.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase5` and open it in VS Code.
3. Look at the Explorer on the left:
   * `backend` and `frontend` at the top: use `cd backend` and `cd frontend`
   * only a `CyberShield-SatCom-3D` folder: use `cd CyberShield-SatCom-3D\backend` and `cd CyberShield-SatCom-3D\frontend`
4. **Terminal 1 (backend):**
```
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v0.5.0 ready`.
5. **Terminal 2 (frontend):**
```
cd frontend
npm install
npm run dev
```
6. Open **http://localhost:5173**.

Mosquitto keeps running in the background as a Windows service.

### Changed and new files

```
backend/app/
├── config.py               CHANGED  detection thresholds
├── detection_engine.py     NEW      all rules, cooldown, alert storage/broadcast
├── attack_simulator.py     NEW      built-in simulated attacks for the buttons
├── telemetry_service.py    CHANGED  calls rules A, B, C
├── mqtt_client.py          CHANGED  calls rule D + spoofing/malformed checks
├── network_simulator.py    CHANGED  calls rule E
├── simulation_controller.py CHANGED Reset also clears alerts
├── main.py                 CHANGED  registers alert routes
└── routes/
    ├── alerts.py           NEW      /api/alerts, /api/alerts/stats, resolve
    └── simulation.py       CHANGED  /api/simulation/attack/...
frontend/src/
├── App.jsx                       CHANGED  alerts card, security row, pop-ups
├── services/api.js               CHANGED  alert + attack calls
├── hooks/useLiveData.js          CHANGED  live alerts and pop-ups
├── components/AlertsPanel.jsx    NEW      alert list with Resolve
├── components/AttackPanel.jsx    NEW      attack buttons
├── components/Toasts.jsx         NEW      pop-up notifications
├── components/DeviceCard.jsx     CHANGED  coloured security status
└── styles/global.css             CHANGED
```

---

## 3. New API endpoints

| Method | URL | What it does |
|---|---|---|
| GET | `/api/alerts?status=open&severity=high&limit=50` | Recent alerts, newest first (all filters optional) |
| GET | `/api/alerts/stats` | Totals by severity, type and status |
| POST | `/api/alerts/{id}/resolve` | Mark an alert as resolved |
| POST | `/api/simulation/attack/excessive-traffic?device_id=IOT-002` | 20 msg/s for 8 s |
| POST | `/api/simulation/attack/unauthorized-device` | IOT-999 sends 5 readings |
| POST | `/api/simulation/attack/abnormal-reading?device_id=IOT-001` | 3 readings at ~85 °C |
| POST | `/api/simulation/attack/connection-storm?device_id=IOT-003` | 12 reconnects |

New live message types: `alert`, `alert_update`.

The standalone simulator from Phase 3 (`iot\simulator\mqtt_simulator.py`)
triggers the same rules from outside the backend, for example
`--scenario flood` or `--scenario connstorm`.

---

## 4. Test Phase 5

| # | Scenario | How | Expected alert |
|---|---|---|---|
| 1 | Normal traffic | Click Reset, wait 1 minute | **No alerts** ("No open alerts. The network looks clean.") |
| 2 | Excessive message rate | Target IOT-002 → **Excessive traffic** | HIGH *Excessive message rate* within ~3 s + pop-up; IOT-002 → suspicious |
| 3 | Unauthorized device | **Unauthorized device** | HIGH *Unauthorized IoT device detected: 'IOT-999'...* |
| 4 | Abnormal sensor value | Target IOT-001 → **Abnormal reading** | HIGH *Abnormal sensor value* (temperature ~85 °C, allowed 0–50 °C) |
| 5 | Suspicious connections | Target IOT-003 → **Connection storm** | HIGH *Suspicious connections* (6+ connections in 30 s) |
| 6 | Link failure | Network map: click line SAT-1 ↔ GS-1 → **Take offline** | CRITICAL *Link failure* |
| 7 | Node failure | Click **BS-5G** → **Take offline** | CRITICAL *Node failure* (one alert, not one per link) |
| 8 | Spoofing | `& "D:\Program Files\mosquitto\mosquitto_pub.exe" -t cybershield/iot/IOT-002/telemetry -m '{\"device_id\":\"IOT-001\",\"temperature\":20,\"humidity\":40,\"battery\":90}'` | HIGH *Device ID spoofing* |
| 9 | Malformed message | Same tool with `-m "hello"` | LOW *Malformed message* (no pop-up for low) |
| 10 | Cooldown | Click **Excessive traffic** twice quickly | Only one alert |
| 11 | Resolve | Click **Resolve** on an alert | Moves out of "Open"; event "Operator resolved alert #..." |
| 12 | Stored in SQLite | Open http://127.0.0.1:8000/api/alerts/stats | Counts match the dashboard |
| 13 | MQTT topic | `& "D:\Program Files\mosquitto\mosquitto_sub.exe" -t cybershield/security/alerts -v`, then run an attack | Alert JSON appears |

Test 8: if you get a *Malformed message* alert instead, you're on PowerShell 7.
Use plain quotes inside the JSON (see the Phase 3 guide).

If all 13 pass, Phase 5 is done.

### Numbers for your report (simulated)

* **Detection time, flood:** the rule needs more than 50 messages in 5 s. At
  20 msg/s that's reached after about **2.5 s**. You can see it in the event
  log: compare the *[SIMULATION] Excessive traffic attack...* time with the
  alert time.
* **Detection time, unauthorized / abnormal / spoofing:** on the **first message** (well under 1 s).
* **Detection time, connection storm:** on the 6th connection, about **2 s** at the simulated speed.
* **False alerts in normal operation:** 0 in our test (normal rate 0.2 msg/s is
  50× below the threshold; normal values stay inside the ranges).

Phase 12 turns these into a full results table.

---

## 5. Tuning the thresholds

Create a `.env` file in the project root (copy `.env.example`) and change
for example:

```
RATE_THRESHOLD_PER_SEC=5
CONN_THRESHOLD=3
ALERT_COOLDOWN_SECONDS=10
```

Restart the backend. Lower thresholds catch attacks faster but risk more false
alerts. That trade-off is worth a paragraph in your report.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| No attack panel / alerts panel | Backend must say `v0.5.0`; refresh the browser with Ctrl+F5 |
| Attack button does nothing | Check Terminal 1 for errors; the backend must be running |
| No pop-up | Pop-ups only appear for high and critical alerts |
| Second click gives no new alert | That's the 30 s cooldown working as designed |
| Too many low alerts | They come from malformed test messages. **Reset** clears all alerts |

---

## Next: Phase 6 — Quarantine

Quarantine a suspicious device: its traffic is blocked, it turns red on the
dashboard (and later in 3D), and you can release it again. You'll get manual
Quarantine / Release buttons, plus optional automatic quarantine for critical alerts.
