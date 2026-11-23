"""X5 analysis: per run, restricted to the measurement window; then mean and SD over the 3 runs per level."""
import csv, glob, json, statistics as st
from collections import defaultdict
O = "/tmp/claude-0/exp/x5/out"
def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))] if v else float("nan")
runs = [json.loads(l) for l in open(f"{O}/runs.jsonl")]
per = defaultdict(list)
for ru in runs:
    tag, t0, t1 = ru["tag"], ru["t_meas"], ru["t_end"]
    sent = {}
    for f in glob.glob(f"{O}/{tag}_sent*.csv"):
        for d, s, ts in csv.reader(open(f)):
            ts = int(ts) / 1000
            if t0 <= ts <= t1: sent[(d, int(s))] = ts
    proc = {}
    try:
        for r in csv.reader(open(f"{O}/{tag}_proc.csv")):
            k = (r[0], int(r[1]))
            if k in sent and k not in proc: proc[k] = (float(r[2]), float(r[3]), float(r[4]))
    except FileNotFoundError: pass
    e2e = [(proc[k][2] - sent[k]) * 1000 for k in proc]
    pt = [(v[2] - v[1]) * 1000 for v in proc.values()]
    qt = [(v[1] - v[0]) * 1000 for v in proc.values()]
    res = json.load(open(f"{O}/{tag}_res.json"))
    S = [s for s in res["samples"] if t0 <= s[0] <= t1]
    A = [a for a in res["api"] if t0 <= a[0] <= t1]
    ok = [a[1] * 1000 for a in A if a[2]]
    total_rows = None
    try:
        import sqlite3; total_rows = sqlite3.connect(f"{O}/{tag}.db").execute("select count(*) from telemetry").fetchone()[0]
    except Exception: pass
    m = {"sent": len(sent), "delivered": len(proc), "delivery_pct": 100 * len(proc) / len(sent) if sent else float("nan"),
         "rate_offered": len(sent) / (t1 - t0), "throughput": len(proc) / (t1 - t0),
         "e2e_med": pct(e2e, .5), "e2e_p95": pct(e2e, .95), "e2e_p99": pct(e2e, .99), "proc_med": pct(pt, .5), "proc_p95": pct(pt, .95),
         "queue_med": pct(qt, .5), "queue_p95": pct(qt, .95),
         "cpu_backend": st.mean(s[1] for s in S) if S else float("nan"), "rss_max": max((s[2] for s in S), default=float("nan")),
         "cpu_broker": st.mean(s[3] for s in S) if S else float("nan"),
         "api_med": pct(ok, .5), "api_p95": pct(ok, .95), "api_ok": f"{len(ok)}/{len(A)}",
         "db_bytes": ru["db_bytes"], "db_rows": total_rows, "bytes_per_row": ru["db_bytes"] / total_rows if total_rows else None}
    per[(ru["n"], ru["interval"])].append(m)
    print(tag, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()})
out = {}
for k in sorted(per, key=lambda x: (x[1] != 5.0, x[0])):
    rs = per[k]; agg = {"runs": len(rs)}
    for f in rs[0]:
        v = [r[f] for r in rs if isinstance(r[f], (int, float)) and r[f] == r[f]]
        if v: agg[f] = {"mean": st.mean(v), "sd": st.stdev(v) if len(v) > 1 else 0.0}
    agg["api_ok"] = [r["api_ok"] for r in rs]
    out[f"{k[0]}@{k[1]:g}s"] = agg
    g = lambda f: f"{agg[f]['mean']:.1f}±{agg[f]['sd']:.1f}" if f in agg else "-"
    print(f"n={k[0]:5d} iv={k[1]:g}s runs={len(rs)} rate {g('rate_offered')} deliv {g('delivery_pct')}% e2e med {g('e2e_med')} p95 {g('e2e_p95')} p99 {g('e2e_p99')} "
          f"proc {g('proc_med')} queue p95 {g('queue_p95')} cpu {g('cpu_backend')}% rss {g('rss_max')}MB broker {g('cpu_broker')}% api {g('api_med')}/{g('api_p95')} B/row {g('bytes_per_row')}")
json.dump(out, open("/tmp/claude-0/exp/x5/x5_results.json", "w"), indent=1)
