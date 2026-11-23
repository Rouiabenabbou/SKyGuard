# Phase 12 — Testing, Optional ML and Final Documentation

**Goal:** finish the project. It adds automated tests that prove the backend
works, an optional machine-learning detector, and the documents you need for
the report and the defence.

**Status:**

* **30 automated tests pass** in about 3 s (28 pass + 2 skipped without scikit-learn).
* The ML detector trained itself on about 150 normal readings, then checked
  50 more normal readings with **0 false alerts**, and flagged an unusual
  in-range reading in the test.
* The final version is **v1.0.0**.

---

## 1. Run the automated tests

```powershell
cd backend
venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest
```

Expected output:

```
..............................                                           [100%]
39 passed in 3.1s
```

The tests use their **own temporary database**, so your real data is not
touched. They need neither Mosquitto nor the frontend. What each test file
checks is in [TESTING.md](TESTING.md).

To see every test name: `python -m pytest -v`

---

## 2. Optional: machine-learning anomaly detector

The rule engine catches what we can describe in advance. The ML detector
learns what normal readings look like **for each device** and flags readings
that don't fit, even inside the allowed range (for example a sudden 8 °C jump).

* **Algorithm:** scikit-learn **Local Outlier Factor** (novelty mode),
  unsupervised. A reading is unusual when it is far from its nearest
  neighbours in the normal training data.
* **Features:** temperature and humidity, normalised per device, plus how much
  each changed since the previous reading.
* **Training:** automatic, once 120 normal readings are stored (about 3 minutes),
  or with **Train now** on the Security tab.
* **Alerts:** type `ml_anomaly`, medium severity, `detection_method = ml`.
  These alerts are **advisory**: they never auto-quarantine.
* We first tried IsolationForest. Its scores hardly changed for extreme values,
  so it could not separate them from borderline normal readings. LOF scores grow
  with distance, which works better for these features. This is a good point
  for your report.

**Turn it on:**

```powershell
cd backend
venv\Scripts\Activate.ps1
pip install -r requirements-ml.txt
```

Then in `.env` set `ML_ENABLED=true` and restart the backend. The Security tab
shows the **ML anomaly detector** panel: trained or not, training readings,
readings checked, readings flagged, and an on/off switch.

**Try it:** wait until "trained: yes", then run **Abnormal reading** on
IOT-001. You get the rule alert (Rule C) **and** an alert *detected by the
machine-learning detector*.

---

## 3. Set up Phase 12 (final version)

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase12.zip** (this is the complete project)
   to `D:\PROJECT\CyberShield-SatCom-3D-final` and open it in VS Code.
3. Optional: copy `.env.example` to `.env` and set `ESP32_ENABLED` / `ML_ENABLED`.
4. **Terminal 1:**
```
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
   You should see `v1.0.0 ready`.
5. **Terminal 2:** `cd frontend` → `npm install` → `npm run dev` → open http://localhost:5173.

### Changed and new files

```
backend/
├── app/ml_detector.py        NEW      optional LOF detector
├── app/routes/ml.py          NEW      /api/ml/status, /train, /settings
├── app/detection_engine.py   CHANGED  alerts can be detection_method "ml"
├── app/telemetry_service.py  CHANGED  calls the ML check for each stored reading
├── app/quarantine_service.py CHANGED  routes refresh immediately on quarantine/release
├── app/config.py             CHANGED  ML settings, version 1.0.0
├── tests/                    NEW      39 tests + conftest.py
├── pytest.ini                NEW
├── requirements-ml.txt       NEW      scikit-learn, numpy
└── requirements-dev.txt      NEW      pytest, httpx
frontend/src/components/MLPanel.jsx  NEW
frontend/src/components/AlertsPanel.jsx  CHANGED  "detected by the machine-learning detector"
docs/ARCHITECTURE.md, TESTING.md, DEMO_SCRIPT.md, REPORT_OUTLINE.md, PHASE12_GUIDE.md  NEW
README.md  REWRITTEN for v1.0
```

---

## 4. Final checklist before your defence

| # | Check | Expected result |
|---|---|---|
| 1 | `python -m pytest` | 39 passed |
| 2 | Backend start | `v1.0.0 ready`, `[mqtt] connected` |
| 3 | Overview tab | 3 (or 4) devices online, charts moving |
| 4 | 4D Twin | Globe, satellite, labels; click works |
| 5 | Attack + quarantine | Excessive traffic → alert → red cage |
| 6 | Failover drill | Backup 5G within about 4 s, failback after recovery |
| 7 | Replay | ⏪ Replay → ⏭ → ▶ shows the incident again |
| 8 | Report | Data & Reports → Print → Save as PDF |
| 9 | ESP32 (if used) | Online, readings, obeys quarantine |
| 10 | ML (if used) | Trained, 0 flagged during normal operation |
| 11 | Demo script | Rehearse [DEMO_SCRIPT.md](DEMO_SCRIPT.md) once, about 5 minutes |

---

## 5. Documents for your report

| File | Use it for |
|---|---|
| `README.md` | Overview, installation, features, API: appendix material |
| `docs/ARCHITECTURE.md` | Design chapter: layers, data flow, design decisions |
| `docs/TESTING.md` | Evaluation chapter: test plan and result tables |
| `docs/REPORT_OUTLINE.md` | Chapter structure for the report and the slides |
| `docs/DEMO_SCRIPT.md` | Live demo |
| `docs/PHASE1…12_GUIDE.md` | Implementation details per feature |

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `pytest: command not found` | Use `python -m pytest` with the venv active, after `pip install -r requirements-dev.txt` |
| `ModuleNotFoundError: app` in tests | Run pytest from the `backend` folder |
| ML panel says "Not installed" | `pip install -r requirements-ml.txt`, set `ML_ENABLED=true`, restart |
| ML never trains | It needs 120 readings from devices with security status "normal"; Reset and wait about 3 minutes |
| Too many ML alerts | Raise `ML_MARGIN` in `.env` (for example 2.0) |
