"""Optional ML detector (Phase 12). Skipped when scikit-learn is not installed."""
import random

import pytest

from app.ml_detector import ML_AVAILABLE, MLDetector
from app.models import SecurityAlert
from app.telemetry_service import ingest_telemetry
from tests.conftest import run

pytestmark = pytest.mark.skipif(not ML_AVAILABLE, reason="scikit-learn not installed")


def test_ml_learns_normal_and_flags_outlier(fresh, db, monkeypatch):
    import app.ml_detector as mod
    random.seed(1)
    # 120 calm readings from IOT-003 (slow, too slow to trigger the rate rule)
    for i in range(120):
        run(ingest_telemetry(db, {"device_id": "IOT-003", "temperature": 22 + random.gauss(0, 0.3),
                                  "humidity": 60 + random.gauss(0, 1), "battery": 90, "source": "test"}))
        if i % 9 == 0:
            from app.detection_engine import detector
            detector.forget_device("IOT-003")  # we are not testing the rate rule here
    detector = MLDetector()
    result = detector.train(db)
    assert result["trained"] is True
    detector.enabled = True
    monkeypatch.setattr(mod, "ml_detector", detector)

    # inside the allowed range (-5..45 C) so the rules stay quiet, but very unusual for this device
    from app.models import Device
    device = db.get(Device, "IOT-003")
    run(detector.check(db, device, 38.0, 95.0))
    alerts = db.query(SecurityAlert).filter(SecurityAlert.alert_type == "ml_anomaly").all()
    assert len(alerts) == 1 and alerts[0].detection_method == "ml"


def test_ml_status_endpoint(client):
    s = client.get("/api/ml/status").json()
    assert s["installed"] is True and "trained" in s
