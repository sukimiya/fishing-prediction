"""Fetch app metadata from Apple App Store Lookup API and store snapshots."""

from datetime import date
from typing import Optional

import httpx

from module2_competitive_analysis.storage import Storage


APPLE_LOOKUP_URL = "https://itunes.apple.com/lookup?id={app_id}&country={country}"


def fetch_app_metadata(app_id: str, country: str = "cn") -> Optional[dict]:
    """Fetch app metadata from Apple Lookup API.

    Returns a dict with keys matching the snapshot schema, or None on failure.
    """
    if not app_id:
        return None

    url = APPLE_LOOKUP_URL.format(app_id=app_id, country=country)
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            resp = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    results = data.get("results", [])
    if not results:
        return None

    app = results[0]
    return {
        "version": app.get("version", ""),
        "rating": app.get("averageUserRating", 0),
        "rating_count": app.get("userRatingCount", 0),
        "review_count": 0,  # not available via lookup API
        "description": (app.get("description", "") or "")[:500],
        "price_text": app.get("formattedPrice", "Free"),
        "app_size_mb": round(int(app.get("fileSizeBytes", 0) or 0) / (1024 * 1024), 1),
        "update_notes": (app.get("releaseNotes", "") or "")[:500],
        "snapshot_date": date.today().isoformat(),
    }


def track_all_apps(config_path: str = "config/module2_config.yaml") -> list[str]:
    """Track all configured apps and return status messages."""
    import yaml
    from pathlib import Path

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    db_path = config.get("storage", {}).get("db_path", "data/module2/competitor_tracker.db")
    storage = Storage(db_path)
    messages = []

    for app in config.get("tracked_apps", []):
        app_id = app.get("apple_id", "")
        name = app.get("name", app_id)
        store = app.get("store", "apple_app_store_cn")

        # Determine country from store name
        country = "cn" if "cn" in store else "us"

        # Upsert app
        storage.upsert_app(
            app_id=f"{store}:{app_id}",
            name=name,
            store=store,
            apple_id=app_id,
        )

        # Fetch metadata
        meta = fetch_app_metadata(app_id, country=country)
        if meta is None:
            messages.append(f"  x {name}: failed to fetch")
            continue

        # Insert snapshot
        storage.insert_snapshot(
            app_id=f"{store}:{app_id}",
            snapshot=meta,
        )

        count = storage.get_snapshot_count(f"{store}:{app_id}")
        messages.append(
            f"  > {name}: v{meta['version']}, "
            f"rating {meta['rating']:.1f} ({meta['rating_count']} votes), "
            f"snapshot #{count}"
        )

    return messages
