"""Helper script called by Rust backend to get predictions as JSON."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from module3_prediction_model.inference.predictor import Predictor


def main():
    lat = float(sys.argv[1])
    lon = float(sys.argv[2])
    date_str = sys.argv[3]
    hour = int(sys.argv[4])

    predictor = Predictor()
    result = predictor.predict(lat=lat, lon=lon, target_date=date_str, hour=hour)

    # Flatten factor scores for simpler JSON
    factors = {}
    for name, info in result.get("factors", {}).items():
        if isinstance(info, dict):
            factors[name] = info.get("score", 0.0)
        else:
            factors[name] = info

    output = {
        "score": result.get("score", 0.0),
        "label": result.get("label", ""),
        "confidence": result.get("confidence", 0.0),
        "factors": factors,
    }

    # Use ensure_ascii=True to avoid GBK encoding issues on Windows
    print(json.dumps(output, ensure_ascii=True))


if __name__ == "__main__":
    main()
