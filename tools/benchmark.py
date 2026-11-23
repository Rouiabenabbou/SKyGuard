"""
CyberShield benchmark (v2.5.1): measures the numbers for the report/competition.

  1. False alarms: normal traffic only for --baseline seconds, count security alerts.
  2. Detection: runs every simulated attack once, measures the time until the first alert.
  3. Failover: a satellite outage drill, reads handover and interruption times.

Run with the backend started (uvicorn app.main:app --port 8000):
    python tools/benchmark.py --user admin --password Admin@2026
It RESETS the simulation (wipes alerts/history). Results: tools/benchmark_results.{md,json}
Everything is simulated; the numbers describe this software model, not a real network.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

import httpx

NOT_ATTACKS = {"link_failure", "node_failure", "malformed_message", "link_degraded"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="Admin@2026")
    ap.add_argument("--baseline", type=float, default=300, help="seconds of normal traffic for the false-alarm test")
    ap.add_argument("--timeout", type=float, default=60, help="max seconds to wait for each detection")
    ap.add_argument("--drill", type=float, default=30)
    a = ap.parse_args()

    c = httpx.Client(base_url=a.url, timeout=30)
    r = c.post("/api/auth/login", json={"username": a.user, "password": a.password})
    if r.status_code == 200 and r.json().get("token"):
        c.headers["Authorization"] = "Bearer " + r.json()["token"]

    def alerts():
        return c.get("/api/alerts", params={"limit": 500}).json()["alerts"]

    def reset(settle=4):
        c.post("/api/simulation/reset")
        time.sleep(settle)

    # 1. false alarms
    reset()
    print(f"[1/3] normal traffic for {a.baseline:.0f} s ...")
    t0 = time.time()
    time.sleep(a.baseline)
    base = [x for x in alerts() if x["alert_type"] not in NOT_ATTACKS]
    print(f"      {len(base)} security alerts on normal traffic: {[x['alert_type'] for x in base]}")

    # 2. detection per attack
    names = [
        "excessive-traffic", "unauthorized-device", "abnormal-reading", "connection-storm",
        "mqtt-brute-force", "unauthorized-publish", "botnet-beaconing", "port-scan", "data-exfiltration",
        "5g-auth-attack", "config-tampering", "gnss-jamming", "gnss-spoofing"]
    rows = []
    for i, name in enumerate(names, 1):
        reset(25)  # let the previous attack finish so its alerts don't count here
        before = {x["id"] for x in alerts()}
        start = time.time()
        info = c.post(f"/api/simulation/attack/{name}").json()
        hit = None
        while time.time() - start < a.timeout:
            new = [x for x in alerts() if x["id"] not in before and x["alert_type"] not in NOT_ATTACKS
                   and x["device_id"] == info.get("device_id")]
            if new:
                hit = (time.time() - start, sorted(new, key=lambda x: x["id"])[0])
                break
            time.sleep(0.25)
        row = {"attack": name, "target": info.get("device_id"), "detected": bool(hit),
               "seconds": round(hit[0], 2) if hit else None, "alert": hit[1]["alert_type"] if hit else None,
               "severity": hit[1]["severity"] if hit else None}
        rows.append(row)
        print(f"[2/3] {i:2}/{len(names)} {name:22} " + (f"detected in {row['seconds']:.2f} s ({row['alert']})" if hit else "NOT detected"))

    # 3. failover
    reset()
    time.sleep(6)
    print(f"[3/3] satellite outage drill {a.drill:.0f} s ...")
    c.post("/api/failover/drill", params={"seconds": a.drill})
    time.sleep(a.drill + 16)
    fo = c.get("/api/failover/status").json()

    det = [r["seconds"] for r in rows if r["detected"]]
    hours = a.baseline / 3600 if a.baseline else 0
    res = {
        "attacks": len(rows), "detected": len(det),
        "detection_rate_pct": round(100 * len(det) / len(rows), 1) if rows else None,
        "detection_s_mean": round(statistics.mean(det), 2) if det else None,
        "detection_s_median": round(statistics.median(det), 2) if det else None,
        "detection_s_max": round(max(det), 2) if det else None,
        "baseline_seconds": a.baseline, "false_alarms": len(base),
        "false_alarms_per_hour": round(len(base) / hours, 2) if hours else None,
        "failover": fo, "per_attack": rows,
        "measured_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    out = Path(__file__).with_name("benchmark_results.json")
    out.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    s = fo.get("stats", fo)
    md = ["# CyberShield benchmark results", "", f"Measured {res['measured_at']} on the simulated network.", "",
          "| Metric | Result |", "|---|---|",
          f"| Attacks detected | {len(det)} / {len(rows)} ({res['detection_rate_pct']} %) |",
          f"| Mean time to detect | {res['detection_s_mean']} s (median {res['detection_s_median']} s, max {res['detection_s_max']} s) |",
          f"| False alarms on normal traffic | {len(base)} in {a.baseline / 60:.0f} min |",
          f"| Average handover (satellite to 5G) | {s.get('avg_handover_ms')} ms |",
          f"| Average service interruption | {s.get('avg_interruption_ms')} ms |",
          "", "| Attack | Target | Detected | Time (s) | Alert | Severity |", "|---|---|---|---|---|---|"]
    md += [f"| {r['attack']} | {r['target']} | {'yes' if r['detected'] else 'no'} | {r['seconds'] or '-'} | {r['alert'] or '-'} | {r['severity'] or '-'} |" for r in rows]
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[4:9]))
    print(f"saved {out} and {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
