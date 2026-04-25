"""Module 2: Competitive Analysis — CLI entry point.

Usage:
    python -m module2_competitive_analysis.main track      # fetch latest snapshots
    python -m module2_competitive_analysis.main dashboard   # show overview table
    python -m module2_competitive_analysis.main detail --app-id <id>
    python -m module2_competitive_analysis.main diff
    python -m module2_competitive_analysis.main snapshot    # full status snapshot
"""

import argparse
import sys
from pathlib import Path

from module2_competitive_analysis.storage import Storage
from module2_competitive_analysis.cli_dashboard import (
    show_overview, show_app_detail, show_diff, show_comparison,
)


DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "module2_config.yaml"


def get_storage() -> Storage:
    import yaml
    if DEFAULT_CONFIG.exists():
        with open(DEFAULT_CONFIG, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        db_path = config.get("storage", {}).get("db_path", "data/module2/competitor_tracker.db")
    else:
        db_path = "data/module2/competitor_tracker.db"
    return Storage(db_path)


def cmd_track(args):
    from module2_competitive_analysis.tracker import track_all_apps
    messages = track_all_apps(str(DEFAULT_CONFIG))
    for m in messages:
        print(m)


def cmd_dashboard(args):
    storage = get_storage()
    show_overview(storage)


def cmd_detail(args):
    storage = get_storage()
    show_app_detail(storage, args.app_id)


def cmd_diff(args):
    storage = get_storage()
    show_diff(storage, since_date=args.since)


def cmd_snapshot(args):
    storage = get_storage()
    show_comparison(storage)


def main():
    parser = argparse.ArgumentParser(description="Competitive Analysis Tracker")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("track", help="Fetch latest metadata for all tracked apps").set_defaults(func=cmd_track)
    sub.add_parser("dashboard", help="Show overview table").set_defaults(func=cmd_dashboard)

    p_detail = sub.add_parser("detail", help="Show app detail history")
    p_detail.add_argument("--app-id", required=True)
    p_detail.set_defaults(func=cmd_detail)

    p_diff = sub.add_parser("diff", help="Show recent changes")
    p_diff.add_argument("--since", default="", help="Date threshold (YYYY-MM-DD)")
    p_diff.set_defaults(func=cmd_diff)

    sub.add_parser("snapshot", help="Full status snapshot").set_defaults(func=cmd_snapshot)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
