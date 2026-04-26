"""Prepare crawled Xiaohongshu data for ML model training.

Reads crawled CSV, parses dates/locations, fetches weather data,
builds a feature matrix suitable for training.
"""

import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

# ---------------------------------------------------------------------------
# Relative date parsing
# ---------------------------------------------------------------------------

RELATIVE_PATTERNS = [
    (re.compile(r"刚刚"), 0),
    (re.compile(r"(\d+)分钟前"), lambda m: -int(m.group(1)) / 1440),
    (re.compile(r"(\d+)小时前"), lambda m: -int(m.group(1)) / 24),
    (re.compile(r"昨天"), -1),
    (re.compile(r"前天"), -2),
    (re.compile(r"(\d+)天前"), lambda m: -int(m.group(1))),
    (re.compile(r"(\d+)周前"), lambda m: -int(m.group(1)) * 7),
]


def parse_publish_time(pub: str, fetched_at: str) -> Optional[str]:
    """Convert publish_time to YYYY-MM-DD string.

    Handles:
      - ISO format: '2024-08-28' or '2024-08-28T...'
      - Month-day: '04-07' (assumes same year as fetch)
      - Relative: '3天前', '昨天', '刚刚', etc.
    """
    if not pub or pd.isna(pub):
        return None

    pub = str(pub).strip()

    # ISO date
    m = re.match(r"(\d{4}-\d{2}-\d{2})", pub)
    if m:
        return m.group(1)

    # Month-day only — infer year from fetched_at
    m = re.match(r"(\d{2})-(\d{2})", pub)
    if m:
        fetch_year = fetched_at[:4] if fetched_at else str(datetime.now().year)
        return f"{fetch_year}-{m.group(1)}-{m.group(2)}"

    # Relative
    fetch_dt = datetime.fromisoformat(fetched_at) if fetched_at else datetime.now()
    for pattern, offset in RELATIVE_PATTERNS:
        m = pattern.search(pub)
        if m:
            days = offset(m) if callable(offset) else offset
            d = fetch_dt + timedelta(days=days)
            return d.strftime("%Y-%m-%d")

    return None


# ---------------------------------------------------------------------------
# Species & catch extraction from title
# ---------------------------------------------------------------------------

SPECIES_KEYWORDS = {
    "翘嘴": "翘嘴",
    "鲈鱼": "鲈鱼",
    "鳜鱼": "鳜鱼",
    "桂鱼": "鳜鱼",
    "黑鱼": "黑鱼",
    "鳡鱼": "鳡鱼",
    "红尾": "红尾",
    "马口": "马口",
    "白条": "白条",
    "青梢": "青梢",
    "鲶鱼": "鲶鱼",
    "军鱼": "军鱼",
    "鲫鱼": "鲫鱼",
    "鲤鱼": "鲤鱼",
    "草鱼": "草鱼",
    "青鱼": "青鱼",
    "鲢鳙": "鲢鳙",
    "鳊鱼": "鳊鱼",
    "黄辣丁": "黄辣丁",
    "昂刺": "昂刺",
    "罗非": "罗非",
    "米级": "",  # size qualifier, not species
}

POSITIVE_CATCH = {
    "爆护", "上鱼", "钓获", "上了条", "连竿", "米级", "巨物",
    "狂拉", "丰收", "顶水", "探钓", "解锁新鱼种",
    "的快乐", "上鱼了",
}
NEGATIVE_CATCH = {"空军", "打龟", "龟了", "白板", "没口", "空空", "是真的烦"}

LOCATION_PATTERN = re.compile(r"[#＃]([^#\s]{2,15}(?:水库|湖|河|江|塘|浜|湾|港|钓场|基地|坑))")


def extract_species(title: str) -> str:
    if not title or pd.isna(title):
        return ""
    for kw, name in SPECIES_KEYWORDS.items():
        if kw in title:
            return name or kw
    return ""


def extract_catch_result(title: str) -> Optional[str]:
    if not title or pd.isna(title):
        return None
    if any(kw in title for kw in POSITIVE_CATCH):
        return "positive"
    if any(kw in title for kw in NEGATIVE_CATCH):
        return "negative"
    return None


def extract_location(title: str) -> str:
    if not title or pd.isna(title):
        return ""
    m = LOCATION_PATTERN.search(title)
    if m:
        return m.group(1)
    # Fallback: common patterns like "上海xxx"
    m = re.search(r"([一-鿿]{2,4}(?:湖|河|江|塘|水库|钓场))", title)
    if m:
        return m.group(1)
    return ""


def has_fishing_keywords(title: str) -> bool:
    if not title or pd.isna(title):
        return False
    fishing_kw = {"路亚", "钓鱼", "打龟", "空军", "爆护", "竿", "饵", "钓", "鱼", "巨物"}
    return any(kw in title for kw in fishing_kw)


# ---------------------------------------------------------------------------
# Geocoding via Amap
# ---------------------------------------------------------------------------

AMAP_KEY = "49fa3c22173dffdbd01ea4e3fb5122a2"
AMAP_URL = "https://restapi.amap.com/v3/geocode/geo"


def geocode(name: str, city: str = "上海") -> Optional[tuple[float, float]]:
    """Geocode a place name via Amap API. Returns (lat, lon) or None."""
    try:
        resp = httpx.get(AMAP_URL, params={
            "key": AMAP_KEY,
            "address": f"{city}{name}",
            "city": city,
            "output": "JSON",
        }, timeout=10)
        data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            loc = data["geocodes"][0].get("location", "")
            if loc and "," in loc:
                lng, lat = loc.split(",")
                return float(lat), float(lng)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Weather fetching
# ---------------------------------------------------------------------------

OPEN_METEO_HISTORICAL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_weather(lat: float, lon: float, date: str) -> Optional[dict]:
    """Fetch daily weather summary from Open-Meteo historical API."""
    try:
        resp = httpx.get(OPEN_METEO_HISTORICAL, params={
            "latitude": lat,
            "longitude": lon,
            "start_date": date,
            "end_date": date,
            "daily": ["temperature_2m_max", "temperature_2m_min",
                       "sunrise", "sunset", "precipitation_sum",
                       "weather_code"],
            "timezone": "auto",
        }, timeout=15)
        data = resp.json()
        daily = data.get("daily", {})
        if daily.get("time"):
            return {
                "temp_max": daily["temperature_2m_max"][0],
                "temp_min": daily["temperature_2m_min"][0],
                "temp_avg": (daily["temperature_2m_max"][0] + daily["temperature_2m_min"][0]) / 2
                           if daily["temperature_2m_max"][0] and daily["temperature_2m_min"][0] else None,
                "weather_code": daily["weather_code"][0] if daily.get("weather_code") else None,
                "precipitation": daily["precipitation_sum"][0] if daily.get("precipitation_sum") else 0,
            }
    except Exception as e:
        print(f"    Weather fetch error: {e}")
    return None


# ---------------------------------------------------------------------------
# Main preparation function
# ---------------------------------------------------------------------------

def prepare_training_data(
    csv_path: str,
    output_path: str = "data/module3/training_data.parquet",
    geocode_enabled: bool = False,
) -> pd.DataFrame:
    """Clean crawled CSV and build feature matrix.

    Args:
        csv_path: Path to Xiaohongshu CSV.
        output_path: Where to save the prepared dataset.
        geocode_enabled: Whether to geocode locations (requires Amap API).

    Returns:
        DataFrame with features suitable for ML training.
    """
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if df.empty:
        print("Empty CSV, nothing to prepare.")
        return df

    print(f"Loaded {len(df)} rows from {csv_path}")

    # --- Step 1: Parse publish dates ---
    df["parsed_date"] = df.apply(
        lambda r: parse_publish_time(r.get("publish_time"), r.get("fetched_at")),
        axis=1,
    )
    valid_dates = df["parsed_date"].notna().sum()
    print(f"  Parsed dates: {valid_dates}/{len(df)}")

    # --- Step 2: Extract species from title ---
    if "species" in df.columns:
        df["species"] = df["species"].fillna("")
        # Fill missing species from title
        mask = df["species"] == ""
        df.loc[mask, "species"] = df.loc[mask, "title"].apply(extract_species)
    else:
        df["species"] = df["title"].apply(extract_species)
    n_species = (df["species"] != "").sum()
    print(f"  Species identified: {n_species}/{len(df)}")

    # --- Step 3: Extract catch_result ---
    if "catch_result" not in df.columns or df["catch_result"].isna().all():
        df["catch_result"] = df["title"].apply(extract_catch_result)
    else:
        missing = df["catch_result"].isna()
        df.loc[missing, "catch_result"] = df.loc[missing, "title"].apply(extract_catch_result)
    n_catch = df["catch_result"].notna().sum()
    print(f"  Catch results: {n_catch}/{len(df)}  (positive={((df['catch_result']=='positive').sum())}, negative={((df['catch_result']=='negative').sum())})")

    # --- Step 4: Extract location ---
    if "location" in df.columns:
        df["location"] = df["location"].fillna("")
        missing_loc = df["location"] == ""
        df.loc[missing_loc, "location"] = df.loc[missing_loc, "title"].apply(extract_location)
    else:
        df["location"] = df["title"].apply(extract_location)
    n_loc = (df["location"] != "").sum()
    print(f"  Locations extracted: {n_loc}/{len(df)}")

    # --- Step 5: Fishing info flag ---
    if "has_fishing_info" not in df.columns:
        df["has_fishing_info"] = df["title"].apply(has_fishing_keywords)

    # --- Step 6: Features ---
    # Month from parsed date
    df["month"] = pd.to_datetime(df["parsed_date"], errors="coerce").dt.month.fillna(0).astype(int)

    # Engagement features
    for col in ["likes", "collects", "comments", "shares"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0

    # --- Step 7: Geocode + weather (if enabled and data available) ---
    df["lat"] = None
    df["lon"] = None
    n_geocoded = 0
    n_weather = 0

    if geocode_enabled:
        has_loc = df["location"] != ""
        has_date = df["parsed_date"].notna()
        to_geocode = df[has_loc & has_date].copy()

        for idx, row in to_geocode.iterrows():
            loc_name = row["location"]
            print(f"  Geocoding '{loc_name}'...", end=" ")
            coords = geocode(loc_name)
            if coords:
                df.at[idx, "lat"] = coords[0]
                df.at[idx, "lon"] = coords[1]
                n_geocoded += 1
                print(f"({coords[0]:.4f}, {coords[1]:.4f})")

                # Fetch weather
                weather = fetch_weather(coords[0], coords[1], row["parsed_date"])
                if weather:
                    df.at[idx, "temp_avg"] = weather["temp_avg"]
                    df.at[idx, "temp_max"] = weather["temp_max"]
                    df.at[idx, "temp_min"] = weather["temp_min"]
                    df.at[idx, "weather_code"] = weather["weather_code"]
                    df.at[idx, "precipitation"] = weather["precipitation"]
                    n_weather += 1
                    print(f"    Weather: {weather['temp_avg']:.1f}°C, code={weather['weather_code']}")
            else:
                print("not found")

        print(f"  Geocoded: {n_geocoded}, Weather fetched: {n_weather}")

    # --- Step 8: Build target ---
    df["target"] = None
    df.loc[df["catch_result"] == "positive", "target"] = 1
    df.loc[df["catch_result"] == "negative", "target"] = 0
    n_targets = df["target"].notna().sum()
    print(f"  Training targets (positive=1, negative=0): {n_targets}")

    # --- Summary ---
    print(f"\n{'='*50}")
    print(f"Preparation complete:")
    print(f"  Total entries: {len(df)}")
    print(f"  With dates: {valid_dates}")
    print(f"  With species: {n_species}")
    print(f"  With catch results: {n_catch}")
    print(f"  With locations: {n_loc}")
    print(f"  Training targets: {n_targets}")

    # Save
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"  Saved to {out_path}")

    return df


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Prepare training data from crawled CSV")
    parser.add_argument("csv", help="Path to Xiaohongshu CSV")
    parser.add_argument("--output", "-o", default="data/module3/training_data.parquet",
                        help="Output path")
    parser.add_argument("--geocode", action="store_true",
                        help="Enable geocoding + weather fetch (requires Amap API)")
    args = parser.parse_args()

    prepare_training_data(
        csv_path=args.csv,
        output_path=args.output,
        geocode_enabled=args.geocode,
    )


if __name__ == "__main__":
    main()
