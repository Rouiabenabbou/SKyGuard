import json, subprocess, time, random
GE5 = {"p_gb": 0.2 * 0.05 / 0.95, "p_bg": 0.2}
P = [("LAN", {}), ("5G-like", {"delay_ms": 12, "jitter_ms": 3, "loss": 0.001}),
     ("LEO-like", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003}), ("GEO-like", {"delay_ms": 280}),
     ("Random-5%", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.05}), ("Burst-5%", {"delay_ms": 35, "jitter_ms": 6, "ge": GE5}),
     ("LEO-64kbps", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003, "rate_kbps": 64, "qmax_ms": 2000}),
     ("Outage-30s", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003, "outage": 30}),
     ("Outage-90s", {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003, "outage": 90})]
plan = [(n, c, r) for r in range(3) for n, c in P]
random.seed(42); random.shuffle(plan)
sub = subprocess.Popen(["../venv/bin/python", "x4_sub.py", "x4_out/recv.csv"])
time.sleep(2); log = open("x4_out/conditions.jsonl", "a")
for name, prof, r in plan:
    cfg = {"delay_ms": 0, "jitter_ms": 0, "loss": 0, "down": False, "ge": None, "rate_kbps": 0}
    cfg.update({k: v for k, v in prof.items() if k != "outage"})
    json.dump(cfg, open("sat.json", "w")); time.sleep(1)
    tag = f"{name}_r{r}"; dur = 200 if "outage" in prof else 120
    t0 = time.time()
    p = subprocess.Popen(["ip", "netns", "exec", "devns", "../venv/bin/python", "x4_pub.py", "--tag", tag, "--duration", str(dur)])
    cut = rest = None
    if "outage" in prof:
        time.sleep(3 + 60); cfg["down"] = True; json.dump(cfg, open("sat.json", "w")); cut = time.time()
        time.sleep(prof["outage"]); cfg["down"] = False; json.dump(cfg, open("sat.json", "w")); rest = time.time()
    p.wait()
    log.write(json.dumps({"tag": tag, "profile": name, "run": r, "cfg": cfg, "t0": t0, "t1": time.time(), "cut": cut, "restore": rest}) + "\n"); log.flush()
    print(tag, "done", flush=True)
sub.terminate()
