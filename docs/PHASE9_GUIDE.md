# Phase 9 — 4D Timeline (time is the 4th dimension)

**Goal:** make the twin **4D**. The three dimensions show *where* everything is,
and the fourth shows *when*. The backend records the complete state of the twin
every 2 seconds. A timeline under the 3D scene can rewind, play, pause, change
speed and jump from event to event, and the 3D scene shows exactly what the
network looked like at that moment.

**Status:** tested. A session with a flood attack, auto-quarantine and a
satellite outage drill was replayed in 3D. The REPLAY badge appeared, the
event markers worked, and prev/next event and play/pause worked. The moment
panel showed *quarantined 1, on backup 5G 2* at the right time. There are no
browser errors.

---

## 1. How it works

```
every 2 s while running                         dashboard
network tick ──► timeline_service.record() ──► state_snapshots table
                 (one compact JSON "frame")            │
                                                       ▼
                                         GET /api/timeline/frames  ──► useTimeline()
                                                                        │ cursor (a moment)
                                                                        ▼
                                                   frame → network snapshot → 3D scene
```

A **frame** (about 1.5 KB) holds, for one moment:

* every node's status (satellite, ground station, tower, servers, devices)
* every link: status, latency, packet loss, carrying traffic?, blocked?
* every device's route (primary / backup / switching / down / quarantined)
* every device's readings and security state
* network availability and the number of open alerts

The dashboard turns a frame back into the same shape as the live data
(`services/timeline.js`), so **the same 3D scene** draws both live and past
states. The **events** (`network_events` table, filled since Phase 2) appear as
coloured markers on the timeline.

Storage: one frame every 2 s is about 1,800 frames an hour. Above
`TIMELINE_MAX_SNAPSHOTS` (default 5400, about 3 hours) the oldest are deleted.
**Reset** clears the timeline together with the other data.

---

## 2. Set up Phase 9

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase9.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase9` and open it in VS Code.
3. **Terminal 1:**
```
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v0.9.0 ready`.
4. **Terminal 2:**
```
cd frontend
npm install
npm run dev
```
5. Open **http://localhost:5173**. The timeline sits under the 3D scene, in the panel now called **4D digital twin**.

### Changed and new files

```
backend/app/
├── timeline_service.py      NEW      builds and stores frames, thins them out, prunes old ones
├── routes/timeline.py       NEW      /api/timeline/range, /frames, /at
├── models.py                CHANGED  new state_snapshots table
├── network_simulator.py     CHANGED  records a frame every tick
├── simulation_controller.py CHANGED  Reset clears the timeline
├── config.py                CHANGED  TIMELINE_MAX_SNAPSHOTS, version 0.9.0
└── main.py                  CHANGED
frontend/src/
├── hooks/useTimeline.js        NEW  live/replay, frames, cursor, play, speed, jump to event
├── services/timeline.js        NEW  find frame at a time; frame → network/devices
├── components/TimelinePanel.jsx NEW  buttons, slider with event markers, "at this moment"
├── App.jsx                     CHANGED  the 3D twin shows the replayed moment
├── services/api.js, styles/global.css  CHANGED
```

---

## 3. Using the timeline

| Control | What it does |
|---|---|
| **● Live** | Back to the live state |
| **⏪ Replay** | Loads the recorded frames for the chosen range; the 3D scene shows **REPLAY** |
| Range menu | Last 10 min / 30 min / 2 h / everything |
| Slider | Drag to any moment |
| Coloured marks | Events: red = security, amber = network/failover, blue = device, grey = system. Click one to jump to it |
| ⏮ / ⏭ | Previous / next event |
| ▶ Play / ⏸ Pause | Plays the recording at 1×, 2×, 5×, 10× or 30× speed |
| **⟳ Reload** | Fetches frames recorded since you started replaying |
| "At this moment" | Availability, open alerts, quarantined devices, devices on backup 5G, and the last 5 events |

In replay the inspector still works (click any object to see its values at that
moment), but the action buttons are hidden, because you cannot change the past.

---

## 4. Test Phase 9

Make some history first: let it run for 20 s, run **Excessive traffic** on
IOT-002, wait 15 s, run the **Satellite outage drill**, and wait until it ends.

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Recording | http://127.0.0.1:8000/api/timeline/range | `count` grows by about 1 every 2 s |
| 2 | Enter replay | **⏪ Replay** | REPLAY badge on the 3D scene; slider at the first frame; markers on the track |
| 3 | Before the attack | Drag to the start | IOT-002 green, all routes primary |
| 4 | The attack | ⏭ until the red markers | IOT-002 turns red with the cage `[Q]`; "Open alerts" and "Quarantined 1" |
| 5 | The outage | ⏭ to the amber markers | SAT-1 and its links red, then IOT-001/003 on the 5G links; "On backup 5G 2" |
| 6 | Play | **▶ Play** at 5× | The scene changes by itself: outage, failover, recovery, failback |
| 7 | Speed | Change to 30× | Playback much faster; stops at the end |
| 8 | Inspect the past | Pause during the outage, click IOT-001 | Route `IOT-001 → BS-5G → CORE`, mode backup |
| 9 | Back to live | **● Live** | Badge disappears, live state again |
| 10 | Reset | **Reset** in the simulation controls, then Replay | Only the new session is recorded |

If all 10 pass, Phase 9 is done.

### For your report

The 4D timeline turns the dashboard from "what is happening now" into a tool
for **incident analysis**. After an attack you can go back and see the order of
events (detection → quarantine → recovery) and how long each step took, in the
same 3D view.

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| "Nothing recorded yet" | The simulation must be **running**; frames are not recorded while it is paused |
| Replay ends before the latest events | Press **⟳ Reload** |
| Markers bunch together | Choose a shorter range (Last 10 min) |
| Database gets large | Lower `TIMELINE_MAX_SNAPSHOTS` in `.env`, or press Reset |

---

## Next: Phase 10 — Full dashboard

The dashboard is reorganised into tabs (Overview, 4D Twin, Network, Security,
Data). It gets real charts (Recharts) for temperature, humidity, latency,
packet loss, availability and alerts, plus CSV exports and a session report.
