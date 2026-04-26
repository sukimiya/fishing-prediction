#!/usr/bin/env python3
"""One-click pipeline: crawl → prepare → train → upload → restart.

Usage:
    python scripts/run_fish_pipeline.py
    python scripts/run_fish_pipeline.py --no-crawl       # skip crawling, use existing CSV
    python scripts/run_fish_pipeline.py --geocode         # enable geocoding (Amap API)
    python scripts/run_fish_pipeline.py --no-upload       # train locally only
    python scripts/run_fish_pipeline.py --sync-predictor  # also sync predictor.py changes

Requires:
    - Server SSH access configured (root@43.129.205.140)
    - ML dependencies: pip install scikit-learn joblib
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: str, desc: str = "") -> bool:
    """Run a shell command and return success status."""
    if desc:
        print(f"\n{'='*60}")
        print(f"  {desc}")
        print(f"{'='*60}")

    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        return False
    return True


def find_latest_csv() -> str:
    """Find the most recent Xiaohongshu CSV in data directory."""
    data_dir = PROJECT_ROOT / "data" / "module1" / "raw_reviews"
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        print("Run the crawler first or pass --csv manually.")
        return ""

    csvs = sorted(data_dir.glob("xiaohongshu_*.csv"))
    if not csvs:
        print(f"No xiaohongshu CSVs found in {data_dir}")
        return ""

    latest = csvs[-1]
    print(f"Latest CSV: {latest} (from {len(csvs)} files)")
    return str(latest)


def main():
    parser = argparse.ArgumentParser(description="Fish Prediction Pipeline: crawl → train → deploy")
    parser.add_argument("--csv", default="",
                        help="Path to CSV (default: latest from data/module1/raw_reviews/)")
    parser.add_argument("--keyword-file", default="",
                        help="Path to keyword.txt (default: scrapers/keyword.txt)")
    parser.add_argument("--max-notes", type=int, default=30,
                        help="Max notes per keyword (default: 30)")
    parser.add_argument("--no-crawl", action="store_true",
                        help="Skip crawling, use existing CSV")
    parser.add_argument("--geocode", action="store_true",
                        help="Enable geocoding + weather fetch (requires Amap API)")
    parser.add_argument("--no-upload", action="store_true",
                        help="Train locally only, don't upload to server")
    parser.add_argument("--sync-predictor", action="store_true",
                        help="Also sync predictor.py changes to server")
    parser.add_argument("--crawl-only", action="store_true",
                        help="Only run the crawler, skip training")
    args = parser.parse_args()

    print(f"\n  🐟 Fish Prediction Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Project: {PROJECT_ROOT}")

    # --- Step 1: Crawl ---
    csv_path = args.csv

    if not args.no_crawl:
        keyword_file = args.keyword_file or str(
            PROJECT_ROOT / "module1_market_research" / "scrapers" / "keyword.txt"
        )

        ok = run(
            f'python -m module1_market_research.scrapers.xiaohongshu search '
            f'--max-notes {args.max_notes} --headless',
            "Step 1: Crawling Xiaohongshu",
        )
        if not ok:
            print("Crawling failed. Aborting.")
            sys.exit(1)

        # Find latest CSV
        csv_path = find_latest_csv()
        if not csv_path:
            print("No CSV found after crawling. Aborting.")
            sys.exit(1)

    if args.crawl_only:
        print("\nCrawl complete (--crawl-only). Skipping training and upload.")
        return

    # --- Step 2: Prepare training data ---
    geocode_flag = "--geocode" if args.geocode else ""
    ok = run(
        f'python -m module3_prediction_model.training.prepare_data "{csv_path}" '
        f'--output data/module3/training_data.parquet {geocode_flag}',
        "Step 2: Preparing training data",
    )
    if not ok:
        print("Data preparation failed. Aborting.")
        sys.exit(1)

    # --- Step 3: Train model ---
    ok = run(
        "python -m module3_prediction_model.training.train_model "
        "--data data/module3/training_data.parquet",
        "Step 3: Training ML model",
    )
    if not ok:
        print("Training failed. Aborting.")
        sys.exit(1)

    # --- Step 4: Upload to server ---
    if not args.no_upload:
        sync_flag = "--sync-predictor" if args.sync_predictor else ""
        ok = run(
            f"python scripts/upload_model.py {sync_flag}",
            "Step 4: Uploading model to server",
        )
        if not ok:
            print("Upload had issues. Check the output above.")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Pipeline complete! {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
