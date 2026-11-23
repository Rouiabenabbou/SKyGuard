# Phase 6 — Device Quarantine

**Goal:** when a device looks compromised, isolate it. Its traffic is blocked,
it is cut out of the network map, the dashboard shows it in red, and the
operator can release it again.

**Status:** tested end to end:
* auto-quarantine on a flood attack: about 70 messages were blocked within seconds, and none of them were stored
* manual Quarantine and Release buttons
* "Mark safe" for suspicious devices
* the auto-quarantine switch
* the MQTT command to the device
* the network map and routes showing isolated devices
* history records
* no browser errors, and the page fits a phone screen

> Quarantine is a **simulation inside this project**. It blocks the device's
> messages in our backend. It does **not** isolate a real device from a real
> telecom network.

---

## 1. What happens when a device is quarantined

```
 alert (flood / storm / spoofing) ──► auto-quarantine?  ─┐
 operator clicks "Quarantine"  ───────────────────────────┤
                                                          ▼
                                    quarantine_service.quarantine()
       ┌───────────────┬────────────────┬──────────────────┼────────────────────┬─────────────────┐
       ▼               ▼                ▼                  ▼                    ▼                 ▼
 security_status   new row in       event log        MQTT command on      dashboard: red     network: links
 = "quarantined"   quarantine_      "QUARANTINED"    .../IOT-002/command   card, 🔒, pop-up    blocked, no route
                   records                           {"action":"quarantine"}
```

From then on, **every message** from that device:

* still arrives (the device doesn't know it's isolated),
* still counts for the rate detector (so we see if the attack continues),
* is **blocked**: not stored, not shown as a reading, only counted in `blocked_messages`.

The 6 required steps from the project brief:

| Requirement | Where |
|---|---|
| 1. Generate a security alert | Phase 5 detection engine |
| 2. Status becomes "quarantined" | `quarantine_service.quarantine()` |
| 3. Block its normal traffic | `telemetry_service.ingest_telemetry()` returns `"quarantined"` |
| 4. Change its appearance | Red card + 🔒 on the map (and in 3D in Phase 7) |
| 5. Show a notification | Pop-up + event log + Quarantine panel |
| 6. Allow release | **Release** button / `POST /api/devices/{id}/release` |

### Automatic vs manual

* **Auto-quarantine** (switch in the Quarantine panel, on by default) isolates a
  device as soon as one of these alerts fires for it:
  `excessive_message_rate`, `suspicious_connections`, `device_id_spoofing`.
* **Abnormal sensor values** only mark the device *suspicious*, because a real
  fire or a broken sensor is not necessarily an attack. The operator decides:
  **Quarantine** or **Mark safe**.
* **Unauthorized devices** are not registered, so there is nothing to
  quarantine. Their messages are already rejected.

### Effect on the network

* A quarantined device's links are drawn **red dotted with 🔒**, and its route
  says *"Quarantined: traffic blocked on purpose"*.
* Quarantined devices are **left out of network availability**. Isolating them
  is a deliberate security action, not a network failure.

### Release

On release, the device is `normal` again, the record gets `released_at`, a
`release` command is published, and its detection history is cleared, so a
new attack is caught immediately.

---

## 2. Set up Phase 6

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase6.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase6` and open it in VS Code.
3. Check the Explorer. If `backend`/`frontend` are at the top, use `cd backend` / `cd frontend`. Otherwise put `CyberShield-SatCom-3D\` in front.
4. **Terminal 1:**
```
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v0.6.0 ready`.
5. **Terminal 2:**
```
cd frontend
npm install
npm run dev
```
6. Open **http://localhost:5173**.

### Changed and new files

```
backend/app/
├── config.py              CHANGED  AUTO_QUARANTINE settings
├── models.py              CHANGED  new QuarantineRecord table
├── quarantine_service.py  NEW      quarantine, release, block counting, auto mode
├── mqtt_topics.py         CHANGED  command topic
├── detection_engine.py    CHANGED  triggers auto-quarantine; forget_device()
├── telemetry_service.py   CHANGED  blocks quarantined devices
├── mqtt_client.py         CHANGED  blocked messages are not "rejected"
├── network_simulator.py   CHANGED  isolates quarantined devices
├── simulation_controller.py CHANGED Reset clears quarantine records
├── main.py                CHANGED  registers quarantine routes
└── routes/quarantine.py   NEW
frontend/src/
├── App.jsx                         CHANGED  Quarantined card, Quarantine panel
├── services/api.js                 CHANGED
├── hooks/useLiveData.js            CHANGED  quarantine state + pop-ups
├── components/QuarantinePanel.jsx  NEW
├── components/DeviceCard.jsx       CHANGED  red banner, Quarantine/Release/Mark safe
├── components/AlertsPanel.jsx      CHANGED  "Quarantine IOT-xxx" button on alerts
├── components/NetworkMap.jsx       CHANGED  🔒 nodes and blocked links
├── components/NetworkPanel.jsx     CHANGED  quarantined routes
└── styles/global.css               CHANGED
```

---

## 3. New API endpoints

| Method | URL | What it does |
|---|---|---|
| POST | `/api/devices/{device_id}/quarantine` | Quarantine (optional body `{"reason": "..."}`) |
| POST | `/api/devices/{device_id}/release` | Release; on a *suspicious* device it clears the flag ("Mark safe") |
| GET | `/api/quarantine` | Active quarantines + history (with blocked message counts) |
| GET | `/api/quarantine/settings` | Is auto-quarantine on? Which alert types trigger it? |
| POST | `/api/quarantine/settings` | `{"auto_quarantine": false}` |

New live message type: `quarantine` (actions `quarantined`, `released`, `blocked`).
New MQTT topic: `cybershield/iot/<device_id>/command`.

---

## 4. Test Phase 6

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Auto-quarantine | Target IOT-002 → **Excessive traffic** | Two pop-ups: *Excessive message rate* then *Device quarantined*; IOT-002 card red with 🔒 banner; Quarantined card = 1 |
| 2 | Traffic blocked | Watch the IOT-002 banner and the telemetry table | "N msgs blocked" keeps rising; **no new IOT-002 rows** in Live telemetry |
| 3 | Network isolation | Network map | IOT-002 🔒 red; its link dotted red with 🔒; route says *Quarantined*; availability stays 100 % (1 or 2 of 2 counted devices) |
| 4 | Release | **Release** on the IOT-002 card | Card back to normal, readings resume, "released (N messages were blocked)" event, record in History |
| 5 | Manual quarantine | **Quarantine** on the IOT-001 card | Red card, reason "manual quarantine by operator" |
| 6 | From an alert | On an alert, click **Quarantine IOT-xxx** | That device is quarantined with the alert as reason |
| 7 | Suspicious only | Target IOT-001 → **Abnormal reading** | IOT-001 *suspicious* (amber), **not** quarantined; buttons **Mark safe** and **Quarantine** |
| 8 | Mark safe | **Mark safe** | Back to *normal*; event "Operator cleared suspicion" |
| 9 | Auto off | Untick **Auto-quarantine**, run **Connection storm** | Alert + suspicious, but **no** quarantine |
| 10 | Command topic | `& "D:\Program Files\mosquitto\mosquitto_sub.exe" -t "cybershield/iot/+/command" -v`, then quarantine/release a device | `{"action": "quarantine"}` / `{"action": "release"}` |
| 11 | Stored | http://127.0.0.1:8000/api/quarantine | Active list + history with `blocked_messages`, `triggered_by`, times |
| 12 | Reset | **Reset** | All devices normal, quarantine list empty |

If all 12 pass, Phase 6 is done.

### Numbers for your report (simulated)

* **Response time** (alert → quarantine) in auto mode: the same second. Compare
  the alert and *QUARANTINED automatically* times in the event log.
* **Containment:** after quarantine, 100 % of the attacker's messages were
  blocked (none stored) in our test.

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| No Quarantine buttons | Backend must say `v0.6.0`; refresh with Ctrl+F5 |
| Device isn't auto-quarantined | Is the Auto-quarantine switch on? Abnormal readings never auto-quarantine (by design) |
| Attack again right after release gives no alert | It should alert: release clears the history. If not, wait for the attack to send more than 50 messages |
| Quarantined device shows "Offline" | It goes offline only if it stops sending entirely; blocked messages still count as "alive" |

---

## Next: Phase 7 — 3D Digital Twin

The big visual step: an interactive Three.js scene with the Earth, an orbiting
satellite, ground station, 5G tower, core servers, security server and IoT
devices. It has animated links coloured by status, red 🔒 devices for
quarantine, and click-to-inspect.
