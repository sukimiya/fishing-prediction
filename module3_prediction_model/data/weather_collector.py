"""Open-Meteo weather data collector.

Free API, no API key required.
Docs: https://open-meteo.com/en/docs
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx


OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HISTORICAL = "https://archive-api.open-meteo.com/v1/archive"


class WeatherCollector:
    """Fetch weather data from Open-Meteo API with local caching."""

    def __init__(self, cache_dir: str = "data/module3/raw_weather", cache_days: int = 7):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_days = cache_days

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_forecast(
        self,
        lat: float,
        lon: float,
        forecast_days: int = 7,
    ) -> Optional[dict]:
        """Fetch weather forecast for the given location.

        Returns dict with hourly data or None on failure.
        """
        cache_key = f"forecast_{lat}_{lon}_{forecast_days}d_{date.today().isoformat()}"
        cached = self._load_cache(cache_key)
        if cached:
            return cached

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": [
                "temperature_2m",
                "surface_pressure",
                "weather_code",
                "wind_speed_10m",
                "precipitation_probability",
            ],
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "sunrise",
                "sunset",
            ],
            "forecast_days": forecast_days,
            "timezone": "auto",
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
                resp = client.get(OPEN_METEO_BASE, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            print(f"  [weather] API request failed: {e}")
            return None

        self._save_cache(cache_key, data)
        return data

    def get_historical(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
    ) -> Optional[dict]:
        """Fetch historical weather data for a date range."""
        cache_key = f"historical_{lat}_{lon}_{start_date}_{end_date}"
        cached = self._load_cache(cache_key)
        if cached:
            return cached

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": [
                "temperature_2m",
                "surface_pressure",
                "weather_code",
                "wind_speed_10m",
            ],
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "sunrise",
                "sunset",
            ],
            "timezone": "auto",
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
                resp = client.get(OPEN_METEO_HISTORICAL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            print(f"  [weather] Historical API request failed: {e}")
            return None

        self._save_cache(cache_key, data)
        return data

    # ------------------------------------------------------------------
    # Data extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_hourly(data: dict, target_date: Optional[str] = None) -> list[dict]:
        """Extract hourly weather data into a list of dicts.

        Args:
            data: Raw API response dict.
            target_date: Optional date string (YYYY-MM-DD) to filter.

        Returns:
            List of {hour, temperature, pressure, weather_code, wind_speed}.
        """
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return []

        result = []
        for i, t in enumerate(times):
            if target_date and not t.startswith(target_date):
                continue
            result.append({
                "hour": int(t.split("T")[1].split(":")[0]) if "T" in t else 0,
                "datetime": t,
                "temperature": hourly.get("temperature_2m", [None])[i],
                "pressure": hourly.get("surface_pressure", [None])[i],
                "weather_code": hourly.get("weather_code", [None])[i],
                "wind_speed": hourly.get("wind_speed_10m", [None])[i],
                "precipitation_probability": hourly.get("precipitation_probability", [None])[i],
            })
        return result

    @staticmethod
    def extract_daily(data: dict) -> dict:
        """Extract daily summary data.

        Returns dict with sunrise, sunset, temp_max, temp_min.
        """
        daily = data.get("daily", {})
        if not daily:
            return {}
        return {
            "sunrise": daily.get("sunrise", [""])[0] if daily.get("sunrise") else "",
            "sunset": daily.get("sunset", [""])[0] if daily.get("sunset") else "",
            "temp_max": daily.get("temperature_2m_max", [None])[0],
            "temp_min": daily.get("temperature_2m_min", [None])[0],
        }

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _load_cache(self, key: str) -> Optional[dict]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime > timedelta(days=self.cache_days):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_cache(self, key: str, data: dict):
        path = self._cache_path(key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
