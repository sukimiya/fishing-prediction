"""Weather-related factors: temperature, pressure, weather condition, wind."""

import math

from module3_prediction_model.factors.base import BaseFactor
from module3_prediction_model.config import OPTIMAL_TEMP_RANGE, OPTIMAL_PRESSURE_RANGE


class TemperatureFactor(BaseFactor):
    """Score based on water/air temperature proximity to optimal range.

    Fish are ectothermic — their activity is highly temperature-dependent.
    Uses a bell-curve around the optimal range.
    """

    name = "temperature"
    category = "weather"

    def __init__(self, weight: float = 0.25, optimal_range: tuple[float, float] = None):
        super().__init__(weight)
        self.low, self.high = optimal_range or OPTIMAL_TEMP_RANGE
        # How far from optimal before score drops to near-zero
        self.sigma = 8.0

    def score(self, temperature: float = 20, **kwargs) -> float:
        """Gaussian-like score centered on optimal range.

        Args:
            temperature: Water or air temperature in Celsius.

        Returns:
            Score in [0, 1].
        """
        mid = (self.low + self.high) / 2
        # Flat top within optimal range, Gaussian falloff outside
        if self.low <= temperature <= self.high:
            return 1.0
        dist = min(abs(temperature - self.low), abs(temperature - self.high))
        raw = math.exp(-(dist ** 2) / (2 * self.sigma ** 2))
        return max(0.0, min(1.0, raw))


class PressureFactor(BaseFactor):
    """Score based on atmospheric pressure and its trend.

    Stable or rising pressure is good for fishing.
    Rapidly falling pressure is bad.
    """

    name = "pressure"
    category = "weather"

    def __init__(self, weight: float = 0.20, rising_boost: float = 0.15):
        super().__init__(weight)
        self.rising_boost = rising_boost

    def score(self, pressure: float = 1013, pressure_trend: str = "stable", **kwargs) -> float:
        """Score based on pressure level and trend.

        Args:
            pressure: Atmospheric pressure in hPa.
            pressure_trend: 'rising', 'falling', or 'stable'.

        Returns:
            Score in [0, 1].
        """
        lo, hi = OPTIMAL_PRESSURE_RANGE
        # Base score: proximity to optimal range
        if lo <= pressure <= hi:
            base = 1.0
        else:
            mid = (lo + hi) / 2
            dist = abs(pressure - mid)
            base = max(0.2, 1.0 - dist / 40)

        # Trend adjustment
        trend = (pressure_trend or "stable").lower()
        if trend == "rising":
            base = min(1.0, base + self.rising_boost)
        elif trend == "falling":
            base = max(0.0, base - 0.2)

        return round(max(0.0, min(1.0, base)), 4)


class WeatherConditionFactor(BaseFactor):
    """Score based on weather condition.

    Overcast/light rain = good. Heavy rain/clear blazing sun = bad.
    """

    name = "weather_condition"
    category = "weather"

    # Weather codes to score mapping (WMO weather codes)
    _WEATHER_SCORES = {
        0: 0.3,    # Clear sky
        1: 0.5,    # Mainly clear
        2: 0.6,    # Partly cloudy
        3: 0.7,    # Overcast
        45: 0.6,   # Foggy
        48: 0.5,   # Depositing rime fog
        51: 0.8,   # Light drizzle
        53: 0.7,   # Moderate drizzle
        55: 0.5,   # Dense drizzle
        56: 0.7,   # Light freezing drizzle
        57: 0.5,   # Dense freezing drizzle
        61: 0.9,   # Slight rain
        63: 0.8,   # Moderate rain
        65: 0.4,   # Heavy rain
        66: 0.7,   # Light freezing rain
        67: 0.4,   # Heavy freezing rain
        71: 0.6,   # Slight snow
        73: 0.4,   # Moderate snow
        75: 0.2,   # Heavy snow
        77: 0.3,   # Snow grains
        80: 0.8,   # Slight rain showers
        81: 0.7,   # Moderate rain showers
        82: 0.4,   # Violent rain showers
        85: 0.3,   # Slight snow showers
        86: 0.2,   # Heavy snow showers
        95: 0.1,   # Thunderstorm
        96: 0.1,   # Thunderstorm with slight hail
        99: 0.0,   # Thunderstorm with heavy hail
    }

    def score(self, weather_code: int = 0, **kwargs) -> float:
        return self._WEATHER_SCORES.get(weather_code, 0.5)


class WindFactor(BaseFactor):
    """Score based on wind speed.

    Light breeze (5-15 km/h) = good. Calm or strong wind = bad.
    """

    name = "wind"
    category = "weather"

    def score(self, wind_speed: float = 0, **kwargs) -> float:
        """Score based on wind speed in km/h."""
        if wind_speed < 2:
            return 0.4  # too calm
        if wind_speed <= 5:
            return 0.6
        if wind_speed <= 12:
            return 0.9  # ideal (light breeze ripples water)
        if wind_speed <= 20:
            return 0.7
        if wind_speed <= 30:
            return 0.4
        return 0.1  # > 30 km/h too windy
