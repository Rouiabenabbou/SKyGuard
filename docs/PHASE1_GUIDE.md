# Phase 1 — Project Setup

**Goal:** a FastAPI backend and a React dashboard that talk to each other over
REST and WebSocket. Every later phase plugs into this skeleton.

**Status:** tested end to end (Python 3.13, Node 22). The dashboard showed the
API online, the WebSocket connected, ~2 ms round trip and no browser errors.

---

## 1. Architecture in one picture

```
 ESP32 + DHT22 ─┐                                   (Phase 11)
 IoT simulator ─┤  MQTT  ┌───────────┐              (Phases 2–3)
                └──────► │ Mosquitto │
                         └─────┬─────┘
                               ▼
                 ┌──────────────────────────────┐
                 │   FastAPI backend (Python)   │
                 │  • MQTT client               │
                 │  • Detection engine          │   (Phase 5)
                 │  • Network simulator         │   (Phases 4, 8)
                 │  • Event store → SQLite      │   (Phases 2, 9)
                 └──────┬──────────────┬────────┘
                   REST │              │ WebSocket (live push)
                        ▼              ▼
                 ┌──────────────────────────────┐
                 │ React + Vite dashboard       │
                 │  • Three.js 3D digital twin  │   (Phase 7)
                 │  • Charts, alerts, timeline  │   (Phases 9–10)
                 └──────────────────────────────┘
```

* **REST** (`GET /api/...`, `POST /api/...`): the browser asks, the server answers.
  Used for loading data and pressing buttons ("Simulate satellite failure").
* **WebSocket** (`/ws`): a connection that stays open so the *server* can push
  data the moment it happens (telemetry, alerts, link failures).
* **Vite proxy:** the browser only talks to `localhost:5173`. Vite forwards
  `/api` and `/ws` to the backend on port 8000. This avoids CORS errors.

In Phase 1 we build the two boxes at the bottom and both arrows between them.

---

## 2. Software to install

| Software | Version | Why |
|---|---|---|
| Python | 3.10 or newer (3.12 recommended) | Backend |
| Node.js | **22 LTS** (needs 20.19+ or 22.12+) | Frontend build tool (Vite 8) |
| Git | any recent | Version control |
| VS Code | any recent | Editor (extensions: Python, ES7 React snippets) |
| Mosquitto | 2.x | Not needed yet; installed in Phase 3 |

### Check what you already have

Run each command in a terminal (PowerShell on Windows, Terminal on macOS/Linux):

```bash
python --version      # Windows. On macOS/Linux use: python3 --version
node --version        # should print v22.x (or v20.19+)
npm --version         # comes with Node, 10.x is fine
git --version
code --version        # VS Code command line (optional)
```

If a command says "not recognized" / "command not found", install it:

* **Python:** https://www.python.org/downloads/ — on Windows tick **"Add python.exe to PATH"** in the installer.
* **Node.js:** https://nodejs.org/ — pick the **LTS** version.
* **Git:** https://git-scm.com/downloads
* **VS Code:** https://code.visualstudio.com/

Close and reopen the terminal after installing so it sees the new commands.

---

## 3. Create the project folders

You can either **unzip the provided `CyberShield-SatCom-3D.zip`** (all files
are already in place, skip to section 5), or create the structure yourself
and copy each file in.

**macOS / Linux / Git Bash:**

```bash
mkdir -p CyberShield-SatCom-3D && cd CyberShield-SatCom-3D
mkdir -p backend/app/routes
mkdir -p frontend/src/{components,pages,three,hooks,services,styles} frontend/public
mkdir -p iot/esp32 iot/simulator database docs
```

**Windows PowerShell:**

```powershell
mkdir CyberShield-SatCom-3D; cd CyberShield-SatCom-3D
mkdir backend\app\routes
"components","pages","three","hooks","services","styles" | % { mkdir "frontend\src\$_" }
mkdir frontend\public, iot\esp32, iot\simulator, database, docs
```

---

## 4. The files and where they go

```
CyberShield-SatCom-3D/
├── .env.example                 settings you may override (all have defaults)
├── .gitignore                   keeps venv, node_modules, .db files out of Git
├── README.md
├── backend/
│   ├── requirements.txt         Python packages
│   └── app/
│       ├── __init__.py          marks "app" as a Python package
│       ├── main.py              creates the FastAPI app, CORS, WebSocket, heartbeat
│       ├── config.py            reads settings from .env with defaults
│       ├── websocket_manager.py tracks connected browsers, broadcasts messages
│       └── routes/
│           ├── __init__.py
│           └── system.py        GET /api/health and GET /api/info
├── frontend/
│   ├── package.json             npm packages and scripts
│   ├── vite.config.js           dev server on 5173 + proxy to backend
│   ├── index.html               page shell, loads src/main.jsx
│   ├── public/shield.svg        logo / browser tab icon
│   └── src/
│       ├── main.jsx             mounts React into the page
│       ├── App.jsx              the Phase 1 status dashboard
│       ├── services/api.js      all REST calls in one place
│       ├── hooks/useBackendSocket.js   WebSocket with auto-reconnect + latency ping
│       ├── components/Header.jsx       title bar + live/offline pill
│       ├── components/StatusCard.jsx   one metric card
│       ├── components/ComponentList.jsx list of system components
│       └── styles/global.css    dark dashboard theme
├── iot/esp32/  iot/simulator/  database/   (empty for now)
└── docs/PHASE1_GUIDE.md         this file
```

### What the key files do

* **`backend/app/main.py`** creates the app. At startup (`lifespan`) it starts a
  background task that sends a `heartbeat` message to every connected browser
  every 2 seconds. The `/ws` endpoint accepts browsers and answers `ping` with
  `pong`, which is how the dashboard measures latency.
* **`backend/app/websocket_manager.py`** keeps a set of open sockets.
  `broadcast()` is what later phases will call to push telemetry and alerts.
* **`frontend/src/hooks/useBackendSocket.js`** opens `ws://localhost:5173/ws`
  (proxied to the backend), reconnects every 2 s if the backend restarts, and
  sends a ping every 3 s.
* **`frontend/src/App.jsx`** polls `/api/health` every 5 s and shows four cards
  plus the component list from `/api/info`.

All WebSocket messages share one shape so every phase can reuse the channel:

```json
{ "type": "heartbeat", "data": { "seq": 12, "time": "2026-10-29T07:58:12Z", "clients": 1 } }
```

---

## 5. Install dependencies

Open the project folder in VS Code (`code .`) and use two terminals.

### Terminal 1 — backend

```bash
cd backend
python -m venv venv          # macOS/Linux: python3 -m venv venv
```

Activate the virtual environment:

| OS | Command |
|---|---|
| Windows PowerShell | `venv\Scripts\Activate.ps1` |
| Windows cmd | `venv\Scripts\activate.bat` |
| macOS / Linux | `source venv/bin/activate` |

Your prompt should now start with `(venv)`. Then:

```bash
pip install -r requirements.txt
```

> Windows: if PowerShell says *running scripts is disabled*, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again.

### Terminal 2 — frontend

```bash
cd frontend
npm install
```

---

## 6. Run it

**Terminal 1 (backend, with venv active):**

```bash
uvicorn app.main:app --reload --port 8000
```

Expected output:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process ...
[startup] CyberShield SatCom 3D v0.1.0 ready
INFO:     Application startup complete.
```

**Terminal 2 (frontend):**

```bash
npm run dev
```

Expected output:

```
  VITE v8.x  ready in 300 ms
  ➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser.

---

## 7. Test Phase 1

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Backend alive | Open http://127.0.0.1:8000/api/health | JSON with `"status": "ok"` |
| 2 | API docs | Open http://127.0.0.1:8000/docs | Swagger page listing `/api/health`, `/api/info` |
| 3 | Proxy works | Open http://localhost:5173/api/health | Same JSON as test 1 |
| 4 | Dashboard | Open http://localhost:5173 | Green "Live link to backend", REST **Online**, WebSocket **Connected** |
| 5 | Real-time push | Watch "Last heartbeat" | Number goes up by 1 every 2 seconds |
| 6 | Latency | Watch "Round-trip latency" | A few ms (localhost) |
| 7 | Failure handling | Press Ctrl+C in Terminal 1 | Within ~5 s: red banner, "Backend offline", cards turn red |
| 8 | Auto-reconnect | Start uvicorn again | Within ~2–5 s everything turns green again without refreshing |

Command-line check (optional):

```bash
curl http://127.0.0.1:8000/api/health
```

If all 8 tests pass, Phase 1 is done.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found (Windows) | Reinstall Python with "Add to PATH", or use `py` instead of `python` |
| `ModuleNotFoundError: No module named 'app'` | Run uvicorn from inside `backend/`, not the project root |
| `ModuleNotFoundError: fastapi` | The venv is not active. Activate it, then `pip install -r requirements.txt` |
| `Address already in use` / port 8000 busy | Another uvicorn is running. Close it, or use `--port 8001` and change both ports in `frontend/vite.config.js` |
| Vite error about Node version | Install Node 22 LTS; check with `node --version` |
| Dashboard says "Backend offline" | Backend not running, or running on a different port than 8000 |
| `http proxy error ... ECONNREFUSED` in the Vite terminal | Same as above: start the backend |
| Blank white page | Open the browser console (F12) and send me the red error text |

---

## 9. Save your work in Git (recommended)

```bash
git init
git add .
git commit -m "Phase 1: FastAPI backend and React dashboard connected"
```

To push to GitHub, create an empty repository on github.com, then follow the
"push an existing repository" commands it shows.

---

## Next: Phase 2 — Database and IoT simulator

SQLite tables (devices, telemetry, events…), three simulated IoT devices that
generate realistic readings, and live device cards on the dashboard.
