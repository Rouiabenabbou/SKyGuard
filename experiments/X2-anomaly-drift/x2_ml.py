"""X2: anomaly detectors for CyberShield telemetry under drift (offline, synthetic data).

Data: 12 devices, 7 days, one reading every 30 s, generated in simulated time:
diurnal cycle + slow AR(1) weather process + sensor noise, humidity anti-correlated
with temperature, half of the devices quantised like a DHT11 (1 C / 1 %), 1 % missing.
Drift scenarios on the test days (5-7): none | step (3 devices relocated at day 5:
+6 C, -15 % RH; the IOT-009 case) | seasonal (+0.8 C/day on all devices from day 1).
Split per device, chronological: train days 1-3, validation day 4 (threshold), test 5-7.
Anomaly episodes (test days only, labelled per reading): stuck, drift (slow ramp to
+4 sd), replay (segment from 12 h earlier), jump (+3 sd offset), noise (+2 sd noise),
spike (one out-of-range reading; the range rule's job). All but spike are kept inside
the device's allowed range.
Detectors: range rule; per-device z-score (max |feature|); autoencoder 4-8-2-8-4 tanh
(same shape as the platform's); LOF (novelty); Isolation Forest; One-Class SVM.
Feature sets: 'point' = the platform's 4 features (z_T, z_H, |dT|/sd, |dH|/sd);
'window' = point + rolling sd of T and H over 12 readings (6 min).
Normalisation: 'static' (train stats, as shipped) | 'adaptive' (per-device mean/sd
re-estimated daily from the previous 3 days of readings not flagged by the range rule).
Threshold: 99.95th percentile of the detector's score on validation day 4.
"""
import json, sys, time, warnings
import numpy as np
from sklearn.neighbors import LocalOutlierFactor
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import roc_auc_score, average_precision_score
warnings.filterwarnings("ignore")

DT, DAYS, ND = 30, 7, 12
PER_DAY = 86400 // DT
N = DAYS * PER_DAY
TYPES = ["stuck", "drift", "replay", "jump", "noise", "spike"]
EP_LEN = {"stuck": 60, "drift": 120, "replay": 120, "jump": 30, "noise": 60, "spike": 1}


def gen(rng, scenario):
    T = np.zeros((ND, N)); H = np.zeros((ND, N)); lo = np.zeros((ND, 2)); hi = np.zeros((ND, 2))
    t = np.arange(N) * DT
    for d in range(ND):
        mu_t, amp, mu_h = rng.uniform(5, 35), rng.uniform(1.5, 6), rng.uniform(25, 70)
        ph = rng.uniform(0, 2 * np.pi)
        w = np.zeros(N); a = np.exp(-DT / (6 * 3600)); s = 1.5 * np.sqrt(1 - a * a)
        e = rng.normal(0, s, N)
        for i in range(1, N): w[i] = a * w[i - 1] + e[i]
        tt = mu_t + amp * np.sin(2 * np.pi * t / 86400 + ph) + w + rng.normal(0, 0.3, N)
        hh = mu_h - 1.8 * (tt - mu_t) + rng.normal(0, 0.8, N)
        if scenario == "seasonal": tt = tt + 0.8 * t / 86400
        if scenario == "step" and d < 3:
            k = 4 * PER_DAY; tt[k:] += 6; hh[k:] -= 15
        if d % 2 == 0: tt, hh = np.round(tt), np.round(hh)
        hh = np.clip(hh, 0, 100)
        T[d], H[d] = tt, hh
        # allowed range as an operator would set it: training-period mean +/- (amp + 4 sd weather) + margin
        tr = slice(0, 3 * PER_DAY)
        lo[d] = [T[d, tr].mean() - amp - 8, H[d, tr].mean() - 1.8 * amp - 20]
        hi[d] = [T[d, tr].mean() + amp + 8 + (6 if scenario == "step" and d < 3 else 0) + (5 if scenario == "seasonal" else 0),
                 H[d, tr].mean() + 1.8 * amp + 20]
        if scenario == "step" and d < 3: lo[d, 1] -= 15  # operator updated the range after relocation
    return T, H, lo, hi


def inject(rng, T, H, lo, hi, per_type=8):
    lab = np.zeros((ND, N), bool); eps = []
    start, end = 4 * PER_DAY, N - 200
    for ty in TYPES:
        for _ in range(per_type):
            for _try in range(50):
                d, s = rng.integers(ND), rng.integers(start, end); L = EP_LEN[ty]
                if not lab[d, max(0, s - 150):s + L + 150].any(): break
            sl = slice(s, s + L); sdT, sdH = T[d, :3 * PER_DAY].std(), H[d, :3 * PER_DAY].std()
            if ty == "stuck": T[d, sl], H[d, sl] = T[d, s - 1], H[d, s - 1]
            elif ty == "drift": r = np.linspace(0, 4, L); T[d, sl] += r * sdT; H[d, sl] -= r * sdH
            elif ty == "replay": T[d, sl], H[d, sl] = T[d, s - PER_DAY // 2:s - PER_DAY // 2 + L], H[d, s - PER_DAY // 2:s - PER_DAY // 2 + L]
            elif ty == "jump": T[d, sl] += 3 * sdT; H[d, sl] -= 3 * sdH
            elif ty == "noise": T[d, sl] += rng.normal(0, 2 * sdT, L); H[d, sl] += rng.normal(0, 2 * sdH, L)
            elif ty == "spike": T[d, s] = hi[d, 0] + rng.uniform(3, 10)
            if ty != "spike":
                T[d, sl] = np.clip(T[d, sl], lo[d, 0] + 0.5, hi[d, 0] - 0.5); H[d, sl] = np.clip(H[d, sl], max(0, lo[d, 1] + 0.5), min(100, hi[d, 1] - 0.5))
            lab[d, sl] = True; eps.append((ty, d, s, L))
    return lab, eps


def roll_sd(x, k=12):
    c1 = np.cumsum(np.insert(x, 0, 0)); c2 = np.cumsum(np.insert(x * x, 0, 0))
    out = np.zeros_like(x)
    for i in range(len(x)):
        j = max(0, i - k + 1); n = i - j + 1
        m = (c1[i + 1] - c1[j]) / n; out[i] = np.sqrt(max(0, (c2[i + 1] - c2[j]) / n - m * m))
    return out


def stats(T, H, miss, rule, norm):
    """per device and reading: mean/sd used to normalise that reading."""
    mT = np.zeros((ND, N)); sT = np.zeros((ND, N)); mH = np.zeros((ND, N)); sH = np.zeros((ND, N))
    for d in range(ND):
        for day in range(DAYS):
            sl = slice(day * PER_DAY, (day + 1) * PER_DAY)
            if norm == "static" or day < 3:
                src = slice(0, 3 * PER_DAY); ok = ~miss[d, src]
                tt, hh = T[d, src][ok], H[d, src][ok]
            else:
                src = slice((day - 3) * PER_DAY, day * PER_DAY); ok = ~miss[d, src] & ~rule[d, src]
                tt, hh = T[d, src][ok], H[d, src][ok]
            mT[d, sl], sT[d, sl], mH[d, sl], sH[d, sl] = tt.mean(), max(tt.std(), 0.3), hh.mean(), max(hh.std(), 0.5)
    return mT, sT, mH, sH


def features(T, H, miss, st, fs):
    mT, sT, mH, sH = st; F = []
    for d in range(ND):
        idx = np.where(~miss[d])[0]  # missing readings never arrive; deltas use the previous *received* reading
        t, h = T[d, idx], H[d, idx]
        dt = np.abs(np.diff(t, prepend=t[0])); dh = np.abs(np.diff(h, prepend=h[0]))
        f = [(t - mT[d, idx]) / sT[d, idx], (h - mH[d, idx]) / sH[d, idx], dt / sT[d, idx], dh / sH[d, idx]]
        if fs == "window": f += [roll_sd(t) / sT[d, idx], roll_sd(h) / sH[d, idx]]
        F.append((idx, np.stack(f, 1)))
    return F


def run(seed, scenario, fs, norm):
    rng = np.random.default_rng(seed)
    T, H, lo, hi = gen(rng, scenario)
    lab, eps = inject(rng, T, H, lo, hi)
    miss = rng.random((ND, N)) < 0.01; miss[:, 0] = False
    for ty, d, s, L in eps: miss[d, s:s + L] = False  # attack readings are delivered
    rule = (T < lo[:, :1]) | (T > hi[:, :1]) | (H < lo[:, 1:]) | (H > hi[:, 1:])
    st = stats(T, H, miss, rule, norm)
    F = features(T, H, miss, st, fs)
    split = lambda a, b: np.concatenate([f[(idx >= a * PER_DAY) & (idx < b * PER_DAY)] for idx, f in F])
    Xtr, Xva = split(0, 3), split(3, 4)
    Xte = np.concatenate([f[idx >= 4 * PER_DAY] for idx, f in F])
    yte = np.concatenate([lab[d, idx[idx >= 4 * PER_DAY]] for d, (idx, f) in enumerate(F)])
    rte = np.concatenate([rule[d, idx[idx >= 4 * PER_DAY]] for d, (idx, f) in enumerate(F)])
    pos = [(d, idx[idx >= 4 * PER_DAY]) for d, (idx, f) in enumerate(F)]
    sub = rng.choice(len(Xtr), min(20000, len(Xtr)), replace=False)
    models = {
        "zscore": None,
        "AE": MLPRegressor(hidden_layer_sizes=(8, 2, 8), activation="tanh", max_iter=300, random_state=seed),
        "LOF": LocalOutlierFactor(n_neighbors=20, novelty=True),
        "IForest": IsolationForest(n_estimators=200, random_state=seed),
        "OCSVM": OneClassSVM(nu=0.005, gamma="scale"),
    }
    res = []
    for name, m in models.items():
        t0 = time.time()
        if name == "zscore": sc = lambda X: np.abs(X).max(1)
        elif name == "AE": m.fit(Xtr[sub], Xtr[sub]); sc = lambda X, m=m: ((m.predict(X) - X) ** 2).mean(1)
        elif name == "OCSVM": m.fit(Xtr[sub[:5000]]); sc = lambda X, m=m: -m.decision_function(X)
        else: m.fit(Xtr[sub]); sc = lambda X, m=m: -m.score_samples(X)
        thr = np.quantile(sc(Xva), 0.9995)
        s = sc(Xte); flag = s > thr
        res.append(evaluate(name, s, flag, yte, rte, pos, eps, seed, scenario, fs, norm, time.time() - t0))
    # rules only
    res.append(evaluate("rules", rte.astype(float), rte, yte, rte, pos, eps, seed, scenario, fs, norm, 0))
    return res


def evaluate(name, s, flag, y, rte, pos, eps, seed, scenario, fs, norm, secs):
    # map back to (device, reading) for episode scoring
    fl = {}; rl = {}; k = 0
    for d, idx in pos:
        for j, i in enumerate(idx): fl[(d, i)] = flag[k + j]; rl[(d, i)] = rte[k + j]
        k += len(idx)
    per = {}
    for ty, d, st_, L in eps:
        hits = [i - st_ for i in range(st_, st_ + L + 5) if fl.get((d, i))]
        rule_hit = any(rl.get((d, i)) for i in range(st_, st_ + L + 5))
        p = per.setdefault(ty, {"n": 0, "det": 0, "delay": [], "unique": 0})
        p["n"] += 1
        if hits: p["det"] += 1; p["delay"].append(hits[0])
        if hits and not rule_hit: p["unique"] += 1
    hours = (~y).sum() * DT / 3600 / ND  # benign device-hours per device ... reported per device-hour below
    fp = int((flag & ~y).sum())
    return {"model": name, "seed": seed, "scenario": scenario, "features": fs, "norm": norm,
            "roc_auc": float(roc_auc_score(y, s)) if name != "rules" else None,
            "pr_auc": float(average_precision_score(y, s)) if name != "rules" else None,
            "tp_readings": int((flag & y).sum()), "fp": fp, "fp_per_dev_h": fp / ((~y).sum() * DT / 3600),
            "precision": float((flag & y).sum() / max(1, flag.sum())), "recall_readings": float((flag & y).sum() / y.sum()),
            "episodes": per, "fit_score_s": round(secs, 1)}


if __name__ == "__main__":
    seeds = range(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
    out = open(sys.argv[2] if len(sys.argv) > 2 else "x2_results.jsonl", "a")
    for seed in seeds:
        for scenario in ("none", "step", "seasonal"):
            for fs in ("point", "window"):
                for norm in ("static", "adaptive"):
                    t0 = time.time()
                    for r in run(seed, scenario, fs, norm): out.write(json.dumps(r, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
                    out.flush(); print(seed, scenario, fs, norm, f"{time.time()-t0:.0f}s", flush=True)
