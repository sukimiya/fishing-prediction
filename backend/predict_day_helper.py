"""Helper script for day/hourly predictions as JSON."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from module3_prediction_model.inference.predictor import Predictor


def main():
    lat = float(sys.argv[1])
    lon = float(sys.argv[2])

    predictor = Predictor()
    results = predictor.predict_day(lat=lat, lon=lon)

    # Simplify: flatten each hour's result
    hourly = []
    for hr in results:
        hourly.append({
            "hour": hr.get("hour", 0),
            "score": hr.get("score", 0.0),
            "label": hr.get("label", ""),
        })

    print(json.dumps(hourly, ensure_ascii=True))


if __name__ == "__main__":
    main()
