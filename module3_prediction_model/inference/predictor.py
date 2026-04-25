"""High-level prediction orchestrator.

Routes between rule-based and ML models depending on data availability.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from module3_prediction_model.models.rule_based import RuleBasedPredictor


class Predictor:
    """Main prediction entry point. Auto-selects model type."""

    def __init__(self, model_type: str = "rule_based"):
        self.model_type = model_type
        self._rule_based = RuleBasedPredictor()

    def predict(self, lat: float, lon: float, target_date: str = "", hour: int = 8, **kwargs) -> dict:
        """Predict fish activity for a specific time and place.

        Args:
            lat: Latitude.
            lon: Longitude.
            target_date: Date string (YYYY-MM-DD), defaults to today.
            hour: Hour of day (0-23).
            **kwargs: Additional parameters passed through to factors.

        Returns:
            dict with score, factors, confidence, and label.
        """
        return self._rule_based.predict_from_coords(
            lat=lat, lon=lon, target_date=target_date, hour=hour, **kwargs
        )

    def predict_day(self, lat: float, lon: float, target_date: str = "") -> list[dict]:
        """Get hourly predictions for a full day."""
        return self._rule_based.predict_day(lat, lon, target_date)

    def predict_now(self, lat: float, lon: float) -> dict:
        """Predict for the current time."""
        now = datetime.now()
        return self.predict(lat, lon, target_date=now.strftime("%Y-%m-%d"), hour=now.hour)
