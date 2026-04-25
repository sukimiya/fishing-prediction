"""Module 3 configuration: factor registry, default weights, thresholds."""

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "module3_config.yaml"


# Factor weights (from fishing literature, tunable)
DEFAULT_WEIGHTS = {
    "temperature": 0.25,
    "pressure": 0.20,
    "time_of_day": 0.15,
    "moon_phase": 0.10,
    "season": 0.10,
    "weather_condition": 0.10,
    "wind": 0.05,
    "water_level": 0.05,
}

# Optimal temperature range for common Chinese freshwater fish (Celsius)
# 翘嘴, 鲈鱼, 鳜鱼, 黑鱼, 鲫鱼
OPTIMAL_TEMP_RANGE = (18, 26)

# Optimal pressure range (hPa)
OPTIMAL_PRESSURE_RANGE = (1010, 1025)

# Good fishing hours (local time)
PRIME_HOURS = [(5, 9), (16, 19)]

# Solunar major periods (approximate)
MAJOR_PERIOD_OFFSETS = [(-1, 1), (12, 14)]  # moonrise/set ± 1h, mirrored ± 1h


def load_config(path: str = "") -> dict[str, Any]:
    """Load config from YAML file, merging with defaults."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return {"factors": {}, "model": {"type": "rule_based"}}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config or {}
