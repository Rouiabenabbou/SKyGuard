"""Emulator validation: send N UDP probes device->host through the emulated link and
measure exact one-way delay (shared clock) and loss, incl. loss-burst lengths.
Runs the receiver in the root namespace and the sender inside devns."""
import json, socket, statistics, subprocess, sys, time, math
PROFILES = [
    ("5G-like",  {"delay_ms": 12, "jitter_ms": 3, "loss": 0.001}),
    ("LEO-like", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003}),
    ("GEO-like", {"delay_ms": 280, "jitter_ms": 0, "loss": 0.0}),
    ("Lossy-5%", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.05}),
    ("Burst-5%", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.0, "ge": {"p_gb": 0.2 * 0.05 / 0.95, "p_bg": 0.2}}),
    ("LEO-64k",  {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003, "rate_kbps": 64, "qmax_ms": 2000}),
]
N, GAP = int(sys.argv[1]) if len(sys.argv) > 1 else 3000, 0.02
SENDER = r'''
import socket, time, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for i in range(int(sys.argv[1])):
    s.sendto(f"{i} {time.time()}".encode().ljust(100), ("10.9.0.1", 9999)); time.sleep(float(sys.argv[2]))
'''
open("_sender.py", "w").write(SENDER)
out = []
for name, cfg in PROFILES:
    c = {"delay_ms": 0, "jitter_ms": 0, "loss": 0, "down": False, "ge": None, "rate_kbps": 0}; c.update(cfg)
    json.dump(c, open("sat.json", "w")); time.sleep(0.5)
    r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); r.bind(("10.9.0.1", 9999)); r.settimeout(3)
    p = subprocess.Popen(["ip", "netns", "exec", "devns", "../venv/bin/python", "_sender.py", str(N), str(GAP)])
    got = {}
    try:
        while True:
            d, _ = r.recvfrom(200); t = time.time()
            i, ts = d.split()[:2]; got[int(i)] = (t - float(ts)) * 1000
    except socket.timeout:
        pass
    p.wait(); r.close()
    lat = list(got.values()); lost = [i for i in range(N) if i not in got]
    bursts, run = [], 0
    for i in range(N):
        if i not in got: run += 1
        elif run: bursts.append(run); run = 0
    row = {"profile": name, "cfg": cfg, "sent": N, "recv": len(got), "loss_meas": round(len(lost) / N, 4),
           "mean_ms": round(statistics.mean(lat), 2), "sd_ms": round(statistics.stdev(lat), 2),
           "p50_ms": round(statistics.median(lat), 2), "mean_burst": round(statistics.mean(bursts), 2) if bursts else 0}
    print(json.dumps(row), flush=True); out.append(row)
json.dump(out, open("x4_validation.json", "w"), indent=1)
