# Phase 10 — Full Dashboard (tabs, charts, reports)

**Goal:** turn the long single page into a proper monitoring dashboard. It has
five tabs, real charts (Recharts), CSV downloads for every table, and a session
report you can print or save as a PDF for your project report.

**Status:** tested. All five tabs render, 3 to 4 live charts each, the CSV
downloads work, the report prints, there are no browser errors, and every tab
fits a 390 px phone screen. The production build (`npm run build`) passes.

---

## 1. The five tabs

| Tab | What's on it |
|---|---|
| **Overview** | Status cards, simulation controls, **temperature** and **humidity** charts (one line per device), **availability** chart, latest events, device cards |
| **4D Twin** | The 3D scene with the inspector and the 4D timeline (Phases 7 and 9) |
| **Network** | 2D map and routes, failover panel, availability and battery charts, **link history** (latency and packet loss of any link, from the database), link table |
| **Security** | Attack buttons, quarantine panel, alerts, **alert statistics** (by type, by severity, per minute), device cards |
| **Data & Reports** | Session report (print / PDF), **CSV downloads**, telemetry table, full event log |

The status cards stay at the top of every tab. The tab is saved in the address
(`http://localhost:5173/#security`), so a refresh keeps it. The Security tab
shows a red badge with the number of open alerts.

### Chart design choices (useful for your report)

* Each device keeps the **same colour on every chart** (blue IOT-001, orange
  IOT-002, green IOT-003, gold ESP32-001). The colours were checked for
  colour-blind separation on the white dashboard background.
* Severity colours (grey, amber, orange, red) are used only for severity.
* Never two y-axes on one chart. Latency and packet loss get **two charts**.
* Every chart has a hover tooltip, and multi-device charts have a legend.
* Sensor charts show the **last 5 minutes**.

---

## 2. Set up Phase 10

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase10.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase10` and open it in VS Code.
3. **Terminal 1:**
```
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v0.10.0 ready`.
4. **Terminal 2.** `npm install` adds Recharts:
```
cd frontend
npm install
npm run dev
```
5. Open **http://localhost:5173**.

### Changed and new files

```
backend/app/
├── routes/reports.py   NEW      CSV exports + /api/report/summary
├── main.py, config.py, routes/system.py   CHANGED  version 0.10.0
frontend/
├── package.json        CHANGED  recharts
└── src/
    ├── App.jsx                         REWRITTEN  tabs
    ├── components/Tabs.jsx             NEW
    ├── components/ReportPanel.jsx      NEW  report + CSV buttons + print
    ├── components/charts/theme.js      NEW  colours, axis and tooltip style
    ├── components/charts/TelemetryChart.jsx    NEW
    ├── components/charts/AvailabilityChart.jsx NEW
    ├── components/charts/LinkCharts.jsx        NEW
    ├── components/charts/AlertCharts.jsx       NEW
    ├── hooks/useSummary.js             NEW  report data, refreshed every 5 s
    ├── hooks/useLiveData.js            CHANGED  availability history for the chart
    ├── services/api.js                 CHANGED
    └── styles/global.css               CHANGED  tabs, charts, print layout
```

---

## 3. New API endpoints

| Method | URL | What it does |
|---|---|---|
| GET | `/api/export/telemetry.csv` | All readings |
| GET | `/api/export/alerts.csv` | All alerts |
| GET | `/api/export/events.csv` | Event log |
| GET | `/api/export/quarantine.csv` | Quarantine records |
| GET | `/api/export/failover.csv` | Failover records |
| GET | `/api/report/summary` | Session summary: totals, per-device statistics, alerts by type, severity and minute, availability, failover statistics |

---

## 4. Test Phase 10

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Tabs | Click each tab | Content changes; the address shows `#overview`, `#twin`… |
| 2 | Refresh keeps tab | On **Network**, press F5 | Still on Network |
| 3 | Sensor charts | Overview | Temperature and humidity lines for every device, moving every 5 s; hover shows values |
| 4 | Abnormal value | Security → **Abnormal reading** on IOT-001, back to Overview | A spike to ~85 °C on the blue line |
| 5 | Availability | Network → **Satellite outage drill** with failover OFF | Availability chart drops to 33 %, then recovers |
| 6 | Link history | Network → Link history → choose `L-SAT-GS` | Latency ~35 ms; packet loss chart; rain fade or Degrade shows as a jump |
| 7 | Alert statistics | Run two different attacks, open Security | Bars by type, severity and minute |
| 8 | Security badge | Any tab | Red number next to Security = open alerts |
| 9 | Report | Data & Reports | Totals, device table, alerts by type, failover numbers |
| 10 | CSV | Click **⬇ Telemetry readings** | A `.csv` file downloads and opens in Excel |
| 11 | PDF | **🖨️ Print / save as PDF** → choose "Save as PDF" | A clean white page with only the report |
| 12 | Phone | Narrow the window | Tabs scroll sideways, charts shrink, no sideways page scroll |

If all 12 pass, Phase 10 is done.

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| `Failed to resolve import "recharts"` | Run `npm install` in the new frontend folder |
| Charts empty | Wait 10 s for readings; the simulation must be running |
| Link history says "Collecting" | History is saved about every 6 s; wait a little |
| CSV opens as one column in Excel | Use Data → From Text/CSV, comma separator |

---

## Next: Phase 11 — ESP32 + DHT22

Connect a **real** ESP32 with a DHT22 temperature/humidity sensor over Wi-Fi
and MQTT. It shows up in the dashboard and 3D twin next to the simulated
devices, and it obeys the quarantine command.
