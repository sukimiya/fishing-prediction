"""
Import fishing spots from Xiaohongshu CSV data into FishPal API.

Usage:
    python backend/import_spots.py <csv_path> [--api-url URL] [--geocode]

Requires Amap Web Service API key for geocoding.
Set env AMAP_KEY=49fa3c22173dffdbd01ea4e3fb5122a2 or pass --amap-key.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests


def extract_location_names(title: str) -> list[str]:
    """Extract potential location names from a note title."""
    names = []
    # Pattern: #xxx 或 #xxx湖 #xxx河 etc.
    names += re.findall(r'[#＃]([^#\s]{2,15}(?:湖|河|江|塘|浜|湾|港|水库|基地|钓场|路亚基地))', title)
    # Pattern: "xxx标点" context
    m = re.search(r'(?:标点[，,]\s*)?([一-龥]{2,8}(?:湖|河|江|塘|浜|湾|港|水库|基地|钓场|路亚基地|村))', title)
    if m:
        names.append(m.group(1))
    # Pattern: standalone location before "路亚"/"钓鱼"
    m = re.search(r'([一-龥]{2,6}(?:湖|河|江|塘))', title)
    if m:
        names.append(m.group(1))
    return names


def geocode(name: str, key: str) -> tuple[float, float] | None:
    """Geocode a place name using Amap REST API."""
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {"key": key, "address": f"上海{name}", "city": "上海", "output": "JSON"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("status") == "1" and data.get("geocodes"):
            loc = data["geocodes"][0].get("location", "")
            if loc and "," in loc:
                lng, lat = loc.split(",")
                return float(lat), float(lng)
    except Exception as e:
        print(f"    Geocode error for '{name}': {e}")
    return None


def login_or_register(api_url: str, nickname: str, invite_code: str) -> str | None:
    """Login or register and return a JWT token."""
    # Try login first
    r = requests.post(f"{api_url}/auth/login", json={"nickname": nickname}, timeout=10)
    if r.ok and r.json().get("success"):
        return r.json()["token"]

    # Register
    r = requests.post(f"{api_url}/auth/register", json={
        "nickname": nickname, "invite_code": invite_code
    }, timeout=10)
    if r.ok and r.json().get("success"):
        return r.json()["token"]

    print(f"  Auth failed: {r.json().get('error', 'unknown')}")
    return None


def upload_spot(api_url: str, token: str, spot: dict) -> bool:
    """Upload a single spot to the API."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(f"{api_url}/api/spots", json=spot, headers=headers, timeout=10)
    if r.ok and r.json().get("success"):
        return True
    print(f"    Upload failed: {r.json().get('error', 'unknown')}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Import fishing spots from CSV to FishPal API")
    parser.add_argument("csv", help="Path to CSV file")
    parser.add_argument("--api-url", default="http://localhost:9090", help="FishPal API URL")
    parser.add_argument("--invite-code", default="FISHING_PAL_2026", help="Invite code")
    parser.add_argument("--nickname", default="import_bot", help="Nickname for import user")
    parser.add_argument("--amap-key", default=os.environ.get("AMAP_KEY", "49fa3c22173dffdbd01ea4e3fb5122a2"),
                        help="Amap Web Service API key for geocoding")
    parser.add_argument("--geocode", action="store_true", help="Enable geocoding (requires Amap key)")
    parser.add_argument("--min-likes", type=int, default=0, help="Minimum likes filter")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be imported without uploading")
    args = parser.parse_args()

    # Read CSV
    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    if df.empty:
        print("CSV is empty.")
        return

    # Filter
    if args.min_likes > 0 and "likes" in df.columns:
        df = df[df["likes"].astype(int) >= args.min_likes]

    # Only fishing-related
    if "has_fishing_info" in df.columns:
        df = df[df["has_fishing_info"]]
        print(f"Fishing-related entries: {len(df)}")

    print(f"Total entries to process: {len(df)}")

    if args.dry_run:
        print("\n[DRY RUN] Would import:")
        for _, row in df.iterrows():
            names = extract_location_names(str(row.get("title", "")))
            print(f"  {row.get('title', '')[:50]} | location={row.get('location', '')} | names={names}")
        return

    # Auth
    token = login_or_register(args.api_url, args.nickname, args.invite_code)
    if not token:
        print("Failed to authenticate.")
        sys.exit(1)
    print(f"Authenticated as '{args.nickname}'")

    # Process each row
    success = 0
    failed = 0
    skipped = 0

    for idx, row in df.iterrows():
        title = str(row.get("title", ""))
        location = str(row.get("location", ""))
        species = str(row.get("species", ""))
        catch_result = str(row.get("catch_result", ""))
        source_url = str(row.get("url", ""))
        try:
            likes = int(float(row.get("likes", 0)))
        except (ValueError, TypeError):
            likes = 0

        # Determine spot name
        spot_name = location or extract_location_names(title)[0] if extract_location_names(title) else title[:30]

        # Get coordinates
        lat, lon = None, None
        if args.geocode:
            candidates = [location] if location else extract_location_names(title)
            for name in candidates:
                print(f"  Geocoding '{name}'...", end=" ")
                coords = geocode(name, args.amap_key)
                if coords:
                    lat, lon = coords
                    print(f"OK ({lat}, {lon})")
                    spot_name = name
                    break
                print("not found")

        if lat is None or lon is None:
            skipped += 1
            print(f"  [{idx}] SKIP '{spot_name}' — no coordinates (use --geocode to auto-resolve)")
            continue

        # Upload
        spot = {
            "name": spot_name,
            "lat": lat,
            "lon": lon,
            "description": title[:200],
            "source_url": source_url,
            "likes": likes,
            "species": species,
            "catch_result": catch_result,
        }

        print(f"  [{idx}] Uploading '{spot_name}' ({lat:.4f}, {lon:.4f})...", end=" ")
        if upload_spot(args.api_url, token, spot):
            success += 1
            print("OK")
        else:
            failed += 1

        # Be nice to the API
        time.sleep(0.3)

    print(f"\nDone! Imported: {success}, Failed: {failed}, Skipped (no coords): {skipped}")


if __name__ == "__main__":
    main()
