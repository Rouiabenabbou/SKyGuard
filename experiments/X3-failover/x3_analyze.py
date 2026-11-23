"""X3 analysis (paired: the four modes share each outage)."""
import csv, json, math, random, statistics as st
from collections import defaultdict
from scipy.stats import wilcoxon
MODES = ["off", "reconnect", "fixed", "rtt"]
recv = defaultdict(list)
for r in csv.reader(open("recv.csv")):
    if r[0].startswith("X3-"): recv[r[0]].append((int(r[1]), int(r[2]), int(r[3]) / 1000))
def boot(v, n=2000):
    random.seed(1); m = sorted(st.median(random.choices(v, k=len(v))) for _ in range(n)); return m[int(.025 * n)], m[int(.975 * n)]
runs = [json.loads(l) for l in open("x3_runs.jsonl")]
A = defaultdict(lambda: defaultdict(dict)); B = {}
for ru in runs:
    for m in MODES:
        dev = f"X3-{ru['tag']}-{m}"
        sent = list(csv.DictReader(open(f"runs/{ru['tag']}_{m}_send.csv")))
        ev = list(csv.DictReader(open(f"runs/{ru['tag']}_{m}_events.csv")))
        rv = sorted(recv[dev], key=lambda x: x[2])
        first, seen, ooo, mx = {}, set(), 0, 0
        for s, ts, t in rv:
            if s in seen: continue
            seen.add(s); first[s] = (ts, t)
            if s < mx: ooo += 1
            mx = max(mx, s)
        dup = len(rv) - len(seen)
        lost = sum(1 for x in sent if int(x["seq"]) not in seen)
        sw = [float(e["t"]) for e in ev if e["event"] == "state" and e["detail"] == "switching"]
        fb = [float(e["t"]) for e in ev if e["event"] == "state" and e["detail"].startswith("primary(failback)")]
        if ru["outage"] == 0:
            hrs = (ru["t1"] - ru["t0"]) / 3600
            B[(ru["tag"], m)] = {"false_failovers": len(sw), "per_hour": len(sw) / hrs, "dup": dup, "lost": lost, "ooo": ooo}
            continue
        cut, rest = ru["cut"], ru["restore"]
        times = sorted(t for ts, t in first.values() if t >= cut - 5)
        gaps = [b - a for a, b in zip(times, times[1:])]
        outage_ts = [t - ts / 1000 for ts, t in first.values() if cut <= ts / 1000 <= rest]
        fbgap = None
        if fb:
            ft = sorted(t for ts, t in first.values() if fb[0] - 3 <= t <= fb[0] + 6)
            fbgap = max((b - a for a, b in zip(ft, ft[1:])), default=None)
        A[ru["outage"]][m][ru["run"]] = {"detect": (sw[0] - cut) if sw and sw[0] >= cut - 1 else None,
            "early_switch": bool(sw and sw[0] < cut - 1), "interruption": max(gaps) if gaps else None,
            "max_delay": max(outage_ts) if outage_ts else None, "lost": lost, "dup": dup, "ooo": ooo, "failback_gap": fbgap,
            "failback": bool(fb)}
out = {"A": {}, "B": {f"{k[0]}|{k[1]}": v for k, v in B.items()}}
for o in sorted(A):
    out["A"][o] = {}
    print(f"== outage {o} s")
    for m in MODES:
        rs = A[o][m]; get = lambda k: [r[k] for r in rs.values() if r[k] is not None]
        d = {k: get(k) for k in ("detect", "interruption", "max_delay", "lost", "dup", "ooo", "failback_gap")}
        summ = {k: {"n": len(v), "median": st.median(v), "ci": boot(v) if len(v) > 2 else None, "mean": st.mean(v), "sd": st.stdev(v) if len(v) > 1 else 0} for k, v in d.items() if v}
        summ["failbacks"] = sum(r["failback"] for r in rs.values()); summ["runs"] = len(rs)
        out["A"][o][m] = summ
        f = lambda k: f"{summ[k]['median']:.2f} [{summ[k]['ci'][0]:.2f},{summ[k]['ci'][1]:.2f}]" if k in summ and summ[k]['ci'] else "-"
        print(f"  {m:9s} n={len(rs)} detect {f('detect')} interr {f('interruption')} maxdelay {f('max_delay')} lost {sum(d['lost'])} dup {sum(d['dup'])} ooo {sum(d['ooo'])} fbgap {f('failback_gap')} fb {summ['failbacks']}")
    tests = {}
    for m1, m2 in (("off", "fixed"), ("reconnect", "fixed"), ("fixed", "rtt"), ("off", "reconnect")):
        ks = sorted(set(A[o][m1]) & set(A[o][m2]))
        x = [A[o][m1][k]["interruption"] for k in ks]; y = [A[o][m2][k]["interruption"] for k in ks]
        pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
        if len(pairs) >= 5:
            dd = [a - b for a, b in pairs]
            w = wilcoxon([a for a, b in pairs], [b for a, b in pairs])
            n = len(pairs); pos = sum(1 for v in dd if v > 0); neg = sum(1 for v in dd if v < 0)
            tests[f"{m1}-{m2}"] = {"n": n, "W": float(w.statistic), "p": float(w.pvalue), "median_diff": st.median(dd), "rank_biserial_sign": (pos - neg) / n}
            print(f"  Wilcoxon {m1} vs {m2}: n={n} W={w.statistic:.1f} p={w.pvalue:.2e} median diff {st.median(dd):.2f}s")
    out["A"][o]["tests"] = tests
for k, v in B.items(): print("B", k, v)
out["raw"] = {str(o): {m: A[o][m] for m in MODES} for o in A}
json.dump(out, open("x3_results.json", "w"), indent=1, default=str)
