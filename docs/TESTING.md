# Testing — CyberShield SatCom 3D

All results below come from the **simulated** environment (one laptop, local
broker). They show that the system behaves as designed. They are not
measurements of a real telecom network.

## 1. Automated tests (backend)

```powershell
cd backend
venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt     # pytest, httpx
pip install -r requirements-ml.txt      # optional, enables the 2 ML tests
python -m pytest
```

Expected: `104 passed` (or `102 passed, 2 skipped` without scikit-learn), in about 30 s.
On PostgreSQL: set `TEST_DATABASE_URL=postgresql://user:pass@host/db` first.
The tests use a temporary database, no MQTT broker, and no random network
events, so they give the same result every time.

| File | Tests | What is checked |
|---|---|---|
| `test_api.py` | 6 | Health, info, 3 registered devices, 404s, start/pause, topology and routes |
| `test_detection.py` | 7 | Valid reading stored; malformed rejected; Rule B unauthorized; Rule C abnormal → suspicious (not quarantined); Rule A flood → alert + auto-quarantine; quarantined traffic blocked and counted; alert cooldown |
| `test_quarantine.py` | 4 | Manual quarantine/release via API, isolation from routing, idempotent quarantine, auto switch, 404 |
| `test_failover.py` | 6 | Healthy stays primary; failover then failback with exact timings; failover off → outage and lost readings; degraded → make-before-break; no backup → down; drill endpoint |
| `test_timeline_reports.py` | 5 | Frames recorded with all fields; thinning to `max`; bad time → 400; all 5 CSV exports; report summary |
| `test_ml.py` | 2 | Model trains on normal data and flags an unusual in-range reading with `detection_method = ml`; status endpoint |
| `test_add_device.py` | 3 | Add a satellite device (node, primary + backup links, route, simulated twin, ingest), real-board device not simulated, validation, built-ins protected |
| `test_network_builder.py` | 2 | Build SAT-2 + GS-2 path, attach a device, route goes over it; duplicates, bad types and protected original topology |
| `test_device_config.py` | 3 | Operator config changes name/location/ranges, is logged, and the new range is enforced by detection; bad ranges → 422; unknown device → 404 |
| `test_analytics.py` | 6 | History generator (rows, days, incidents), hourly rollup never shrinks, trends/alerts/forecast, company scoping, platform-only history |
| `test_v14.py` | 7 | Big companies seeded once, incident lifecycle and company scoping, maintenance mutes the phone, reboot/firmware, AI key from the dashboard (never sent back), /metrics token |
| `test_v22.py` | 5 | Huawei IoTDA push (off without token, bad token 401, reading stored as LAB, unknown device, status hides the token); LAB source labels; lab test report (JSON and Markdown, none without a real board); ModelArts autoencoder model loads, scores normal vs jump, bad file handled; model status endpoint |
| `test_v21.py` | 11 | The 9 new simulated scenarios raise rules CS-011..CS-021; threat hunting query language, saved queries and export; IOC match and intel lookup without keys; AI analyst cites evidence and only proposes actions; 7-phase incident workflow, playbook and report; L1/L2/L3 permissions and approvals; two-person rule; 2FA login and step-up approval; required-2FA role; audit hash chain detects edits and deletions; end-to-end demo |
| `test_soc.py` | 6 | Rule catalogue with MITRE, a switched-off rule does not fire, rule test runs the simulated attack, alert triage (acknowledge, assign, escalate to incident, close) with history and evidence, MTTD from a simulated attack, SOC permissions and company scoping |
| `test_v15.py` | 5 | v1.5 network and devices seeded once (SAT-2, GS-2, regional towers), reroute through a backup ground station, investigation graph (dispositions, observables, timeline), company scoping of the graph, layout saved per user, re-wiring a device, OmniRoute without a key |

Result on v2.2: **104 passed** on SQLite and on PostgreSQL 16 (Python 3.13), and 102 passed + 2 skipped on Python 3.10 without scikit-learn (v2.1: 99, v2.0: 88, v1.5: 82, v1.4: 77, v1.3: 70, v1.2: 63, v1.1: 51, v1.0: 39) (also run three times in a row, with no flaky tests).

## 2. Manual / UI tests

Each `PHASEx_GUIDE.md` has a test table (10–13 tests per phase, about 130 in
total). The UI was also checked with an automated browser (Playwright, Chromium):

* every tab renders, with no console errors
* the page fits a 390 px phone screen with no sideways scroll
* the 3D twin renders with WebGL, objects are clickable, and the inspector shows the right data
* failover drill, timeline replay and charts are visible

## 3. Evaluation results (simulated)

| # | Scenario | Metric | Result |
|---|---|---|---|
| 1 | 3 devices, normal traffic, 45 s | False alerts | **0** |
| 2 | Flood 20 msg/s on IOT-002 | Detection time | **≈ 2.5 s** |
| 3 | Flood, auto-quarantine on | Alert → quarantine | **same second** |
| 4 | Flood continues after quarantine | Attacker readings stored | **0 of ~70–160** (100 % blocked) |
| 5 | Unauthorized IOT-999 | Detection | first message, nothing stored |
| 6 | Abnormal value 85 °C on IOT-001 | Alert / action | HIGH alert, device *suspicious*, operator decides |
| 7 | Connection storm (12 reconnects) | Detection | HIGH alert, auto-quarantine |
| 8 | SAT-1 offline 25 s, **failover ON** | Interruption per device | **2.6–4.6 s** (detection ≤ 2 s + handover 1.5–3 s) |
| 9 | Same, **failover OFF** | Interruption | **25 s** (whole outage), device went offline |
| 10 | Same outage | Readings lost per device | **~1** with failover, **~5** without |
| 11 | Satellite back | Failback interruption | **0 s** (make-before-break) |
| 12 | Degraded satellite (GS-1 degraded) | Readings lost during switch | **0** |
| 13 | ESP32 emulator | Quarantine command | device stops sending; resumes on release |
| 14 | ML detector (trained on ~120 normal readings) | Unusual in-range reading | flagged, `detection_method = ml` |

### Network availability

With failover on, availability during a satellite outage drops only for the
few seconds of the handover. Afterwards it is back to 100 % because the
devices are on 5G. With failover off, it stays at 33 % (1 of 3 devices) for
the whole outage. The availability chart on the Network tab shows both cases.

## 4. Known limitations of the evaluation

* There is one machine, and the latency between components is near zero.
* Handover times are random values from configuration, not a radio model.
* Detection thresholds were chosen for the simulated traffic. Real devices may need tuning.
* The ML detector looks at sensor values only, not traffic patterns.
* The ESP32 firmware was checked with the emulator. Test it with the real board before the demo.
