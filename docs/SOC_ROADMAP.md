# CyberShield SOC: audit and staged plan (v2.0, stages 2 to 4 in v2.1)

## 1. Audit of the existing project (before v2.0)

| Area | What exists and works | Status |
|---|---|---|
| Backend | FastAPI, REST + WebSocket `/ws`, SQLAlchemy 2 (SQLite or PostgreSQL), 88 automated tests | real |
| Auth | Login, JWT-style tokens, roles viewer < operator < admin, audit log of every change, multi-company scoping | real |
| Telemetry | Built-in device simulator (29 devices), optional MQTT broker and a real ESP32 board | simulated / lab |
| Network | Satellite, ground stations, 5G towers, core, links with latency/loss, routing, failover | simulated model |
| Detection | 10 rules (rate, unknown device, ranges, reconnect storm, spoofing, malformed, link/node down, motion, ML Isolation Forest) | real code on simulated data |
| Response | Quarantine (simulated isolation), auto-quarantine, incidents with notes, phone alarm (ntfy / Telegram) | real workflow, simulated effect |
| Data | Long-term warehouse (hourly roll-ups, history generator), reports, CSV export | real |
| AI | Offline rule-based analyst, or Gemini / Groq / OpenRouter / OmniRoute with the live state as context | real |
| 3D | Globe twin with procedural equipment models, replay timeline, device 3D viewer | real |

Technologies kept: React 19 + Vite (JavaScript, not TypeScript: rewriting 60 working components would
risk breaking them for no user-visible gain), Recharts, Three.js / react-three-fiber, FastAPI, SQLAlchemy.
Rule kept from v1.2: database upgrades only add **new tables**, never new columns, so old databases keep working.

## 2. Stages

| Stage | Content | State |
|---|---|---|
| 1 (v2.0) | SOC design system (dark theme, sidebar with grouped modules, line icons, global search, notifications, SIM/LAB labels); SOC Overview with real MTTD / MTTA / MTTR; Alert Center (MITRE ATT&CK, confidence, dedup, correlation, acknowledge / assign / investigate / escalate / close, evidence page); Detection Rules (on/off, simulated test per rule); IoT Asset Management; Satellite & 5G Security; 3D twin: zoom-to, pan, full screen, Configure / Security / Network tabs, network designer | **done** |
| 2 | Security event store (source/destination IP, protocol, MQTT client, port) with **Threat Hunting** (search, time range, saved queries, export); new simulated scenarios: MQTT brute force with auth failures, botnet beaconing, port scan, unauthorized publish, abnormal outbound / exfiltration, suspicious 5G authentication, config change; GNSS spoofing / jamming indicators; environment selector Simulation / Lab / Production | **done (v2.1)** |
| 3 | **Threat Intelligence** (local IOC list, enrichment through VirusTotal / AbuseIPDB / OTX when keys are set in `.env`); **AI SOC Analyst** with controlled tools (`search_security_events`, `get_device_information`, `analyze_alert`, `correlate_events`, `create_incident`, `request_device_isolation` …) that cite evidence and need analyst approval for actions; incident workflow Detection → Triage → Investigation → Containment → Eradication → Recovery → Closure with MITRE mapping and evidence panel | **done (v2.1)** |
| 4 | Roles Admin / SOC Manager / L1 / L2 / L3, TOTP MFA, approval workflow for containment, tamper-evident (hash-chained) audit log; playbooks; end-to-end demo scenario and report | **done (v2.1)** |

## 3. What is real, simulated, or needs external infrastructure

* **Real:** every number on the dashboards is computed from stored rows; the detection code; the triage
  workflow; the audit log; authentication and role checks; company isolation.
* **Simulated (labelled SIM):** devices, attacks, satellite / 5G links, quarantine and failover effects.
* **Lab (labelled LAB):** readings from a real ESP32 board over MQTT.
* **Production:** not used. There is no authorised real infrastructure in this project.
* **Optional external services:** VirusTotal / AbuseIPDB / OTX work when their API keys are set in `.env`
  (off by default).
* **Needs external services (not connected):** Suricata, Zeek, Wazuh, OpenSearch, Kafka / Redpanda,
  a real 5G core or satellite modem.
