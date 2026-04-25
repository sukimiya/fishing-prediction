"""Catch diary CSV import and validation.

Expected CSV columns:
  date, time, lat, lon, temperature, pressure, weather_code, wind_speed,
  water_level_trend, species, count, notes
"""

import csv
from pathlib import Path
from typing import Optional

import pandas as pd


REQUIRED_COLUMNS = ["date", "lat", "lon"]
OPTIONAL_COLUMNS = [
    "time", "temperature", "pressure", "weather_code", "wind_speed",
    "water_level_trend", "species", "count", "notes",
]

# Template for creating a new diary CSV
TEMPLATE_CSV = """date,time,lat,lon,temperature,pressure,weather_code,wind_speed,water_level_trend,species,count,notes
2026-04-01,06:30,30.5,114.3,22,1015,3,8,stable,翘嘴,5,早晨窗口期
"""


def create_template(path: str = "data/module3/catch_diary.csv"):
    """Create a diary CSV template."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(TEMPLATE_CSV, encoding="utf-8-sig")
        print(f"Created diary template: {p}")
    else:
        print(f"Diary already exists: {p}")


def load_diary(path: str = "data/module3/catch_diary.csv") -> Optional[pd.DataFrame]:
    """Load and validate catch diary CSV."""
    p = Path(path)
    if not p.exists():
        print(f"Diary not found: {p}")
        return None

    df = pd.read_csv(p, encoding="utf-8-sig")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"Missing required columns: {missing}")
        return None

    # Normalize
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    df["has_catch"] = (df["count"] > 0).astype(int)

    for c in OPTIONAL_COLUMNS:
        if c not in df.columns:
            df[c] = None

    return df
