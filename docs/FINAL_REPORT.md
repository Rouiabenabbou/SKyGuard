# CyberShield SOC v2.1: final implementation report

This report covers the four SOC stages built on top of CyberShield SatCom 3D (v1.0 to v1.5). Stage 1 came
in v2.0, stages 2 to 4 in v2.1. The plan and the audit are in `SOC_ROADMAP.md`.

**Safety rule followed everywhere:** every attack is simulated inside the application. Attacker addresses
come from the RFC 5737 documentation ranges (203.0.113.0/24, 198.51.100.0/24), which can never belong to a
real host. No real device, network, satellite or 5G core is touched. Quarantine, failover and the 5G core
are simulations and are labelled as such.

## 1. Architecture

```
 Simulated devices ──┐                         ┌── React 19 dashboard (SOC console)
 ESP32 lab board ────┤ MQTT  ┌──────────────┐  │     REST + WebSocket
 Attack scenarios ───┴──────►│ FastAPI      │◄─┘
                             │  ingestion   │──► security event store (security_events)
                             │  detection   │──► alerts, incidents, approvals, audit chain
                             │  AI tools    │──► optional LLM (only sees the evidence list)
                             │  intel       │──► optional VirusTotal / AbuseIPDB / OTX (keys in .env)
                             └──────────────┘
                                   │ SQLAlchemy
                             SQLite or PostgreSQL
```

* **Backend:** FastAPI, SQLAlchemy 2, SQLite by default or PostgreSQL. One HTTP middleware checks login,
  role level, permission, company scope and the 2FA requirement, and writes the audit log.
* **Frontend:** React 19 + Vite, Recharts, Three.js (3D twin), lucide icons. Pages are hidden or disabled
  when the role lacks the permission, and the server checks again on every request.
* **Database rule:** upgrades only add new tables, never new columns, so a v1.x database keeps working.
  v2.1 tables: `security_events`, `saved_queries`, `iocs`, `intel_cache`, `incident_phases`,
  `incident_evidence`, `approval_requests`, `user_mfa`, `audit_chain`, `playbook_runs`,
  `ai_investigations`, `demo_runs`.

### Main modules (backend/app)

| Module | Role |
|---|---|
| `security_events.py` | Records events, per-minute flow summaries, retention; `NetDetector` with rules CS-011..CS-021 (sliding windows) |
| `attack_scenarios.py` | The 9 new simulated scenarios |
| `routes/hunt.py` | Threat Hunting query language, histogram, facets, export, saved queries |
| `intel.py`, `routes/intel.py` | IOC list, matching, VirusTotal / AbuseIPDB / OTX look-ups with a 24 h cache |
| `gnss.py` | Simulated GNSS status (C/N0, fix, position) for satellite devices |
| `ai_tools.py`, `routes/ai.py` | AI SOC Analyst: tools, evidence list, citation check, offline analyst |
| `incident_workflow.py` | 7 phases, MITRE mapping, evidence, approvals, report |
| `playbooks.py` | PB-01..PB-05 with ordered steps |
| `soc_access.py` | Roles and permissions |
| `mfa.py` | TOTP (RFC 6238) with the Python standard library |
| `auth.py` | Login, middleware, hash-chained audit log |
| `demo.py` | End-to-end demo scenario |

## 2. What is real and what is simulated

| Part | Status |
|---|---|
| Numbers on every dashboard (MTTD, MTTA, MTTR, counts, charts) | **Real:** computed from stored rows; "—" when there is no data |
| Detection rules, hunting, correlation, workflow, approvals, roles, 2FA, audit chain | **Real code** running on the stored events |
| Devices, attacks, satellite / 5G links, GNSS signal | **Simulated**, labelled SIM |
| Quarantine, release, failover, password rotation | **Simulated effects** (the device is isolated inside the simulator only) |
| ESP32 board readings | **Lab**, labelled LAB |
| Production environment | **Not connected**; the selector says so instead of showing data |
| VirusTotal, AbuseIPDB, OTX | **Real services, optional**: used only when the key is in `.env`; documentation and private addresses are never sent |
| AI language model | **Optional** (Gemini, Groq, OpenRouter, OmniRoute); without a key a built-in analyst writes the answer from the same evidence |
| Suricata, Zeek, Wazuh, OpenSearch, Kafka, real 5G core | **Not connected** (would need real infrastructure) |

## 3. Stage by stage

### Stage 2: events and hunting
* Every login, publish, connection, 5G registration, GNSS sample and config change is a row in
  `security_events` with source / destination address and port, protocol, MQTT client and topic, user,
  outcome, bytes and the source label (simulated / lab / production).
* Threat Hunting: `field:value`, `a,b` (any of), `*` wildcard, `-field:x` (not), `bytes:>N`, `"text"`;
  time ranges from 15 minutes to 30 days, a timeline, top values, saved and shared queries, 10 ready-made
  hunts, CSV and JSON export.
* New rules with MITRE ATT&CK: CS-011 MQTT brute force (T1110.001), CS-012 C2 beaconing (T1071.001),
  CS-013 port scan (T1046), CS-014 unauthorized publish (T0855), CS-015 exfiltration (T1048), CS-016 5G
  authentication anomaly (T1110), CS-017 unauthorized config change (T0836), CS-018 threat-intel match,
  CS-019 GNSS jamming (T1464), CS-020 GNSS spoofing, CS-021 credential compromise (T1078).

### Stage 3: intelligence, AI analyst, incident workflow
* **Threat Intelligence:** IOC list with kind, severity, source and sightings in 24 h. A match in any event
  raises CS-018.
* **AI SOC Analyst:** the analyst may only read through 8 tools. Each tool result becomes an evidence item
  E1, E2 .... The language model gets only these items and must cite them; an answer that cites nothing or
  cites an item that does not exist is rejected and the built-in analyst answers instead. The two action
  tools (`create_incident`, `request_device_isolation`) are only shown as proposals; a person confirms and
  isolation then waits for approval. Every investigation is stored and attached to the incident.
* **Incident workflow:** Detection → Triage → Investigation → Containment → Eradication → Recovery →
  Closure, one phase at a time. Leaving Containment without an executed containment needs a note, closing
  needs a note. MITRE techniques are collected from the alerts and can be edited. The report is Markdown.

### Stage 4: roles, 2FA, approvals, audit, playbooks, demo

| Role | Account (demo) | Can do |
|---|---|---|
| Viewer | — | read only |
| SOC analyst L1 | `analyst_l1 / AnalystL1@2026` | triage alerts, threat hunting |
| SOC analyst L2 | `analyst_l2 / AnalystL2@2026` | + open incidents, IOCs, simulated attacks, **request** isolation |
| SOC analyst L3 | `analyst_l3 / AnalystL3@2026` | + isolate / release, **approve** requests, playbooks, response |
| SOC manager | `soc_manager / Manager@2026` | + detection rules |
| Operator (v1.1) | `operator / Operator@2026` | same as L3 |
| Administrator | `admin / Admin@2026` | everything, users, settings |

* **Approvals:** isolation requested by L2, a playbook step, the AI analyst or the demo waits on the
  Approvals page. `APPROVAL_TWO_PERSON=true` stops anyone approving their own request.
* **2FA:** TOTP with any authenticator app (Account menu → Two-factor). If the approver has 2FA on, the
  code is asked again to approve a containment. `MFA_REQUIRED_ROLES` forces it for chosen roles. Codes
  cannot be reused.
* **Audit chain:** each audit row is hashed with SHA-256 together with the previous hash. Audit Logs →
  Verify integrity reports rows that were edited, deleted or added outside the chain.
* **Playbooks:** PB-01 compromised device, PB-02 credential attack, PB-03 reconnaissance, PB-04 GNSS
  interference, PB-05 generic. Steps are automatic, need approval, are checks or are manual, and run in
  order; running a step moves the incident to the step's phase.

## 4. Demo walkthrough (about 3 minutes)

1. Log in as `admin` and open **Operations → Demo Scenario**. Press **Start demo**.
2. Watch the steps: simulated MQTT brute force and rogue publish from a documentation address → about 12
   security events stored → 3 alerts (CS-011, CS-021, CS-014) → incident opened → AI analyst runs its tools
   (about 6 tool calls, 15 evidence items).
3. The isolation step **waits for you**. Press **Approve** (enter the 2FA code if it is on).
4. The rest runs by itself: simulated isolation, the address added to the IOC list, simulated password
   rotation, the device released, the incident closed. Press **download report**.
5. Open the incident link to show the 7-phase stepper, evidence, MITRE techniques and the AI answer with
   citations; open **Audit Logs → Verify integrity**.
6. Optional: log in as `analyst_l1` to show that the containment and attack buttons are gone and the server
   answers 403.

## 5. Testing

99 automated tests (`docs/TESTING.md`): 99 passed on SQLite and on PostgreSQL 16 (Python 3.13); on
Python 3.10, 97 passed and the 2 machine-learning tests were skipped because scikit-learn was not installed. `tests/test_v21.py` covers the new
scenarios, hunting, intel, the AI analyst, the workflow and playbooks, roles and approvals, the two-person
rule, 2FA, the audit chain and the full demo. All new pages were also checked in a headless browser on
desktop and at phone width (390 px) with no console errors.

## 6. Limits and future work

* Events come from the simulator and the lab board only; real sensors (Suricata, Zeek, Wazuh) and a big
  event store (OpenSearch, Kafka) are not connected.
* Detection state (sliding windows) is kept in memory, so it resets on restart; stored events and alerts
  do not.
* The AI analyst is only as good as its tools: it cannot see data outside the event store.
* Quarantine and password rotation act on the simulator, not on a real broker or device.
* Two-factor uses TOTP only (no hardware keys); there is no single sign-on.
* Some icons on the map and graph markers are still emoji.
