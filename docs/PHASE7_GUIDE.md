# Phase 7 — 3D Digital Twin

**Goal:** show the whole simulated network as an interactive 3D scene: the
Earth, an orbiting satellite, the ground station, the 5G tower, the telecom
core, the security server and the IoT devices. Every object takes its colour
from the live state, so the scene is a **digital twin** of the simulation.

**Status:** tested in Chromium. The scene loads, links animate, quarantined
devices show a red cage, clicking an object opens the inspector, and there are
no browser errors. The page also fits a phone screen.

> The globe, positions and orbit are **illustrative**. They are not real
> coordinates, and the orbit is not to scale.

---

## 1. What you see

| Object | Shape | Colour means |
|---|---|---|
| Earth | Textured globe drawn in code (no image download) with a blue atmosphere | — |
| SAT-1 | Satellite with solar panels, sweeping along the dashed orbit | green online · amber degraded · red offline |
| GS-1 | Ground station dish | same |
| BS-5G | 5G tower with antenna rings | same |
| CORE | Three server racks | same |
| SEC | Server with a blue crystal on top | same |
| IoT devices | Sensor on a pole | green online · grey offline · orange suspicious · **red + rotating red cage = quarantined** |

**Links**

* **Green moving dashes + small dots** = traffic is flowing on this link now
* **Amber, slower** = degraded link (rain fade or manual "Degrade")
* **Red dashed** = link down
* **Grey dashed** = backup link on standby (used for failover in Phase 8)
* **Dark red** = blocked because a device is quarantined

**Controls:** drag to rotate, scroll to zoom, and click an object to inspect it.
**Reset view** puts the camera back. **Labels** turns the name tags on or off.

**Inspector (right side)**

* IoT device: status, security state, temperature, humidity, battery,
  messages, route to the core, path latency, and a **Quarantine / Release** button.
* Infrastructure: status, every link with latency and packet loss, and the
  **Normal / Degrade / Take offline** buttons.

Everything you do in the 3D view (for example taking SAT-1 offline) changes the
same simulation as the 2D map, so both views always agree.

---

## 2. Set up Phase 7

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase7.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase7` and open it in VS Code.
3. Check the Explorer. If `backend`/`frontend` are at the top, use `cd backend` / `cd frontend`. Otherwise put `CyberShield-SatCom-3D\` in front.
4. **Terminal 1:**
```
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v0.7.0 ready`.
5. **Terminal 2.** `npm install` now also downloads Three.js, so it takes a bit longer:
```
cd frontend
npm install
npm run dev
```
6. Open **http://localhost:5173**. The 3D panel is just under the simulation controls.

New packages: `three`, `@react-three/fiber` (React renderer for Three.js),
`@react-three/drei` (helpers: orbit controls, stars, curved lines).

### Changed and new files

```
frontend/
├── package.json                    CHANGED  three, @react-three/fiber, @react-three/drei
└── src/
    ├── App.jsx                     CHANGED  shows the 3D panel
    ├── components/TwinPanel.jsx    NEW      panel, inspector, legend
    ├── components/NetworkPanel.jsx CHANGED  StateButtons shared with the 3D inspector
    ├── styles/global.css           CHANGED
    └── three/
        ├── layout.js               NEW  positions (lat/lon), orbit, colours
        ├── earthTexture.js         NEW  draws the Earth texture on a canvas
        ├── Earth.jsx               NEW  globe + atmosphere
        ├── OrbitRing.jsx           NEW  dashed orbit
        ├── Satellite.jsx           NEW  moving satellite
        ├── NodeModel.jsx           NEW  ground station, tower, servers, devices, quarantine cage
        ├── LinkLine.jsx            NEW  curved animated links + data packets
        ├── Label.jsx               NEW  name tags (canvas sprites)
        └── TwinScene.jsx           NEW  the Canvas: lights, stars, camera, everything together
backend/app/config.py, routes/system.py   CHANGED  version 0.7.0, "3D twin ready"
```

### How it works (for your report)

* `TwinScene` receives the same **network snapshot** that the backend pushes
  over the WebSocket every 2 seconds (`nodes`, `links`, `routes`). It doesn't
  have its own data, so it can never disagree with the backend.
* Ground nodes have fixed positions from latitude/longitude (`layout.js`).
  The satellite's position changes every frame (`useFrame`). Links attached to
  it update their curve each frame through a shared position object.
* A link counts as **"in use"** when it is on a device's current route, or it
  is the core → security server link (monitoring traffic). Only links in use
  show moving traffic.
* The 3D code is **lazy-loaded** (`React.lazy`), so the rest of the dashboard
  appears immediately while Three.js loads.

---

## 3. Test Phase 7

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Scene loads | Open the dashboard | Globe, stars, dashed orbit, SAT-1 moving slowly, labels on all nodes |
| 2 | Traffic | Look at the links | Green moving dashes and dots on IOT → SAT-1 → GS-1 → CORE and IOT-002 → BS-5G → CORE; grey dashed backup links |
| 3 | Rotate / zoom | Drag, scroll | Camera orbits the globe; **Reset view** returns |
| 4 | Inspect a device | Click IOT-003 | Inspector shows readings, route `IOT-003 → SAT-1 → GS-1 → CORE` and latency |
| 5 | Inspect infrastructure | Click SAT-1 | Its links with latency and loss, and the state buttons |
| 6 | Failure in 3D | SAT-1 → **Take offline** | SAT-1 and its links turn red; IOT-001/003 routes say "no route to core"; the 2D map shows the same |
| 7 | Degrade | GS-1 → **Degrade** | Amber links, slower packets |
| 8 | Quarantine visual | Run **Excessive traffic** on IOT-002 | IOT-002 turns red with a rotating red cage and `[Q]` label; its link turns dark red |
| 9 | Release from 3D | Click IOT-002 → **Release** | Cage disappears, traffic flows again |
| 10 | Labels | Untick **Labels** | Name tags disappear |
| 11 | Phone | Narrow the browser window | 3D view on top, inspector below, no sideways scroll |

If all 11 pass, Phase 7 is done.

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| "3D view needs WebGL" | Use Chrome or Edge; Settings → System → turn on **Use graphics acceleration** |
| Black box, nothing appears | Wait a few seconds the first time (Three.js is loading). Check the browser console (F12) |
| `Cannot find module 'three'` | You skipped `npm install` in the new folder |
| Scene is slow on a weak laptop | Untick **Labels**, make the window smaller |
| Terminal shows `THREE.Clock deprecated` warning | Harmless, comes from the library |

---

## Next: Phase 8 — Satellite to 5G failover

When the satellite path fails, devices automatically switch to the backup 5G
link. You'll see the handover in 3D, measure how long it takes and how much
data was lost, and compare it with failover switched off.
