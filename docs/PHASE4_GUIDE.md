# Phase 4 — Satellite–5G Network Simulation

**Goal:** model the telecom network that carries the IoT data. That means a
satellite, a ground station, a 5G base station, the telecom core and a
security server, connected by links whose latency, packet loss and bandwidth
change live.

**Status:** tested end to end. All 9 links reported live numbers. Taking the
satellite offline cut IOT-001 and IOT-003 off from the core (availability
33.3 %), and setting it back to Normal restored 100 %. Random rain fades
showed up as degraded links. No browser errors, and the page fits a phone screen.

> This is a simplified teaching model. It does **not** implement a real
> satellite handover protocol or a real 5G core network. All values are simulated.

---

## 1. The network

```
                    🛰 SAT-1  (LEO satellite)
                   /   |     \
     satellite   /     |      \  satellite feeder link
               /       |       \
        IOT-001     IOT-003     📡 GS-1 (ground station)
          :  \        :              |
  backup  :   \       :  backup      | fiber
  (5G)    :    \      :              |
        🗼 BS-5G ── fiber ──────── 🖧 CORE (telecom core) ── LAN ── 🛡 SEC (security server)
           |
         5G radio
           |
        IOT-002
```

| Node | Type | Role |
|---|---|---|
| SAT-1 | satellite | Low-Earth-orbit satellite serving remote devices |
| GS-1 | ground_station | Receives satellite traffic, forwards it over fiber |
| BS-5G | base_station | Terrestrial 5G tower (gNodeB) |
| CORE | core | Telecom core network: every route ends here |
| SEC | security_server | Cybersecurity monitoring server |
| IOT-001/002/003 | iot_device | The three IoT devices |

| Link | From → To | Type | Role | Normal latency | Normal loss |
|---|---|---|---|---|---|
| L-IOT001-SAT | IOT-001 → SAT-1 | satellite | primary | ~35 ms | ~0.3 % |
| L-IOT003-SAT | IOT-003 → SAT-1 | satellite | primary | ~35 ms | ~0.3 % |
| L-IOT002-5G | IOT-002 → BS-5G | 5G | primary | ~12 ms | ~0.1 % |
| L-IOT001-5G | IOT-001 → BS-5G | 5G | **backup** | ~12 ms | ~0.1 % |
| L-IOT003-5G | IOT-003 → BS-5G | 5G | **backup** | ~12 ms | ~0.1 % |
| L-SAT-GS | SAT-1 → GS-1 | satellite | primary | ~35 ms | ~0.3 % |
| L-GS-CORE | GS-1 → CORE | fiber | primary | ~3 ms | ~0.01 % |
| L-5G-CORE | BS-5G → CORE | fiber | primary | ~3 ms | ~0.01 % |
| L-CORE-SEC | CORE → SEC | LAN | primary | ~0.5 ms | 0 % |

Backup links stay unused in Phase 4. In **Phase 8** they carry the traffic
when the satellite fails (failover).

---

## 2. How the simulator works (`backend/app/network_simulator.py`)

Every 2 seconds, while the simulation is running:

1. **New numbers.** Each link gets latency, packet loss and bandwidth from its
   type's typical value plus random noise (a Gaussian distribution).
2. **Failures applied.**
   * A node set **offline** takes all its links offline (100 % loss, 0 bandwidth).
   * A node or link set **degraded** gets 3–4× latency, 3–8 % loss and 20–40 % bandwidth.
   * **Rain fade:** about once every 3 minutes, heavy rain weakens a random
     satellite link for 15–30 s. Real satellite links do suffer from rain, and
     this makes the demo feel alive.
3. **Status decided from the numbers.** A link is *degraded* when packet loss
   is above 2 % or latency is above 2.5× normal, and *offline* when it carries nothing.
4. **Routes.** For each device, a breadth-first search over working primary
   links finds a path to CORE. No path means "traffic interrupted".
5. **Availability** = % of devices that can reach the core. The dashboard shows
   the current value and the session average.
6. **History.** Every ~6 s all link values are stored in the new
   `link_metrics` table (for the charts in Phase 10). Status changes are
   written to the event log.

---

## 3. Set up Phase 4

Mosquitto now runs as a Windows service, so you only need two terminals.

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase4.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase4` and open that folder in VS Code.
3. **Terminal 1 (backend):**
```
cd CyberShield-SatCom-3D\backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v0.4.0 ready`.
4. **Terminal 2 (frontend):**
```
cd CyberShield-SatCom-3D\frontend
npm install
npm run dev
```
5. Open **http://localhost:5173**.

(If VS Code opened the inner `CyberShield-SatCom-3D` folder directly, leave out
the `CyberShield-SatCom-3D\` part of the `cd` commands.)

### Changed and new files

```
backend/app/
├── config.py             CHANGED  NET_RANDOM_EVENTS setting
├── models.py             CHANGED  new LinkMetric table (link history)
├── seed.py               CHANGED  network nodes + links
├── database.py           CHANGED  seeds the network on first start
├── network_simulator.py  NEW      metrics, failures, routes, availability
├── simulation_controller.py CHANGED runs the network every 2 s; Reset resets it
├── main.py               CHANGED  registers the network routes
└── routes/network.py     NEW      network API
frontend/src/
├── App.jsx                     CHANGED  availability card, network panel, link table
├── services/api.js             CHANGED  network calls
├── hooks/useLiveData.js        CHANGED  live network snapshot
├── components/NetworkMap.jsx   NEW      animated 2D topology (SVG)
├── components/NetworkPanel.jsx NEW      map + details + failure buttons + routes
├── components/LinkTable.jsx    NEW      live link numbers
└── styles/global.css           CHANGED
```

---

## 4. New API endpoints

| Method | URL | What it does |
|---|---|---|
| GET | `/api/network/topology` | Nodes, links, routes, availability |
| GET | `/api/network/status` | Summary: link counts, routes, availability history |
| GET | `/api/network/links/L-SAT-GS/history` | Recent stored values of one link |
| POST | `/api/network/links/{link_id}/state` | Body `{"state": "auto"}`, `"degraded"` or `"offline"` |
| POST | `/api/network/nodes/{node_id}/state` | Same, for SAT-1, GS-1, BS-5G, CORE, SEC |

`auto` means back to normal simulated behaviour. Try them at
http://127.0.0.1:8000/docs. The live channel has a new message type,
`network`, sent every 2 s.

---

## 5. Test Phase 4

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Topology shown | Open the dashboard | Map with 8 nodes; blue moving dashes on primary links, grey curved backup links |
| 2 | Live numbers | Watch the link table | Latency/loss change every 2 s; satellite ~35 ms, 5G ~12 ms, fiber ~3 ms |
| 3 | Routes | "Device routes" | IOT-001 and IOT-003 via SAT-1 → GS-1 → CORE; IOT-002 via BS-5G → CORE |
| 4 | Satellite down | Click **SAT-1** → **Take offline** | 3 links red with ✕; IOT-001/003 "No route to core"; availability **33.3 %** |
| 5 | Restore | **Normal** | All green again; availability **100 %**; "back to normal" events |
| 6 | Degraded link | Click the line SAT-1 ↔ GS-1 → **Degrade** | Orange, slower dashes; ~120 ms latency, 3–8 % loss; routes show "(degraded)" |
| 7 | Ground link | Click **GS-1** → **Take offline** | Satellite devices lose their route even though SAT-1 is fine |
| 8 | Rain fade | Wait a few minutes | 🌧 in the link table, 🛰 "Heavy rain is weakening..." event; recovers by itself |
| 9 | History | Open http://127.0.0.1:8000/api/network/links/L-SAT-GS/history | List of stored values, offline periods show 100 % loss |
| 10 | Reset | Click **Reset** | All links normal, overrides cleared, session availability back to 100 % |

If all 10 pass, Phase 4 is done.

**Note:** in Phase 4 a device without a route still delivers its readings,
because the simulator doesn't know about the network yet. In **Phase 8**,
traffic either switches to the backup 5G link (failover) or is shown as
interrupted.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| No network panel | Check Terminal 1 says `v0.4.0`; refresh the browser (Ctrl+F5) |
| Network values don't change | Simulation is paused: click **Start** |
| Rain fades are distracting during a demo | Add `NET_RANDOM_EVENTS=false` to a `.env` file in the project root and restart the backend |
| `no such table: link_metrics` | You reused an old database. The table is created automatically on start, so restart the backend |

---

## Next: Phase 5 — Cybersecurity detection

A rule-based detection engine that turns the Phase 3 scenarios (flood,
unauthorized device, abnormal values, connection storm) and link failures into
security alerts with severity levels, stored in SQLite and shown live.
