"""Train fish activity prediction model from prepared training data.

Trains a GradientBoostingClassifier on weather + context features,
exports the model + metadata. Falls back gracefully if data is insufficient.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import cross_val_score, train_test_split


# Minimum samples needed to train
MIN_TRAIN_SAMPLES = 10

# Feature columns used for training
FEATURE_COLUMNS = [
    "month",
    "likes_log",
    "collects_log",
    "comments_log",
    "shares_log",
]

# Weather features (used if available after geocoding)
WEATHER_FEATURES = [
    "temp_avg",
    "temp_max",
    "temp_min",
    "weather_code",
    "precipitation",
]

# Model storage
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def _log_transform(series: pd.Series) -> pd.Series:
    return np.log1p(series.fillna(0).astype(float))


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build feature matrix from prepared DataFrame."""
    features = pd.DataFrame(index=df.index)

    # Month (from parsed date)
    features["month"] = df["month"].fillna(0).astype(int)

    # Log-transformed engagement signals
    for col in ["likes", "collects", "comments", "shares"]:
        if col in df.columns:
            features[f"{col}_log"] = _log_transform(df[col])
        else:
            features[f"{col}_log"] = 0.0

    # Species one-hot encoding
    if "species" in df.columns:
        species_dummies = pd.get_dummies(df["species"], prefix="species")
        features = pd.concat([features, species_dummies], axis=1)

    # Weather features (may be all NaN if geocoding wasn't done)
    for wf in WEATHER_FEATURES:
        if wf in df.columns:
            features[wf] = df[wf].fillna(df[wf].median() if df[wf].notna().any() else 20.0)
        else:
            features[wf] = 0.0

    return features


def _compute_empirical_stats(df: pd.DataFrame) -> dict:
    """Compute empirical fishing activity statistics from crawled data.

    These serve as interpretable insights and fallback when ML data is sparse.
    """
    stats = {
        "total_entries": len(df),
        "fishing_related": int(df["has_fishing_info"].sum()) if "has_fishing_info" in df.columns else 0,
        "with_species": int((df["species"] != "").sum()) if "species" in df.columns else 0,
        "catch_rate": None,
        "by_month": {},
        "by_species": {},
        "generated_at": datetime.now().isoformat(),
    }

    # Catch rate
    targets = df["target"].dropna()
    if len(targets) > 0:
        stats["catch_rate"] = {
            "positive": int((targets == 1).sum()),
            "negative": int((targets == 0).sum()),
            "rate": float(round(targets.mean(), 4)),
        }

    # By month
    if "month" in df.columns:
        for m in sorted(df["month"].unique()):
            if m == 0:
                continue
            subset = df[df["month"] == m]
            n_fish = subset["has_fishing_info"].sum() if "has_fishing_info" in df.columns else 0
            stats["by_month"][int(m)] = {
                "total": int(len(subset)),
                "fishing_related": int(n_fish),
            }

    # By species
    if "species" in df.columns:
        species_data = df[df["species"] != ""]
        for sp in species_data["species"].unique():
            subset = species_data[species_data["species"] == sp]
            catch_rate = None
            targets = subset["target"].dropna()
            if len(targets) > 0:
                catch_rate = float(round(targets.mean(), 3))
            stats["by_species"][sp] = {
                "count": int(len(subset)),
                "catch_rate": catch_rate,
            }

    return stats


def train(
    data_path: str = "data/module3/training_data.parquet",
    model_output: str = "",
    metadata_output: str = "",
) -> Optional[str]:
    """Main training function.

    Args:
        data_path: Path to prepared parquet file.
        model_output: Path for model.joblib output.
        metadata_output: Path for metadata.json output.

    Returns:
        Path to exported model file, or None if training skipped.
    """
    # Load data
    df = pd.read_parquet(data_path)
    if df.empty:
        print("No training data found.")
        return None

    print(f"Loaded {len(df)} samples from {data_path}")

    # Compute empirical stats regardless
    stats = _compute_empirical_stats(df)

    # Prepare features and target
    features = _build_features(df)
    targets = df["target"].dropna()

    n_targets = len(targets)
    print(f"Training targets (labeled positive/negative): {n_targets}")

    if n_targets >= MIN_TRAIN_SAMPLES:
        # Filter to rows with targets
        train_idx = targets.index
        X = features.loc[train_idx]
        y = targets.values.astype(int)

        # Drop constant columns
        X = X.loc[:, X.std() > 0]

        print(f"Feature matrix: {X.shape}")
        print(f"Target distribution: positive={y.sum()}, negative={len(y)-y.sum()}")

        # Check class balance
        min_class = np.bincount(y.astype(int)).min() if len(np.unique(y)) > 1 else 0

        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42,
        )

        if min_class >= 3:
            # Enough data for train/test split
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            model.fit(X_train, y_train)
            train_score = model.score(X_train, y_train)
            test_score = model.score(X_test, y_test)
            print(f"Train accuracy: {train_score:.3f}")
            print(f"Test accuracy:  {test_score:.3f}")
            stats["train_accuracy"] = float(round(train_score, 4))
            stats["test_accuracy"] = float(round(test_score, 4))

            if n_targets >= 20:
                try:
                    cv_scores = cross_val_score(model, X, y, cv=min(5, min_class))
                    print(f"CV accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")
                    stats["cv_accuracy"] = float(round(cv_scores.mean(), 4))
                    stats["cv_std"] = float(round(cv_scores.std(), 4))
                except Exception:
                    pass
        else:
            # Small/imbalanced data: train on all samples, no validation
            print(f"Class balance too low (minority={min_class}). Training on all data.")
            model.fit(X, y)
            train_score = model.score(X, y)
            stats["train_accuracy"] = float(round(train_score, 4))

        # Feature importance
        importance = sorted(
            zip(X.columns, model.feature_importances_),
            key=lambda x: -x[1],
        )
        print("\nTop features:")
        for name, imp in importance[:10]:
            print(f"  {name:30s} {imp:.4f}")

        stats["feature_importance"] = {name: float(round(imp, 4)) for name, imp in importance[:20]}
        stats["model_type"] = "GradientBoosting"
        stats["n_features"] = X.shape[1]
        stats["n_train_samples"] = int(n_targets)

        # Export model
        model_dir = Path(model_output) if model_output else MODEL_DIR
        model_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "fishing_model.joblib"
        joblib.dump(model, model_path)
        print(f"\nModel saved: {model_path}")

        # Also save the feature columns for inference
        stats["feature_columns"] = list(X.columns)

        result_path = model_path
    else:
        print(f"\nNot enough labeled samples ({n_targets} < {MIN_TRAIN_SAMPLES}).")
        print("Skipping ML training. Using empirical statistics only.")

        # Save dummy model path
        model_path = Path(model_output) if model_output else MODEL_DIR
        model_dir = model_path if model_path.suffix else model_path
        model_dir.mkdir(parents=True, exist_ok=True)
        model_file = (model_dir if model_path.suffix else model_dir) / "fishing_model.joblib"

        # Remove old model if it exists — fall back to rule-based
        if model_file.exists():
            model_file.unlink()
            print("Removed old model (not enough new data).")

        result_path = None

    # Save metadata
    meta_path = Path(metadata_output) if metadata_output else MODEL_DIR / "model_metadata.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"Metadata saved: {meta_path}")

    return str(result_path) if result_path else None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Train fish prediction model")
    parser.add_argument("--data", "-d", default="data/module3/training_data.parquet",
                        help="Prepared training data (.parquet)")
    parser.add_argument("--output", "-o", default="",
                        help="Output directory for model.joblib")
    parser.add_argument("--metadata", "-m", default="",
                        help="Output path for metadata.json")
    args = parser.parse_args()

    train(
        data_path=args.data,
        model_output=args.output,
        metadata_output=args.metadata,
    )


if __name__ == "__main__":
    main()
