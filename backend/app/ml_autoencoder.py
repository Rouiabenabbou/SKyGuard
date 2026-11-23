"""
v2.2: anomaly model trained on Huawei ModelArts with MindSpore.

ml/modelarts/train.py trains a small autoencoder (4 -> 8 -> 2 -> 8 -> 4) on
normal readings exported from the dashboard (telemetry.csv). It learns to
rebuild normal readings; a reading it cannot rebuild well (high
reconstruction error) is unusual. The training job writes anomaly_ae.json
(weights + per-device normalisation + alert threshold). Copy that file to
backend/models/anomaly_ae.json (or set AE_MODEL_PATH) and restart.

The app only runs the forward pass, in plain Python, so MindSpore is needed
for training only, not on the server. Features are the same as the Phase 12
detector (ml_detector.py): z-scores of temperature and humidity per device
and the size of the change since the previous reading.

Alerts: type "ml_anomaly", medium severity, detection_method "ml-ae".
Advisory only: never triggers quarantine.
"""
import json
import math
import os
import time

from sqlalchemy.orm import Session

from app import config
from app.models import Device

ACT = {"tanh": math.tanh, "relu": lambda x: x if x > 0 else 0.0, "linear": lambda x: x}


def forward(layers: list[dict], x: list[float]) -> list[float]:
    for layer in layers:
        f = ACT[layer.get("act", "linear")]
        x = [f(sum(w * v for w, v in zip(row, x)) + b) for row, b in zip(layer["W"], layer["b"])]
    return x


def features(stats: dict, t: float, h: float, prev: tuple[float, float] | None) -> list[float]:
    pt, ph = prev if prev else (t, h)
    return [(t - stats["t_mean"]) / stats["t_std"], (h - stats["h_mean"]) / stats["h_std"],
            abs(t - pt) / stats["t_std"], abs(h - ph) / stats["h_std"]]


def reconstruction_error(model: dict, x: list[float]) -> float:
    y = forward(model["layers"], x)
    return sum((a - b) ** 2 for a, b in zip(x, y)) / len(x)


class AEDetector:
    def __init__(self) -> None:
        self.model: dict | None = None
        self.error: str | None = None
        self.loaded_at: float | None = None
        self.previous: dict[str, tuple[float, float]] = {}
        self.checked = 0
        self.flagged = 0
        self.last_error: dict[str, float] = {}
        self.load()

    def load(self, path: str | None = None) -> dict:
        path = path or config.AE_MODEL_PATH
        self.model, self.error = None, None
        if not os.path.exists(path):
            self.error = "no model file yet (train it on ModelArts, see docs/HUAWEI_INNOVATION.md)"
            return self.status()
        try:
            with open(path, encoding="utf-8") as fh:
                m = json.load(fh)
            if not m.get("layers") or not m.get("stats") or "threshold" not in m:
                raise ValueError("missing layers / stats / threshold")
            if len(m["layers"][0]["W"][0]) != 4 or len(m["layers"][-1]["W"]) != 4:
                raise ValueError("model must take and return 4 features")
            self.model, self.loaded_at = m, time.time()
        except Exception as exc:  # bad file: keep running without it
            self.error = f"could not load {os.path.basename(path)}: {exc}"
        return self.status()

    def score(self, device_id: str, t: float, h: float) -> float | None:
        if not self.model or device_id not in self.model["stats"]:
            return None
        prev = self.previous.get(device_id)
        self.previous[device_id] = (t, h)
        return reconstruction_error(self.model, features(self.model["stats"][device_id], t, h, prev))

    async def check(self, db: Session, device: Device, t: float, h: float) -> None:
        if not config.AE_ENABLED or not self.model:
            return
        err = self.score(device.device_id, t, h)
        if err is None:
            return
        self.checked += 1
        self.last_error[device.device_id] = round(err, 4)
        if err > self.model["threshold"]:
            self.flagged += 1
            from app.detection_engine import detector
            await detector.raise_alert(
                db, "ml_anomaly", "medium",
                f"Anomaly model ({self.model.get('framework', '?')}): {device.device_id} reading (temperature {t} C, "
                f"humidity {h} %) could not be rebuilt by the autoencoder (error {err:.3f} > threshold "
                f"{self.model['threshold']:.3f}). It does not match the learned normal pattern.",
                device_id=device.device_id, detection_method="ml-ae",
            )

    def reset(self) -> None:
        self.previous.clear()

    def status(self) -> dict:
        m = self.model or {}
        return {"loaded": bool(self.model), "enabled": config.AE_ENABLED, "error": self.error,
                "framework": m.get("framework"), "trained_at": m.get("trained_at"), "trained_where": m.get("trained_where"),
                "samples": m.get("samples"), "devices": sorted(m.get("stats", {})), "threshold": m.get("threshold"),
                "validation": m.get("validation"), "readings_checked": self.checked, "readings_flagged": self.flagged,
                "last_errors": self.last_error}


ae_detector = AEDetector()
