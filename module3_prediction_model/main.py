"""Module 3: Fish Activity Prediction Model — CLI entry point.

Usage:
    python -m module3_prediction_model.main predict --lat 30.5 --lon 114.3
    python -m module3_prediction_model.main predict --lat 30.5 --lon 114.3 --date 2026-05-01 --hour 6
    python -m module3_prediction_model.main today --lat 30.5 --lon 114.3
    python -m module3_prediction_model.main day --lat 30.5 --lon 114.3
    python -m module3_prediction_model.main diary --create
    python -m module3_prediction_model.main diary --evaluate data/module3/catch_diary.csv
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from module3_prediction_model.inference.predictor import Predictor
from module3_prediction_model.models.rule_based import RuleBasedPredictor
from module3_prediction_model.data.diary_importer import create_template, load_diary


def _print_result(result: dict, detailed: bool = False):
    """Pretty-print a prediction result."""
    score = result["score"]
    label = result["label"]

    # Color-code with markers
    if score >= 0.7:
        marker = "[+++]"
    elif score >= 0.55:
        marker = "[ ++]"
    elif score >= 0.4:
        marker = "[ + ]"
    else:
        marker = "[ - ]"

    print(f"\n{marker} 鱼口概率: {score:.1%}  ({label})")
    print(f"  置信度: {result['confidence']:.0%}")

    if detailed and "factors" in result:
        print("\n  因子分解:")
        for name, fdata in sorted(result["factors"].items(), key=lambda x: -x[1]["weighted"]):
            bar_len = int(fdata["score"] * 20)
            bar = "#" * bar_len + "." * (20 - bar_len)
            print(f"    {fdata['weight']:.0%} {name:20s} |{bar}| {fdata['score']:.2f}")


def cmd_predict(args):
    predictor = Predictor()
    result = predictor.predict(args.lat, args.lon, args.date, args.hour)
    _print_result(result, detailed=args.verbose)


def cmd_today(args):
    predictor = Predictor()
    now = datetime.now()
    result = predictor.predict(args.lat, args.lon, now.strftime("%Y-%m-%d"), now.hour)
    _print_result(result, detailed=True)


def cmd_day(args):
    predictor = Predictor()
    target_date = args.date or date.today().isoformat()
    print(f"\n=== {target_date} 鱼情预测 (每小時) ===\n")

    hourly = predictor.predict_day(args.lat, args.lon, target_date)
    if not hourly:
        print("No data available.")
        return

    # Print hourly chart
    for h in hourly:
        score = h["score"]
        if score >= 0.7:
            marker = "+++"
            color_s = "+"
        elif score >= 0.55:
            marker = "++"
            color_s = "+"
        elif score >= 0.4:
            marker = "+"
            color_s = "-"
        else:
            marker = "-"
            color_s = " "

        bar = "#" * int(score * 30)
        print(f"  {h['hour']:02d}:00 | {bar} {score:.0%} [{marker}]")


def cmd_diary(args):
    if args.create:
        create_template(args.path)
        return

    if args.evaluate:
        import pandas as pd
        print(f"\nEvaluating catch diary: {args.path}")
        df = load_diary(args.path)
        if df is None or df.empty:
            print("No diary data found.")
            return

        predictor = Predictor()
        results = []
        for _, row in df.iterrows():
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
                dt = row.get("date", date.today().isoformat())
                hour = int(row.get("time", "08:00").split(":")[0]) if pd.notna(row.get("time")) else 8
                pred = predictor.predict(lat, lon, str(dt), hour)
                results.append({
                    "date": dt,
                    "actual_catch": int(row.get("has_catch", 0)),
                    "count": int(row.get("count", 0)),
                    "predicted_score": pred["score"],
                    "confidence": pred["confidence"],
                })
            except Exception as e:
                print(f"  Error processing row: {e}")

        if not results:
            return

        rdf = pd.DataFrame(results)

        from module3_prediction_model.evaluation.metrics import calculate_accuracy, top_decile_capture
        metrics = calculate_accuracy(rdf)
        if "error" not in metrics:
            print(f"\n  预测准确率评估:")
            print(f"    样本数: {metrics['samples']}")
            print(f"    准确率: {metrics['accuracy']:.1%}")
            print(f"    精确率: {metrics['precision']:.1%}")
            print(f"    召回率: {metrics['recall']:.1%}")
            print(f"    F1分数: {metrics['f1']:.2f}")
            print(f"    AUC-ROC: {metrics['auc_roc']:.3f}")

        decile = top_decile_capture(rdf)
        if "error" not in decile:
            print(f"    Top 10% 捕获率: {decile['top_decile_capture']:.1%}")


def cmd_info(args):
    """Show info about the model factors."""
    print("\n  Fish Activity Prediction Model")
    print("  ==============================")
    print("\n  因子列表:")
    predictor = RuleBasedPredictor()
    for f in predictor.factors:
        print(f"    {f.weight:.0%}  {f.name:20s}  [{f.category}]")


def main():
    parser = argparse.ArgumentParser(description="Fish Activity Prediction Model")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show factor breakdown")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    p_predict = sub.add_parser("predict", help="Predict fish activity for a specific time")
    p_predict.add_argument("--lat", type=float, required=True)
    p_predict.add_argument("--lon", type=float, required=True)
    p_predict.add_argument("--date", default="", help="YYYY-MM-DD (default: today)")
    p_predict.add_argument("--hour", type=int, default=8, help="Hour 0-23 (default: 8)")
    p_predict.add_argument("--verbose", "-v", action="store_true")
    p_predict.set_defaults(func=cmd_predict)

    p_today = sub.add_parser("today", help="Predict for right now")
    p_today.add_argument("--lat", type=float, required=True)
    p_today.add_argument("--lon", type=float, required=True)
    p_today.set_defaults(func=cmd_today)

    p_day = sub.add_parser("day", help="Show hourly predictions for a day")
    p_day.add_argument("--lat", type=float, required=True)
    p_day.add_argument("--lon", type=float, required=True)
    p_day.add_argument("--date", default="", help="YYYY-MM-DD (default: today)")
    p_day.set_defaults(func=cmd_day)

    p_diary = sub.add_parser("diary", help="Manage or evaluate catch diary")
    p_diary.add_argument("--create", action="store_true", help="Create diary template")
    p_diary.add_argument("--evaluate", action="store_true", help="Evaluate predictions vs diary")
    p_diary.add_argument("--path", default="data/module3/catch_diary.csv", help="Path to diary CSV")
    p_diary.set_defaults(func=cmd_diary)

    sub.add_parser("info", help="Show model info").set_defaults(func=cmd_info)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
