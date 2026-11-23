# Suggested Outline — Written Report and Presentation

## Written report (about 30–50 pages)

1. **Introduction**
   1.1 Background: IoT over satellite and 5G · 1.2 Problem statement · 1.3 Objectives · 1.4 Scope and limitations (simulation, ethics) · 1.5 Report structure
2. **Literature review**
   2.1 IoT architectures and MQTT · 2.2 Satellite–terrestrial integrated networks (LEO, NTN in 5G) · 2.3 IoT security threats (DoS/flooding, spoofing, rogue devices) · 2.4 Intrusion detection: rule-based vs machine learning · 2.5 Digital twins in networking · 2.6 Related work and the gap this project fills
3. **Requirements and design**
   3.1 Functional and non-functional requirements · 3.2 Architecture (diagram from README §3) · 3.3 Data model (tables, README §15) · 3.4 MQTT topic design · 3.5 Detection rules design · 3.6 Quarantine and failover design (state machine diagram, PHASE8_GUIDE) · 3.7 Dashboard and 3D/4D design
4. **Implementation**
   4.1 Technology choices and why · 4.2 Backend modules (ARCHITECTURE.md §5) · 4.3 Network simulator · 4.4 Detection engine · 4.5 Quarantine · 4.6 Failover · 4.7 3D twin and 4D timeline · 4.8 Dashboard · 4.9 ESP32 firmware · 4.10 Optional ML detector
5. **Testing and evaluation**
   5.1 Test strategy · 5.2 Automated tests (TESTING.md §1) · 5.3 Scenario tests and results table (TESTING.md §3) · 5.4 Discussion: detection time, false alerts, containment, availability, recovery time · 5.5 Limitations of the evaluation
6. **Conclusion and future work**
   6.1 Summary of achievements against the objectives · 6.2 Lessons learned · 6.3 Future work (TLS, authentication, multiple satellites, traffic-based ML, Docker)
- **References**
- **Appendices:** A. Installation guide (README §6–7) · B. API reference (README §16) · C. Phase guides · D. Firmware listing · E. Screenshots

## Presentation (12–15 slides, 10–15 minutes)

1. Title
2. Problem: why satellite–5G IoT needs security and resilience
3. Objectives
4. Architecture diagram
5. Technology stack
6. Simulated network and devices
7. Detection rules (table)
8. Quarantine flow
9. Failover state machine + results (2–4 s vs 25 s)
10. 3D digital twin (screenshot)
11. 4D timeline: incident replay (screenshot)
12. Real ESP32 device (photo + wiring)
13. Testing and evaluation results
14. Limitations and future work
15. Live demo (DEMO_SCRIPT.md) / Questions

**Screenshots to take:** Overview tab, 4D Twin (normal), 4D Twin (quarantine
cage), Network tab during the drill (backup 5G badges), timeline in replay,
Security tab with alert statistics, the report page, and the ESP32 serial monitor.
