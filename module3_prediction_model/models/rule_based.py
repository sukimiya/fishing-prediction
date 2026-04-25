"""Rule-based prediction model using weighted factor scores.

This is the zero-training startup model — it works immediately
based on fishing domain knowledge encoded in the factor modules.
"""

from typing import Optional

import pandas as pd

from module3_prediction_model.factors.weather_factor import (
    TemperatureFactor, PressureFactor, WeatherConditionFactor, WindFactor,
)
from module3_prediction_model.factors.temporal_factor import TimeOfDayFactor, SeasonFactor
from module3_prediction_model.factors.astronomical_factor import MoonPhaseFactor
from module3_prediction_model.factors.hydrological_factor import WaterLevelFactor
from module3_prediction_model.data.weather_collector import WeatherCollector
from module3_prediction_model.data.astronomy import get_sun_times, get_moon_phase


class RuleBasedPredictor:
    """Zero-training fish activity predictor using weighted factor scores.

    Factors are scored independently and combined via weighted average.
    No historical data required.
    """

    def __init__(self):
        self.factors = []
        self._register_factors()

    def _register_factors(self):
        """Register all factors with their default weights."""
        self.factors = [
            TemperatureFactor(weight=0.25),
            PressureFactor(weight=0.20),
            TimeOfDayFactor(weight=0.15),
            MoonPhaseFactor(weight=0.10),
            SeasonFactor(weight=0.10),
            WeatherConditionFactor(weight=0.10),
            WindFactor(weight=0.05),
            WaterLevelFactor(weight=0.05),
        ]

    def predict(self, **kwargs) -> dict:
        """Compute fish activity prediction from environmental conditions.

        Args:
            **kwargs: All factor parameters (temperature, pressure, hour, ...)

        Returns:
            dict with score, factor_breakdown, confidence.
        """
        scores = {}
        total_weight = 0
        weighted_sum = 0

        for factor in self.factors:
            try:
                val = factor.score(**kwargs)
            except Exception:
                val = 0.5  # neutral on error
            scores[factor.name] = {
                "score": round(val, 4),
                "weight": factor.weight,
                "weighted": round(val * factor.weight, 4),
            }
            weighted_sum += val * factor.weight
            total_weight += factor.weight

        final_score = round(weighted_sum / total_weight, 4) if total_weight > 0 else 0.5

        # Confidence: based on how many factors had non-default values
        provided = sum(1 for s in scores.values() if s["score"] != 0.5)
        total = len(scores)
        confidence = round(provided / total, 2)

        return {
            "score": final_score,
            "confidence": confidence,
            "factors": scores,
            "label": self._label(final_score),
        }

    def predict_from_coords(
        self,
        lat: float,
        lon: float,
        target_date: str = "",
        hour: int = 8,
        water_level_trend: str = "stable",
    ) -> dict:
        """Fetch weather data and predict for a location/date.

        This is the high-level API: give it coordinates and it does
        the rest automatically.
        """
        from datetime import date, datetime

        # Parse date
        if not target_date:
            target_date = date.today().isoformat()
        dt = datetime.strptime(target_date, "%Y-%m-%d") if isinstance(target_date, str) else target_date
        month = dt.month if hasattr(dt, "month") else date.today().month

        # Get astronomy
        sun_times = get_sun_times(lat, lon, dt.date() if hasattr(dt, "date") else None)
        moon_phase = get_moon_phase(dt.date() if hasattr(dt, "date") else None)

        # Get weather
        collector = WeatherCollector()
        weather_data = collector.get_forecast(lat, lon, forecast_days=7)

        if weather_data:
            hourly = collector.extract_hourly(weather_data, target_date=str(dt.date()) if hasattr(dt, "date") else target_date[:10])
            hour_data = next((h for h in hourly if h["hour"] == hour), hourly[0] if hourly else {})
            weather_code = hour_data.get("weather_code", 0)
            temperature = hour_data.get("temperature", 20)
            pressure = hour_data.get("pressure", 1013)
            wind_speed = hour_data.get("wind_speed", 5)
        else:
            weather_code = 0
            temperature = 20
            pressure = 1013
            wind_speed = 5

        return self.predict(
            temperature=temperature,
            pressure=pressure,
            pressure_trend="stable",
            hour=hour,
            sunrise=sun_times.get("sunrise", 6),
            sunset=sun_times.get("sunset", 18),
            month=month,
            moon_phase=moon_phase,
            weather_code=weather_code,
            wind_speed=wind_speed,
            water_level_trend=water_level_trend,
        )

    def predict_day(self, lat: float, lon: float, target_date: str = "") -> list[dict]:
        """Predict fish activity for each hour of a day.

        Returns list of {hour, score, label} for hours 0-23.
        """
        import copy
        from datetime import date

        if not target_date:
            target_date = date.today().isoformat()

        hourly_predictions = []
        for h in range(24):
            result = self.predict_from_coords(lat, lon, target_date, hour=h)
            hourly_predictions.append({
                "hour": h,
                "score": result["score"],
                "label": result["label"],
            })

        return hourly_predictions

    @staticmethod
    def _label(score: float) -> str:
        if score >= 0.7:
            return "优 (Excellent)"
        if score >= 0.55:
            return "良 (Good)"
        if score >= 0.4:
            return "一般 (Fair)"
        return "差 (Poor)"
