# Phase 8 — Satellite → 5G Failover

**Goal:** keep IoT devices connected when the satellite path fails. When it
fails, traffic automatically moves to the backup 5G link. When the satellite
is healthy again, traffic moves back (failback). Every switch is measured,
recorded and shown in 2D and 3D.

**Status:** tested. With failover ON, a 25 s satellite outage cost each device
about 2.6 to 4 s of interruption (detection plus handover), and about 1 lost reading.
With failover OFF, the same outage cut IOT-001 off for 25 s, it lost 5
readings and went offline. There are no browser errors, and the page fits a phone screen.

> This is a **teaching model**. It is not a real 3GPP satellite / 5G handover
> procedure, and it does not control any real network. The handover time is
> simulated with a random value of 1.5 to 3 s.

---

## 1. How failover works

Each device can have two paths to the telecom core:

| Device | Primary path | Backup path |
|---|---|---|
| IOT-001 | IOT-001 → SAT-1 → GS-1 → CORE (satellite) | IOT-001 → BS-5G → CORE (5G) |
| IOT-003 | IOT-003 → SAT-1 → GS-1 → CORE (satellite) | IOT-003 → BS-5G → CORE (5G) |
| IOT-002 | IOT-002 → BS-5G → CORE (5G) | none |

Every 2 seconds, `failover_service.py` runs a small **state machine** for each device:

```
           primary path lost / degraded for 6 s
 PRIMARY ───────────────────────────────────────► SWITCHING ──(handover 1.5–3 s)──► BACKUP
    ▲                                                                                 │
    └────────── primary healthy for 10 s ("failback", no interruption) ◄──────────────┘

 no path at all ──► DOWN ──(a path comes back)──► PRIMARY or SWITCHING
```

* **Break before make** (the satellite is suddenly gone): the device has no
  connectivity until the handover finishes. Readings made in that time are **lost**.
* **Make before break** (degraded satellite, or failback): the old path keeps
  carrying traffic during the handover, so nothing is lost.
* **Interruption time** = how long the device really had no path. That is the
  detection delay (up to 2 s, one network tick) plus the handover time.

### Readings lost

The built-in simulator now checks the device's route before sending. If the
device has no path to the core (link down, handover in progress), the reading
never arrives and is counted as **lost**. This is how the dashboard shows the
value of failover: compare the "readings lost" figure with failover on and off.

### Settings (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `FAILOVER_ENABLED` | `true` | Also switchable on the dashboard |
| `HANDOVER_DELAY_MIN` / `MAX` | `1.5` / `3.0` | Simulated handover time, seconds |
| `FAILBACK_STABLE_SECONDS` | `10` | Primary must be healthy this long before failback |
| `FAILOVER_ON_DEGRADED` | `true` | Also fail over when the primary is degraded… |
| `DEGRADED_FAILOVER_SECONDS` | `6` | …for this long |
| `DRILL_SECONDS` | `30` | Length of the outage drill |

---

## 2. Set up Phase 8

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase8.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase8` and open it in VS Code.
3. Check the Explorer for the nested folder, as before.
4. **Terminal 1:**
```
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v0.8.0 ready`.
5. **Terminal 2:**
```
cd frontend
npm install
npm run dev
```
6. Open **http://localhost:5173**. The **Satellite → 5G failover** panel is next to the network map.

### Changed and new files

```
backend/app/
├── failover_service.py      NEW      state machine, timing, lost readings, statistics
├── routes/failover.py       NEW      status, history, on/off, outage drill
├── models.py                CHANGED  new failover_events table
├── network_simulator.py     CHANGED  finds primary AND backup paths; links get "role" and "in_use"
├── simulation_controller.py CHANGED  readings with no path are lost; Reset clears failover
├── config.py                CHANGED  failover settings, version 0.8.0
└── main.py                  CHANGED  registers failover routes
frontend/src/
├── components/FailoverPanel.jsx NEW
├── components/NetworkPanel.jsx  CHANGED  path badges (primary / backup 5G / switching / down)
├── components/NetworkMap.jsx    CHANGED  backup links light up when they carry traffic
├── three/TwinScene.jsx, NodeModel.jsx  CHANGED  cyan pulse during handover
├── hooks/useLiveData.js, services/api.js, App.jsx, styles/global.css  CHANGED
```

---

## 3. New API endpoints

| Method | URL | What it does |
|---|---|---|
| GET | `/api/failover/status` | On/off, settings, each device's mode, statistics |
| GET | `/api/failover/history?limit=50` | Failover / failback / outage records with times and lost readings |
| POST | `/api/failover/settings` | `{"enabled": false}` |
| POST | `/api/failover/drill?seconds=30` | Takes SAT-1 offline, then brings it back automatically |

New fields in the network snapshot: each route has `mode` (`primary`, `backup`,
`switching`, `down`, `quarantined`). Each link has `role` (`primary` or `backup`)
and `in_use`. New live message type: `failover`. New table: `failover_events`.

---

## 4. Test Phase 8

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Normal | Open the dashboard | All routes `primary`; backup links grey dashed |
| 2 | Drill with failover ON | **Satellite outage drill (30 s)** | IOT-001/003 show `switching` (cyan pulse in 3D) then `backup 5G`; routes `IOT-00x → BS-5G → CORE`; backup links turn active in 2D and 3D |
| 3 | Measured | Failover panel | failovers = 2; avg handover around 1.5–3 s; avg interruption around 2–5 s; 0–1 readings lost per device |
| 4 | Failback | Wait until the drill ends, plus 10 s | Events *FAILBACK … primary path healthy for 10 s*; routes back to `primary`; failback cut = 0.0 s |
| 5 | Failover OFF | Untick **Automatic failover**, run the drill again | IOT-001/003 `down`, "No route to core", readings lost keeps rising, devices go **offline** after 15 s |
| 6 | Restore | Wait for the drill to end | *connectivity restored after ~30 s (N readings lost)*, devices online again |
| 7 | Compare | Failover panel history | Outage with failover OFF ≈ 30 s cut; with ON ≈ 3 s. That's the result for your report |
| 8 | Degraded | Turn failover on; GS-1 → **Degrade** on the map | After about 6 s, the satellite devices move to 5G with **no** lost readings (make before break) |
| 9 | Manual | SAT-1 → **Take offline** in 3D or 2D | Same as the drill, but it stays offline until you click **Normal** |
| 10 | API | http://127.0.0.1:8000/api/failover/history | JSON records with `handover_ms`, `interruption_ms`, `readings_lost` |

If all 10 pass, Phase 8 is done.

### Numbers for your report (simulated)

* **Service interruption with failover:** about 2.6 to 4 s (up to 2 s detection plus 1.5 to 3 s handover).
* **Service interruption without failover:** the whole outage (30 s in the drill).
* **Data loss:** about 1 reading per device with failover, compared with about 6 without it, for a 30 s outage at one reading every 5 s.
* **Network availability** during the outage stays at 100 % with failover, once the handover is done.

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| No failover panel | Backend must say `v0.8.0`; refresh with Ctrl+F5 |
| Devices fail over by themselves now and then | That's the random rain fade degrading the satellite link for more than 6 s. Set `NET_RANDOM_EVENTS=false` in `.env` for a calm demo |
| IOT-002 never fails over | It has no backup path (5G only), by design |
| Drill button stays disabled | A drill is running; wait for the countdown |

---

## Next: Phase 9 — 4D timeline

Time becomes the fourth dimension. The backend records snapshots of the whole
twin, and a timeline slider replays any moment (attack, detection, quarantine,
failover) in the 3D scene.
