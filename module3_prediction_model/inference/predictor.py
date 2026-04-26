"""High-level prediction orchestrator.

Routes between rule-based and ML models depending on data availability.
ML model is loaded from models/fishing_model.joblib if present.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from module3_prediction_model.models.rule_based import RuleBasedPredictor

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_PATH = MODEL_DIR / "fishing_model.joblib"
METADATA_PATH = MODEL_DIR / "model_metadata.json"


class Predictor:
    """Main prediction entry point. Auto-selects model type."""

    def __init__(self, model_type: str = "auto"):
        self.model_type = model_type
        self._rule_based = RuleBasedPredictor()
        self._ml_model = None
        self._ml_features = None
        self._ml_metadata = None
        self._load_ml_model()

    # ------------------------------------------------------------------
    # ML model loading
    # ------------------------------------------------------------------

    def _load_ml_model(self):
        """Try loading the ML model from disk. No-op if not found."""
        try:
            import joblib
        except ImportError:
            return

        if not MODEL_PATH.exists():
            return

        try:
            self._ml_model = joblib.load(MODEL_PATH)
            logger.info(f"ML model loaded: {MODEL_PATH}")

            # Load metadata for feature info
            if METADATA_PATH.exists():
                with open(METADATA_PATH, "r", encoding="utf-8") as f:
                    self._ml_metadata = json.load(f)
                self._ml_features = self._ml_metadata.get("feature_columns", [])
                logger.info(f"ML model features: {len(self._ml_features or [])}")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}")
            self._ml_model = None

    def _ml_available(self) -> bool:
        """Check if ML model is loaded and usable."""
        return self._ml_model is not None

    # ------------------------------------------------------------------
    # ML prediction
    # ------------------------------------------------------------------

    def _predict_ml(self, lat: float, lon: float, target_date: str = "",
                    hour: int = 8) -> Optional[dict]:
        """Score with ML model using weather data as features.

        Returns None if ML model unavailable or feature extraction fails.
        """
        if not self._ml_available():
            return None

        try:
            # Get weather data (reuse rule-based's data fetching)
            from datetime import date
            dt = datetime.strptime(target_date, "%Y-%m-%d") if target_date else datetime.now()

            from module3_prediction_model.data.weather_collector import WeatherCollector
            from module3_prediction_model.data.astronomy import get_moon_phase

            collector = WeatherCollector()
            weather_data = collector.get_forecast(lat, lon, forecast_days=7)

            if weather_data:
                hourly = collector.extract_hourly(weather_data, target_date=str(dt.date()))
                hour_data = next((h for h in hourly if h["hour"] == hour), hourly[0] if hourly else {})
                temp_avg = hour_data.get("temperature", 20)
                weather_code = hour_data.get("weather_code", 0)
                precip = hour_data.get("precipitation_probability", 0)
            else:
                temp_avg = 20
                weather_code = 0
                precip = 0

            month = dt.month
            moon_phase = get_moon_phase(dt.date() if hasattr(dt, "date") else dt)

            # Build feature vector matching training features
            features = {
                "month": month,
                "likes_log": 0,
                "collects_log": 0,
                "comments_log": 0,
                "shares_log": 0,
                "temp_avg": temp_avg,
                "temp_max": temp_avg + 2,
                "temp_min": temp_avg - 2,
                "weather_code": weather_code,
                "precipitation": precip,
            }

            # If model has species features, use default (empty)
            if self._ml_features:
                for col in self._ml_features:
                    if col.startswith("species_") and col not in features:
                        features[col] = 0

            # Build array in correct column order
            if self._ml_features:
                X = np.array([[features.get(col, 0) for col in self._ml_features]])
            else:
                default_features = [
                    "month", "likes_log", "collects_log", "comments_log",
                    "shares_log", "temp_avg", "temp_max", "temp_min",
                    "weather_code", "precipitation",
                ]
                X = np.array([[features.get(col, 0) for col in default_features]])

            proba = self._ml_model.predict_proba(X)[0]
            # Probability of class 1 (positive catch)
            ml_score = float(proba[1]) if len(proba) > 1 else float(proba[0])

            return {
                "score": ml_score,
                "confidence": min(1.0, float(len(proba)) / 2.0) if len(proba) > 1 else 0.5,
                "model": "ml",
            }

        except Exception as e:
            logger.warning(f"ML prediction failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, lat: float, lon: float, target_date: str = "",
                hour: int = 8, **kwargs) -> dict:
        """Predict fish activity for a specific time and place.

        Uses ML model if available, otherwise falls back to rule-based.
        When ML is available, blends both predictions for robustness.

        Args:
            lat: Latitude.
            lon: Longitude.
            target_date: Date string (YYYY-MM-DD), defaults to today.
            hour: Hour of day (0-23).
            **kwargs: Additional parameters passed through to factors.

        Returns:
            dict with score, factors, confidence, and label.
        """
        # Get rule-based prediction (always available)
        rule_result = self._rule_based.predict_from_coords(
            lat=lat, lon=lon, target_date=target_date, hour=hour, **kwargs
        )

        # Try ML prediction
        ml_result = self._predict_ml(lat, lon, target_date, hour)

        if ml_result and ml_result["score"] is not None:
            # Blend: weight ML higher when confidence is good
            ml_weight = min(0.5, ml_result["confidence"] * 0.6)
            rule_weight = 1.0 - ml_weight

            blended_score = (
                rule_result["score"] * rule_weight +
                ml_result["score"] * ml_weight
            )

            rule_result["score"] = round(blended_score, 4)
            rule_result["confidence"] = round(
                max(rule_result["confidence"], ml_result["confidence"]), 2
            )
            rule_result["ml_score"] = round(ml_result["score"], 4)
            rule_result["ml_weight"] = round(ml_weight, 3)
            rule_result["label"] = self._label(blended_score)

        return rule_result

    def predict_day(self, lat: float, lon: float, target_date: str = "") -> list[dict]:
        """Get hourly predictions for a full day."""
        hourly = []
        for h in range(24):
            result = self.predict(lat, lon, target_date, hour=h)
            hourly.append({
                "hour": h,
                "score": result["score"],
                "label": result["label"],
            })
        return hourly

    def predict_now(self, lat: float, lon: float) -> dict:
        """Predict for the current time."""
        now = datetime.now()
        return self.predict(lat, lon, target_date=now.strftime("%Y-%m-%d"), hour=now.hour)

    def reload_model(self):
        """Reload ML model from disk (called after upload)."""
        self._ml_model = None
        self._ml_features = None
        self._ml_metadata = None
        self._load_ml_model()
        return self._ml_available()

    @staticmethod
    def _label(score: float) -> str:
        if score >= 0.7:
            return "优 (Excellent)"
        if score >= 0.55:
            return "良 (Good)"
        if score >= 0.4:
            return "一般 (Fair)"
        return "差 (Poor)"
