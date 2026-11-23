"""Score X1 for both engines on identical traffic.
TP: the expected alert on a target between t_start and t_end + 10 s. FP: any other alert on
one of the 26 experiment devices in the run period (alerts on other experiments' device IDs
are ignored). FP are attributed to the link context in force at the alert time; alerts within
30 s after an outage ends are labelled 'post-outage'."""
import csv, json, math, sqlite3, statistics as st, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
W = 10.0
EXP = {"flood": "excessive_message_rate", "lowslow": "excessive_message_rate", "forged": "excessive_message_rate",
       "distributed": "excessive_message_rate", "connstorm": "suspicious_connections", "abnormal": "abnormal_sensor_value"}
def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)
out_dir = sys.argv[1] if len(sys.argv) > 1 else "x1_out"
sched = [l.strip().split(",", 2) for l in open(f"{out_dir}/link_schedule.csv")]
sched = [(float(t), c) for t, c, _ in sched]
t_begin, t_end = sched[0][0], sched[-1][0] + 60
meta = json.load(open(f"{out_dir}/meta.json"))
outs = [o for o in meta["outages"] if o[1]]
def ctx_at(t):
    for a, b in outs:
        if b <= t <= b + 30: return "post-outage"
    c = "normal"
    for ts, cc in sched:
        if ts <= t: c = cc
    return "outage" if c.startswith("outage") else c
db0 = sqlite3.connect(f"{out_dir}/unaware.db")
devs = {r[0] for r in db0.execute("select device_id from devices")}
inj = list(csv.DictReader(open(f"{out_dir}/injections.csv")))
items = []  # (type, target(s), t0, t1, ctx)
for r in inj:
    tg = r["targets"].split("|"); t0, t1 = float(r["t_start"]), float(r["t_end"])
    if r["type"] == "concurrent":
        items += [("flood(conc)", [tg[0]], t0, t1, r["ctx_start"], "excessive_message_rate"),
                  ("abnormal(conc)", [tg[1]], t0, t1, r["ctx_start"], "abnormal_sensor_value"),
                  ("connstorm(conc)", [tg[2]], t0, t1, r["ctx_start"], "suspicious_connections")]
    else:
        items.append((r["type"], tg, t0, t1, r["ctx_start"], EXP[r["type"]]))
res = {}
import glob, os
ENGINES = sorted((os.path.basename(f)[:-3] for f in glob.glob(f"{out_dir}/*.db")), key=lambda e: (e != "unaware", e))
for eng in ENGINES:
    db = sqlite3.connect(f"{out_dir}/{eng}.db")
    al = []
    for aid, dev, typ, ts in db.execute("select id,device_id,alert_type,timestamp from security_alerts"):
        t = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp()
        if t_begin <= t <= t_end and dev in devs: al.append({"id": aid, "dev": dev, "type": typ, "t": t})
    used = set(); per = defaultdict(list); lat = defaultdict(list); perctx = defaultdict(list)
    for ty, tg, t0, t1, cx, exp in items:
        hits = [x for x in al if x["dev"] in tg and t0 <= x["t"] <= t1 + W]
        used |= {x["id"] for x in hits}
        ok = any(x["type"] == exp for x in hits)
        base = ty.split("(")[0]
        per[ty].append(ok); perctx[(base, "outage" if cx.startswith("outage") else cx)].append(ok)
        if ok: lat[ty].append(min(x["t"] for x in hits if x["type"] == exp) - t0)
    fps = [x for x in al if x["id"] not in used]
    hours = (t_end - t_begin) / 3600
    fpctx = Counter((ctx_at(x["t"]), x["type"]) for x in fps)
    res[eng] = {"hours": hours, "device_hours": hours * len(devs), "alerts": len(al), "fp": len(fps),
                "fp_per_dev_h": len(fps) / (hours * len(devs)), "fp_by_ctx_type": {f"{a}|{b}": n for (a, b), n in fpctx.items()},
                "recall": {ty: [sum(v), len(v), *wilson(sum(v), len(v))] for ty, v in per.items()},
                "recall_by_ctx": {f"{a}|{b}": [sum(v), len(v)] for (a, b), v in perctx.items()},
                "ttd_median": {ty: st.median(v) for ty, v in lat.items() if v}}
    print(f"== {eng}: {len(al)} alerts, {len(fps)} FP in {hours:.2f} h ({len(fps)/(hours*len(devs)):.4f} per device-hour)")
    print("   FP by context/type:", dict(fpctx))
    for ty, v in sorted(per.items()):
        lo, hi = wilson(sum(v), len(v)); print(f"   {ty:16s} {sum(v)}/{len(v)}  CI {lo:.2f}-{hi:.2f}  TTD {st.median(lat[ty]) if lat[ty] else float('nan'):.2f}s")
json.dump(res, open(f"{out_dir}/x1_results.json", "w"), indent=1)
pr = json.load(open(f"{out_dir}/x1_results.json"))
