"""Module 1: Market Research — CLI entry point.

Usage:
    python -m module1_market_research.main scrape --app-id 1488431932
    python -m module1_market_research.main analyze --input data/module1/raw_reviews/reviews.csv
    python -m module1_market_research.main report --input data/module1/raw_reviews/reviews_analyzed.csv
    python -m module1_market_research.main all  # full pipeline
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from module1_market_research.scrapers.app_store_cn import AppStoreChinaScraper
from module1_market_research.analyzers.sentiment import analyze_reviews
from module1_market_research.analyzers.report_generator import generate_report


def cmd_scrape(args):
    """Scrape reviews from Apple App Store China."""
    scraper = AppStoreChinaScraper()
    reviews = scraper.fetch_reviews(args.app_id, max_pages=args.pages)

    if not reviews:
        print("No reviews fetched.")
        return

    df = pd.DataFrame(reviews)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"reviews_{args.app_id}_{date.today().isoformat()}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Saved {len(df)} reviews to {out_path}")
    return out_path


def cmd_analyze(args):
    """Add sentiment analysis to scraped reviews."""
    df = pd.read_csv(args.input)
    print(f"Loaded {len(df)} reviews from {args.input}")

    df = analyze_reviews(df)

    out_path = Path(args.input).parent / f"reviews_analyzed_{date.today().isoformat()}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Saved analyzed reviews to {out_path}")

    # Quick summary
    print(f"\nSentiment distribution:")
    print(df["sentiment_label"].value_counts().to_string())
    return out_path


def cmd_report(args):
    """Generate market report from analyzed reviews."""
    df = pd.read_csv(args.input)
    print(f"Loaded {len(df)} analyzed reviews from {args.input}")

    report_path = generate_report(df, output_dir=args.out_dir)
    print(f"Report generated: {report_path}")
    return report_path


def cmd_all(args):
    """Run full pipeline: scrape -> analyze -> report."""
    today = date.today().isoformat()

    # Known target apps
    targets = [
        ("1488431932", "钓鱼天气预报"),
        ("6469984171", "正口-让路亚更简单"),
        ("6443960894", "钓鱼佬"),
        # ("477967747", "Fishbrain"),  # US store, may not work with China RSS
    ]

    out_data = Path("data/module1/raw_reviews")
    out_data.mkdir(parents=True, exist_ok=True)

    all_reviews = []

    for app_id, app_name in targets:
        print(f"\n{'='*60}")
        print(f"Scraping: {app_name} (ID: {app_id})")
        print(f"{'='*60}")

        scraper = AppStoreChinaScraper()
        reviews = scraper.fetch_reviews(app_id, max_pages=args.pages)
        print(f"  Got {len(reviews)} reviews")

        if reviews:
            df = pd.DataFrame(reviews)
            all_reviews.append(df)

            # Save per-app raw data
            per_app_path = out_data / f"reviews_{app_id}_{today}.csv"
            df.to_csv(per_app_path, index=False, encoding="utf-8-sig")

    if not all_reviews:
        print("No reviews collected from any app.")
        return

    combined = pd.concat(all_reviews, ignore_index=True)
    print(f"\nTotal reviews: {len(combined)}")

    # Analyze
    combined = analyze_reviews(combined)

    analyzed_path = out_data / f"all_reviews_analyzed_{today}.csv"
    combined.to_csv(analyzed_path, index=False, encoding="utf-8-sig")
    print(f"Saved analyzed data to {analyzed_path}")

    # Report
    report_path = generate_report(combined, output_dir="outputs/module1", report_date=today)
    print(f"\n{'='*60}")
    print(f"Report generated: {report_path}")
    print(f"{'='*60}")

    # Print quick summary
    print("\nQuick summary:")
    summary = combined.groupby("app_name").agg(
        reviews=("body", "count"),
        avg_rating=("rating", "mean"),
        avg_sentiment=("ensemble_score", "mean"),
    ).round(2)
    print(summary.to_string())


def main():
    parser = argparse.ArgumentParser(description="Fishing App Market Research Tool")
    parser.add_argument("--out-dir", default="outputs/module1", help="Output directory")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # scrape
    p_scrape = sub.add_parser("scrape", help="Scrape reviews from App Store")
    p_scrape.add_argument("--app-id", required=True, help="Apple App Store app ID")
    p_scrape.add_argument("--pages", type=int, default=5, help="Number of pages to scrape")
    p_scrape.set_defaults(func=cmd_scrape)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyze sentiment of reviews")
    p_analyze.add_argument("--input", required=True, help="Path to reviews CSV")
    p_analyze.set_defaults(func=cmd_analyze)

    # report
    p_report = sub.add_parser("report", help="Generate market report")
    p_report.add_argument("--input", required=True, help="Path to analyzed reviews CSV")
    p_report.set_defaults(func=cmd_report)

    # all
    p_all = sub.add_parser("all", help="Run full pipeline")
    p_all.add_argument("--pages", type=int, default=5, help="Pages per app to scrape")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
