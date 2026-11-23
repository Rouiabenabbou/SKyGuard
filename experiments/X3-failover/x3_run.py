"""X3 orchestrator. Part A: outage sweep (10/30/120 s), 12 runs each in random order; in
every run the four modes run side by side (paired). Part B: no outage, bursty-loss
primary (LEO-like and GEO-like), 20 min each, to count false failovers."""
import json, random, subprocess, sys, time
GE5 = {"p_gb": 0.2 * 0.05 / 0.95, "p_bg": 0.2}
SAT = {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003, "ge": None, "rate_kbps": 0}
G5 = {"delay_ms": 12, "jitter_ms": 3, "loss": 0.001, "ge": None, "rate_kbps": 0, "down": False}
MODES = ["off", "reconnect", "fixed", "rtt"]
R = int(sys.argv[1]) if len(sys.argv) > 1 else 12
part = sys.argv[2] if len(sys.argv) > 2 else "AB"
json.dump(G5, open("/tmp/claude-0/exp/x/g5.json", "w"))
sub = subprocess.Popen(["../venv/bin/python", "../x/x4_sub.py", "recv.csv"]); time.sleep(2)
log = open("x3_runs.jsonl", "a")
def agents(tag, dur):
    ps = []
    for i, m in enumerate(MODES):
        ps.append(subprocess.Popen(["ip", "netns", "exec", "devns", "../venv/bin/python", "x3_agent.py", "--mode", m,
                                    "--device", f"X3-{tag}-{m}", "--duration", str(dur), "--out", f"runs/{tag}_{m}"]))
    return ps
if "A" in part:
    plan = [(o, r) for r in range(R) for o in (10, 30, 120)]; random.seed(3); random.shuffle(plan)
    for o, r in plan:
        json.dump({**SAT, "down": False}, open("/tmp/claude-0/exp/x/sat.json", "w")); time.sleep(2)
        tag = f"o{o}r{r}"; dur = 20 + o + 60
        ps = agents(tag, dur); time.sleep(20 + random.uniform(0, 1))
        json.dump({**SAT, "down": True}, open("/tmp/claude-0/exp/x/sat.json", "w")); tc = time.time(); time.sleep(o)
        json.dump({**SAT, "down": False}, open("/tmp/claude-0/exp/x/sat.json", "w")); tu = time.time()
        for p in ps: p.wait()
        log.write(json.dumps({"tag": tag, "outage": o, "run": r, "cut": tc, "restore": tu}) + "\n"); log.flush()
        print(tag, "done", flush=True)
if "B" in part:
    for name, prof in (("leo-burst", {**SAT, "ge": GE5}), ("geo-burst", {**SAT, "delay_ms": 280, "jitter_ms": 0, "ge": GE5})):
        json.dump({**prof, "down": False}, open("/tmp/claude-0/exp/x/sat.json", "w")); time.sleep(2)
        t0 = time.time(); ps = agents(name, 600)
        for p in ps: p.wait()
        log.write(json.dumps({"tag": name, "outage": 0, "t0": t0, "t1": time.time(), "cfg": prof}) + "\n"); log.flush()
        print(name, "done", flush=True)
sub.terminate()
