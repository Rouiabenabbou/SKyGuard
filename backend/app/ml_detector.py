"""
Optional machine-learning anomaly detector (Phase 12).

The rule engine (Phase 5) catches what we can describe in advance: too many
messages, values outside a fixed range, unknown devices. This module adds a
second opinion that LEARNS what normal readings look like and flags readings
that don't fit, even when they are inside the allowed range (for example a
sudden 8 °C jump, or a humidity value that is unusual for that device).

Method: scikit-learn LocalOutlierFactor in "novelty" mode, an unsupervised
outlier detector: a reading is unusual when it sits far away from its nearest
neighbours in the normal training data. (We first tried IsolationForest, but
its scores barely grew for extreme values, so far-out readings were not
separated well from borderline normal ones. LOF scores grow with the
distance, which suits these simple numeric features.)
Features per reading, normalised per device (so one model serves all devices):
    z_temp   = (temperature - device mean) / device std
    z_hum    = (humidity    - device mean) / device std
    d_temp   = |change in temperature since the previous reading| / device std
    d_hum    = |change in humidity since the previous reading|    / device std

Training data: readings already stored from devices that were never flagged
(security_status "normal"). With ML_ENABLED=true it trains itself once enough
readings exist, or you can retrain from the dashboard / POST /api/ml/train.

A reading is flagged when its anomaly score is clearly lower (by ML_MARGIN)
than almost all normal training readings, which keeps false alerts rare.

Alerts it raises have detection_method = "ml" and type "ml_anomaly" (medium
severity). They never trigger auto-quarantine: ML is advisory here.

scikit-learn is optional. Without it the app runs normally and /api/ml/status
says "not installed".
"""
import time

from sqlalchemy.orm import Session

from app import config
from app.models import Device, Telemetry

try:  # optional dependency
    import numpy as np
    from sklearn.neighbors import LocalOutlierFactor
    ML_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    ML_AVAILABLE = False


class MLDetector:
    def __init__(self) -> None:
        self.enabled = config.ML_ENABLED and ML_AVAILABLE
        self.model = None
        self.stats: dict[str, dict] = {}  # device_id -> mean/std of temperature and humidity
        self.previous: dict[str, tuple[float, float]] = {}  # last reading per device
        self.trained_at: float | None = None
        self.training_size = 0
        self.checked = 0
        self.flagged = 0
        self.last_score: dict[str, float] = {}
        self._last_auto_try = 0.0
        self.threshold = 0.0

    # ----------------------------------------------------------- features
    def _features(self, device_id: str, t: float, h: float, prev: tuple[float, float] | None) -> list[float]:
        s = self.stats[device_id]
        pt, ph = prev if prev else (t, h)
        return [
            (t - s["t_mean"]) / s["t_std"],
            (h - s["h_mean"]) / s["h_std"],
            abs(t - pt) / s["t_std"],
            abs(h - ph) / s["h_std"],
        ]

    # ----------------------------------------------------------- training
    def train(self, db: Session) -> dict:
        if not ML_AVAILABLE:
            return {"trained": False, "reason": "scikit-learn is not installed (pip install -r requirements-ml.txt)"}
        normal_ids = [d.device_id for d in db.query(Device).filter(Device.security_status == "normal").all()]
        rows = (db.query(Telemetry).filter(Telemetry.device_id.in_(normal_ids), ~Telemetry.source.like("attack%"))
                .order_by(Telemetry.id).all())
        if len(rows) < config.ML_MIN_TRAINING_READINGS:
            return {"trained": False, "reason": f"need {config.ML_MIN_TRAINING_READINGS} normal readings, have {len(rows)}"}

        by_device: dict[str, list[tuple[float, float]]] = {}
        for r in rows:
            by_device.setdefault(r.device_id, []).append((r.temperature, r.humidity))
        stats = {}
        for dev, values in by_device.items():
            arr = np.array(values)
            stats[dev] = {
                "t_mean": float(arr[:, 0].mean()), "t_std": max(float(arr[:, 0].std()), 0.5),
                "h_mean": float(arr[:, 1].mean()), "h_std": max(float(arr[:, 1].std()), 1.0),
            }
        self.stats = stats
        X = []
        for dev, values in by_device.items():
            prev = None
            for t, h in values:
                X.append(self._features(dev, t, h, prev))
                prev = (t, h)
        model = LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=config.ML_CONTAMINATION)
        X = np.array(X)
        model.fit(X)
        # Alert threshold: clearly below the lowest scores seen in normal training data.
        # (Using the model's own cut-off would flag ~1 % of normal readings: too noisy.)
        scores = model.decision_function(X)
        self.threshold = float(np.percentile(scores, 0.5)) - config.ML_MARGIN
        self.model = model
        self.trained_at = time.time()
        self.training_size = len(X)
        return {"trained": True, "samples": len(X), "devices": sorted(stats)}

    # ------------------------------------------------------------ scoring
    async def check(self, db: Session, device: Device, temperature: float, humidity: float) -> None:
        """Called for every stored reading."""
        if not self.enabled:
            return
        if self.model is None:
            # train automatically once there is enough data (at most every 30 s)
            if time.time() - self._last_auto_try > 30:
                self._last_auto_try = time.time()
                self.train(db)
            if self.model is None:
                return
        if device.device_id not in self.stats:
            return  # device had no training data (e.g. added later): skip until retrained
        prev = self.previous.get(device.device_id)
        self.previous[device.device_id] = (temperature, humidity)
        features = np.array([self._features(device.device_id, temperature, humidity, prev)])
        score = float(self.model.decision_function(features)[0])  # < 0 = outlier
        self.last_score[device.device_id] = round(score, 3)
        self.checked += 1
        if score < self.threshold:
            self.flagged += 1
            from app.detection_engine import detector
            await detector.raise_alert(
                db, "ml_anomaly", "medium",
                f"ML detector: unusual reading from {device.device_id} (temperature {temperature} C, "
                f"humidity {humidity} %, anomaly score {score:.2f}). It does not match the learned normal pattern.",
                device_id=device.device_id, detection_method="ml",
            )

    def reset(self) -> None:
        self.previous.clear()

    def status(self) -> dict:
        return {
            "installed": ML_AVAILABLE,
            "enabled": self.enabled,
            "trained": self.model is not None,
            "trained_at": self.trained_at,
            "training_samples": self.training_size,
            "devices": sorted(self.stats),
            "readings_checked": self.checked,
            "readings_flagged": self.flagged,
            "last_scores": self.last_score,
            "min_training_readings": config.ML_MIN_TRAINING_READINGS,
            "contamination": config.ML_CONTAMINATION,
            "alert_threshold": round(self.threshold, 3),
        }


ml_detector = MLDetector()
