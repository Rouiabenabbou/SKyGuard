"""
Optional ML detector endpoints (Phase 12).

GET  /api/ml/status     installed? enabled? trained? how many readings checked / flagged
POST /api/ml/train      (re)train on the readings stored so far
POST /api/ml/settings   {"enabled": true | false}
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml_detector import ML_AVAILABLE, ml_detector

router = APIRouter(prefix="/api/ml", tags=["ml"])


class MLSettings(BaseModel):
    enabled: bool


@router.get("/status")
def status():
    return ml_detector.status()


@router.post("/train")
def train(db: Session = Depends(get_db)):
    result = ml_detector.train(db)
    return {**result, "status": ml_detector.status()}


@router.post("/settings")
def settings(body: MLSettings):
    if body.enabled and not ML_AVAILABLE:
        raise HTTPException(status_code=400, detail="scikit-learn is not installed: pip install -r requirements-ml.txt")
    ml_detector.enabled = body.enabled
    return ml_detector.status()


# v2.2: autoencoder trained on ModelArts / MindSpore (ml_autoencoder.py)
@router.get("/autoencoder")
def ae_status():
    from app.ml_autoencoder import ae_detector
    return ae_detector.status()


@router.post("/autoencoder/reload")
def ae_reload():
    from app.ml_autoencoder import ae_detector
    return ae_detector.load()
