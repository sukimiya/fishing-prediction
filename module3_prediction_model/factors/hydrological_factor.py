"""Hydrological factors: water level, dissolved oxygen.

Note: Open-Meteo does not provide water data directly.
These factors rely on user input or estimation.
"""

from module3_prediction_model.factors.base import BaseFactor


class WaterLevelFactor(BaseFactor):
    """Score based on water level trend.

    Rising water = good (triggers feeding). Falling = bad.
    """

    name = "water_level"
    category = "hydrological"

    def score(self, water_level_trend: str = "stable", **kwargs) -> float:
        """Score based on water level trend.

        Args:
            water_level_trend: 'rising', 'falling', or 'stable'.

        Returns:
            Score in [0, 1].
        """
        trend = (water_level_trend or "stable").lower()
        if trend == "rising":
            return 0.9
        if trend == "stable":
            return 0.6
        return 0.3  # falling
