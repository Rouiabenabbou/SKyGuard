"""X4 analysis: per run and QoS level: delivery, duplicates, latency percentiles; then per
profile: mean and 95% t-interval across the 3 runs (runs are the unit of repetition)."""
import csv, json, math, statistics as st
from collections import defaultdict
recv = defaultdict(list)
for r in csv.reader(open("x4_out/recv.csv")):
    recv[(r[0], int(r[1]), int(r[2]))].append(int(r[3]))
T95 = {2: 4.303, 3: 3.182, 4: 2.776}
def ci(v):
    if len(v) < 2: return 0.0
    return T95.get(len(v) - 1, 2.0) * st.stdev(v) / math.sqrt(len(v))
def pct(v, p):
    v = sorted(v); k = (len(v) - 1) * p; lo, hi = math.floor(k), math.ceil(k); return v[lo] + (v[hi] - v[lo]) * (k - lo)
runs = defaultdict(lambda: defaultdict(list))
for line in open("x4_out/conditions.jsonl"):
    c = json.loads(line)
    sent = list(csv.DictReader(open(f"x4_out/{c['tag']}_sent.csv")))
    ev = [l.strip().split(",") for l in open(f"x4_out/{c['tag']}_events.csv")]
    for q in ("0", "1"):
        s = [x for x in sent if x["qos"] == q]
        lat, dup, got = [], 0, 0
        for x in s:
            k = (x["device_id"], int(x["seq"]), int(x["ts_sent_ms"]))
            if k in recv:
                got += 1; dup += len(recv[k]) - 1; lat.append(min(recv[k]) - k[2])
        t_stop = c["t0"] + 3 + 4 + (200 if c["cut"] else 120)  # end of publishing (before the final clean disconnect)
        disc = sum(1 for e in ev if e[1] == "disconnect" and e[0].startswith(f"Q{q}") and float(e[2]) < t_stop)
        runs[(c["profile"], int(q))]["delivery"].append(100 * got / len(s))
        runs[(c["profile"], int(q))]["dup"].append(dup)
        runs[(c["profile"], int(q))]["p50"].append(pct(lat, .5)); runs[(c["profile"], int(q))]["p95"].append(pct(lat, .95))
        runs[(c["profile"], int(q))]["max"].append(max(lat)); runs[(c["profile"], int(q))]["disc"].append(disc)
        runs[(c["profile"], int(q))]["sent"].append(len(s))
order = ["LAN", "5G-like", "LEO-like", "GEO-like", "Random-5%", "Burst-5%", "LEO-64kbps", "Outage-30s", "Outage-90s"]
print("profile,qos,runs,sent_per_run,delivery_mean,delivery_ci,dup_mean,p50_mean,p50_ci,p95_mean,p95_ci,max_mean,disconnects_mean")
res = []
for p in order:
    for q in (0, 1):
        r = runs.get((p, q))
        if not r: continue
        row = [p, q, len(r["p50"]), round(st.mean(r["sent"])), round(st.mean(r["delivery"]), 2), round(ci(r["delivery"]), 2),
               round(st.mean(r["dup"]), 1), round(st.mean(r["p50"]), 1), round(ci(r["p50"]), 1), round(st.mean(r["p95"]), 1),
               round(ci(r["p95"]), 1), round(st.mean(r["max"])), round(st.mean(r["disc"]), 1)]
        res.append(row); print(",".join(map(str, row)))
json.dump({"rows": res, "raw": {f"{k[0]}|{k[1]}": v for k, v in runs.items()}}, open("x4_results.json", "w"), indent=1)
