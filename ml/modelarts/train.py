"""
CyberShield anomaly model: training job for Huawei Cloud ModelArts (MindSpore).

Trains a small autoencoder (4 -> 8 -> 2 -> 8 -> 4) on NORMAL sensor readings and
writes anomaly_ae.json, which the backend loads (backend/app/ml_autoencoder.py).

Input : telemetry.csv exported from the dashboard (Reports -> telemetry.csv,
        or GET /api/export/telemetry.csv). Attack readings are left out.
Output: anomaly_ae.json (+ anomaly_ae.ckpt and anomaly_ae.mindir with MindSpore).

ModelArts training job (see docs/HUAWEI_INNOVATION.md):
  boot file  ml/modelarts/train.py, framework MindSpore,
  input  data_url  = OBS folder with telemetry.csv
  output train_url = OBS folder for the model
Locally:
  python train.py --data telemetry.csv --out .                       (MindSpore if installed)
  python train.py --data telemetry.csv --out . --framework numpy     (no MindSpore: same network in NumPy)
"""
import argparse
import csv
import json
import math
import os
import random
from datetime import datetime, timezone

import numpy as np

SIZES = [4, 8, 2, 8, 4]
ACTS = ["tanh", "tanh", "tanh", "linear"]


# ------------------------------------------------------------------ data
def load_rows(path: str) -> dict[str, list[tuple[float, float]]]:
    if os.path.isdir(path):
        path = os.path.join(path, "telemetry.csv")
    by_dev: dict[str, list[tuple[float, float]]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("source") or "").startswith("attack"):
                continue
            try:
                by_dev.setdefault(r["device_id"], []).append((float(r["temperature"]), float(r["humidity"])))
            except (KeyError, ValueError):
                continue
    return by_dev


def make_dataset(by_dev):
    """Same features as the backend: z-scores per device + size of the change since the previous reading."""
    stats, X = {}, []
    for dev, vals in by_dev.items():
        if len(vals) < 20:
            continue
        a = np.array(vals)
        s = {"t_mean": float(a[:, 0].mean()), "t_std": max(float(a[:, 0].std()), 0.5),
             "h_mean": float(a[:, 1].mean()), "h_std": max(float(a[:, 1].std()), 1.0)}
        stats[dev] = s
        prev = None
        for t, h in vals:
            pt, ph = prev if prev else (t, h)
            X.append([(t - s["t_mean"]) / s["t_std"], (h - s["h_mean"]) / s["h_std"],
                      abs(t - pt) / s["t_std"], abs(h - ph) / s["h_std"]])
            prev = (t, h)
    return stats, np.array(X, dtype=np.float32)


# ------------------------------------------------------------- MindSpore
def train_mindspore(X, epochs, lr, out_dir):
    import mindspore as ms
    from mindspore import nn, Tensor

    ms.set_context(mode=ms.GRAPH_MODE)
    cells = []
    for i in range(len(SIZES) - 1):
        cells.append(nn.Dense(SIZES[i], SIZES[i + 1]))
        if ACTS[i] == "tanh":
            cells.append(nn.Tanh())
    net = nn.SequentialCell(cells)
    step = nn.TrainOneStepCell(nn.WithLossCell(net, nn.MSELoss()), nn.Adam(net.trainable_params(), learning_rate=lr))
    step.set_train()
    batch = 256
    for ep in range(epochs):
        idx = np.random.permutation(len(X))
        for i in range(0, len(X), batch):
            xb = Tensor(X[idx[i:i + batch]])
            loss = step(xb, xb)
        if ep % 20 == 0 or ep == epochs - 1:
            print(f"epoch {ep:4d}  loss {float(loss.asnumpy()):.5f}")
    ms.save_checkpoint(net, os.path.join(out_dir, "anomaly_ae.ckpt"))
    try:
        ms.export(net, Tensor(X[:1]), file_name=os.path.join(out_dir, "anomaly_ae"), file_format="MINDIR")
    except Exception as exc:  # export is a bonus; the JSON is what the app uses
        print("MindIR export skipped:", exc)
    params = [p.asnumpy() for p in net.trainable_params()]  # weight (out, in), bias, in layer order
    return [{"W": params[2 * i].tolist(), "b": params[2 * i + 1].tolist(), "act": ACTS[i]} for i in range(len(ACTS))]


# ----------------------------------------------------------------- NumPy
def train_numpy(X, epochs, lr, out_dir, seed=7):
    rng = np.random.default_rng(seed)
    W = [rng.uniform(-1, 1, (SIZES[i + 1], SIZES[i])) / math.sqrt(SIZES[i]) for i in range(len(ACTS))]
    b = [np.zeros(SIZES[i + 1]) for i in range(len(ACTS))]
    mW = [np.zeros_like(w) for w in W]; vW = [np.zeros_like(w) for w in W]
    mb = [np.zeros_like(x) for x in b]; vb = [np.zeros_like(x) for x in b]
    t, batch, b1, b2 = 0, 256, 0.9, 0.999
    for ep in range(epochs):
        idx = rng.permutation(len(X))
        for i in range(0, len(X), batch):
            xb = X[idx[i:i + batch]].astype(np.float64)
            acts = [xb]
            for k in range(len(W)):
                z = acts[-1] @ W[k].T + b[k]
                acts.append(np.tanh(z) if ACTS[k] == "tanh" else z)
            grad = 2 * (acts[-1] - xb) / xb.size
            t += 1
            for k in reversed(range(len(W))):
                if ACTS[k] == "tanh":
                    grad = grad * (1 - acts[k + 1] ** 2)
                gW, gb = grad.T @ acts[k], grad.sum(0)
                grad = grad @ W[k]
                for p, g, m, v in ((W, gW, mW, vW), (b, gb, mb, vb)):
                    m[k] = b1 * m[k] + (1 - b1) * g
                    v[k] = b2 * v[k] + (1 - b2) * g * g
                    p[k] -= lr * (m[k] / (1 - b1 ** t)) / (np.sqrt(v[k] / (1 - b2 ** t)) + 1e-8)
        if ep % 20 == 0 or ep == epochs - 1:
            print(f"epoch {ep:4d}  loss {float(np.mean((acts[-1] - xb) ** 2)):.5f}")
    return [{"W": W[k].tolist(), "b": b[k].tolist(), "act": ACTS[k]} for k in range(len(ACTS))]


def errors(layers, X):
    a = X.astype(np.float64)
    for L in layers:
        a = a @ np.array(L["W"]).T + np.array(L["b"])
        if L["act"] == "tanh":
            a = np.tanh(a)
    return np.mean((a - X) ** 2, axis=1)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", "--data_url", dest="data", required=True, help="telemetry.csv or a folder containing it")
    ap.add_argument("--out", "--train_url", dest="out", default=".", help="output folder")
    ap.add_argument("--framework", choices=["auto", "mindspore", "numpy"], default="auto")
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--lr", type=float, default=0.01)
    ap.add_argument("--trained_where", default="", help="label shown in the app, e.g. ModelArts")
    ap.add_argument("--margin", type=float, default=3.0, help="threshold = margin x the 99.9th percentile error")
    args, _ = ap.parse_known_args()  # ModelArts adds its own arguments

    by_dev = load_rows(args.data)
    stats, X = make_dataset(by_dev)
    if len(X) < 200:
        raise SystemExit(f"need at least 200 normal readings, found {len(X)}")
    random.seed(7); np.random.seed(7)
    idx = np.random.permutation(len(X)); cut = int(len(X) * 0.8)
    train, val = X[idx[:cut]], X[idx[cut:]]
    os.makedirs(args.out, exist_ok=True)

    fw = args.framework
    if fw == "auto":
        try:
            import mindspore  # noqa: F401
            fw = "mindspore"
        except ImportError:
            fw = "numpy"
    print(f"training on {len(train)} readings from {len(stats)} devices with {fw}")
    layers = train_mindspore(train, args.epochs, args.lr, args.out) if fw == "mindspore" else train_numpy(train, args.epochs, args.lr, args.out)

    err_train = errors(layers, train)
    threshold = float(np.percentile(err_train, 99.9) * args.margin)
    err_val = errors(layers, val)
    # Synthetic check: the same validation readings with a sudden temperature jump of 4 standard deviations.
    shifted = val.copy(); shifted[:, 0] += 4.0; shifted[:, 2] += 4.0
    validation = {"val_readings": int(len(val)), "false_alarm_rate": round(float((err_val > threshold).mean()), 4),
                  "detect_rate_4sd_jump": round(float((errors(layers, shifted) > threshold).mean()), 4),
                  "train_error_mean": round(float(err_train.mean()), 5)}
    model = {"name": "cybershield-anomaly-ae", "framework": fw,
             "trained_where": args.trained_where or ("ModelArts" if os.getenv("MA_JOB_DIR") else "local"),
             "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "samples": int(len(train)), "features": ["z_temp", "z_hum", "d_temp", "d_hum"],
             "stats": stats, "layers": layers, "threshold": threshold, "validation": validation}
    path = os.path.join(args.out, "anomaly_ae.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(model, fh)
    print("validation:", validation)
    print("saved", path)


if __name__ == "__main__":
    main()
