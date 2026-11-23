# CyberShield benchmark results

Measured 2026-11-05 13:46 on the simulated network.

| Metric | Result |
|---|---|
| Attacks detected | 13 / 13 (100.0 %) |
| Mean time to detect | 0.78 s (median 0.07 s, max 1.87 s) |
| False alarms on normal traffic | 1 in 5 min |
| Average handover (satellite to 5G) | 2224 ms |
| Average service interruption | 1539 ms |

| Attack | Target | Detected | Time (s) | Alert | Severity |
|---|---|---|---|---|---|
| excessive-traffic | IOT-002 | yes | 0.03 | ml_anomaly | medium |
| unauthorized-device | IOT-999 | yes | 0.03 | unauthorized_device | high |
| abnormal-reading | IOT-001 | yes | 0.07 | abnormal_sensor_value | high |
| connection-storm | IOT-003 | yes | 1.62 | suspicious_connections | high |
| mqtt-brute-force | IOT-002 | yes | 1.85 | mqtt_bruteforce | high |
| unauthorized-publish | IOT-002 | yes | 0.03 | unauthorized_publish | high |
| botnet-beaconing | IOT-003 | yes | 0.03 | threat_intel_match | critical |
| port-scan | IOT-001 | yes | 1.62 | port_scan | medium |
| data-exfiltration | IOT-003 | yes | 0.07 | threat_intel_match | high |
| 5g-auth-attack | IOT-002 | yes | 1.87 | 5g_auth_anomaly | high |
| config-tampering | IOT-001 | yes | 0.04 | unauthorized_config_change | high |
| gnss-jamming | IOT-001 | yes | 1.85 | gnss_jamming | critical |
| gnss-spoofing | IOT-003 | yes | 1.06 | gnss_spoofing | high |
