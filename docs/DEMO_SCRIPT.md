# 5-Minute Demo Script

**Before the demo**

1. Start Mosquitto (service), the backend (`uvicorn app.main:app --port 8000`) and the frontend (`npm run dev`).
2. For a calm demo, put `NET_RANDOM_EVENTS=false` in `.env`.
3. Open http://localhost:5173 and press **Reset**. Let it run for 1–2 minutes so the charts fill.
4. Optional: ESP32 board plugged in (or `esp32_emulator.py` running) with `ESP32_ENABLED=true`.

| Time | Where | Do | Say |
|---|---|---|---|
| 0:00 | Overview | Point at the cards and charts | "Three IoT sensors send data over MQTT through a simulated satellite–5G network. Everything is live." |
| 0:30 | 4D Twin | Rotate the globe, click IOT-003 | "This is the digital twin. Each object takes its colour from the live state. IOT-003 reaches the core over the satellite: 70 ms." |
| 1:00 | Security | **Excessive traffic** on IOT-002 | "A simulated flooding attack. The rule engine detects it in about 2 seconds…" |
| 1:15 | (pop-ups) | Show the alert and the quarantine pop-up | "…and isolates the device automatically. Its messages are now blocked, not stored." |
| 1:30 | 4D Twin | Show IOT-002 with its red cage | "In the twin the device is caged, and its link is blocked." |
| 1:45 | Network | **Satellite outage drill** | "Now the satellite fails. Watch IOT-001 and IOT-003 switch to the backup 5G links." |
| 2:15 | Network | Failover panel | "Each switch took about 2–4 seconds, and we lost at most one reading. Without failover we'd lose the whole outage." |
| 2:45 | 4D Twin | **⏪ Replay**, then ⏭ to the red markers, **▶ Play** at 10× | "Time is the fourth dimension. We can rewind and replay the incident: attack, quarantine, satellite failure, failover, recovery." |
| 3:45 | Security | Alert statistics; **Release** IOT-002 | "Statistics by type and severity. The operator releases the device after checking it." |
| 4:15 | Data & Reports | Show the report, click a CSV | "Everything is stored and can be exported for analysis." |
| 4:30 | (ESP32) | Breathe on the DHT22, or quarantine ESP32-001 | "And this is a real ESP32: same pipeline, same security, and it obeys the quarantine command." |
| 4:50 | — | — | "All attacks and network behaviour are simulated locally. The architecture is the same one a real deployment would use." |

**Backup plan:** if Mosquitto fails, the app keeps running in "direct" mode.
If the 3D view is slow, use the Network tab for the failover part.
