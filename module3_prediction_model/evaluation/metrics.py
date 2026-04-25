"""Evaluation metrics for fish activity predictions."""

from typing import Optional

import numpy as np
import pandas as pd


def calculate_accuracy(df: pd.DataFrame, score_col: str = "predicted_score",
                       actual_col: str = "has_catch", threshold: float = 0.5) -> dict:
    """Calculate prediction accuracy metrics.

    Args:
        df: DataFrame with predicted scores and actual catch results.
        score_col: Column name for predicted scores [0, 1].
        actual_col: Column name for actual catch (0 or 1).
        threshold: Score threshold for "positive" prediction.

    Returns:
        dict with accuracy, precision, recall, f1, and AUC-ROC.
    """
    if df.empty or len(df) < 2:
        return {"error": "Not enough data"}

    y_true = df[actual_col].values
    y_pred_binary = (df[score_col].values >= threshold).astype(int)

    tp = np.sum((y_true == 1) & (y_pred_binary == 1))
    tn = np.sum((y_true == 0) & (y_pred_binary == 0))
    fp = np.sum((y_true == 0) & (y_pred_binary == 1))
    fn = np.sum((y_true == 1) & (y_pred_binary == 0))

    accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # AUC-ROC (simplified)
    try:
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y_true, df[score_col].values)
    except Exception:
        auc = 0.0

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "auc_roc": round(auc, 4),
        "samples": len(y_true),
        "threshold": threshold,
    }


def top_decile_capture(df: pd.DataFrame, score_col: str = "predicted_score",
                       actual_col: str = "has_catch") -> dict:
    """Check whether the top 10% highest-score days contain
    a disproportionate share of actual catches.
    """
    if df.empty or len(df) < 10:
        return {"error": "Not enough data (need >= 10 samples)"}

    sorted_df = df.sort_values(score_col, ascending=False).reset_index(drop=True)
    n_top = max(1, len(sorted_df) // 10)
    top = sorted_df.head(n_top)
    total_catches = sorted_df[actual_col].sum()
    top_catches = top[actual_col].sum()

    return {
        "top_decile_capture": round(top_catches / total_catches, 4) if total_catches > 0 else 0,
        "top_n": n_top,
        "top_catches": int(top_catches),
        "total_catches": int(total_catches),
    }
