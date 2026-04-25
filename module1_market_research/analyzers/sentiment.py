"""Chinese sentiment analysis for app reviews.

Uses SnowNLP as the primary model with a keyword-based rule fallback
for fishing-specific vocabulary that general models may misclassify.
"""

import re
from typing import Optional

import pandas as pd

try:
    from snownlp import SnowNLP
except ImportError:
    SnowNLP = None


# Fishing/complaint-specific keyword dictionary
# Positive words indicate user satisfaction / good experience
_POSITIVE_KEYWORDS = {
    "好评", "好用", "实用", "良心", "推荐", "喜欢", "不错", "满意",
    "精准", "准确", "详细", "全面", "强大", "方便", "简洁", "美观",
    "稳定", "流畅", "值得", "惊喜", "收藏", "爱了", "必备", "神器",
    "爆护", "上鱼", "鱼获", "高手", "专业", "细致", "用心",
}

# Negative words indicate user complaints / pain points
_NEGATIVE_KEYWORDS = {
    "垃圾", "差评", "难用", "恶心", "骗人", "坑", "垃圾软件",
    "闪退", "崩溃", "卡顿", "死机", "广告太多", "广告烦",
    "强制", "收费", "骗钱", "没用", "不好", "垃圾", "卸载",
    "假", "错误", "不准", "查不到", "定位不准", "数据不对",
    "失望", "垃圾", "不更新", "不维护", "没卵用", "鸡肋",
    "空军", "白板", "龟了", "打龟",
}


def _keyword_score(text: str) -> Optional[float]:
    """Rule-based sentiment score using fishing-specific keywords.

    Returns a score in [0, 1] or None if no keywords match.
    0 = negative, 1 = positive.
    """
    if not text:
        return None

    pos_count = sum(1 for kw in _POSITIVE_KEYWORDS if kw in text)
    neg_count = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in text)

    total = pos_count + neg_count
    if total == 0:
        return None

    return pos_count / total


def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of a Chinese text string.

    Returns a dict with:
      - snownlp_score: SnowNLP polarity [0, 1] (None if unavailable)
      - keyword_score: keyword-based score [0, 1] (None if no keywords matched)
      - ensemble_score: combined score [0, 1]
      - label: 'positive', 'negative', or 'neutral'
    """
    result = {"snownlp_score": None, "keyword_score": None, "ensemble_score": 0.5, "label": "neutral"}

    # SnowNLP
    if SnowNLP is not None and text.strip():
        try:
            s = SnowNLP(text)
            result["snownlp_score"] = round(float(s.sentiments), 4)
        except Exception:
            pass

    # Keyword fallback
    result["keyword_score"] = _keyword_score(text)

    # Ensemble: use SnowNLP if available, fall back to keyword, then neutral
    kw = result["keyword_score"]
    sn = result["snownlp_score"]

    if sn is not None and kw is not None:
        # Average both when both are available
        result["ensemble_score"] = round((sn + kw) / 2, 4)
    elif sn is not None:
        result["ensemble_score"] = sn
    elif kw is not None:
        result["ensemble_score"] = kw
    else:
        result["ensemble_score"] = 0.5

    # Label
    if result["ensemble_score"] >= 0.65:
        result["label"] = "positive"
    elif result["ensemble_score"] <= 0.35:
        result["label"] = "negative"
    else:
        result["label"] = "neutral"

    return result


def analyze_reviews(df: pd.DataFrame, text_column: str = "body") -> pd.DataFrame:
    """Add sentiment columns to a reviews DataFrame.

    Returns the DataFrame with new columns: snownlp_score, keyword_score,
    ensemble_score, sentiment_label.
    """
    texts = df[text_column].fillna("").astype(str)
    sentiments = texts.apply(analyze_sentiment)

    df["snownlp_score"] = sentiments.apply(lambda x: x["snownlp_score"])
    df["keyword_score"] = sentiments.apply(lambda x: x["keyword_score"])
    df["ensemble_score"] = sentiments.apply(lambda x: x["ensemble_score"])
    df["sentiment_label"] = sentiments.apply(lambda x: x["label"])

    return df


def sentiment_distribution(df: pd.DataFrame, group_column: str = "app_name") -> pd.DataFrame:
    """Compute sentiment distribution per group.

    Returns a DataFrame with counts and percentages of pos/neg/neu per group.
    """
    if df.empty or "sentiment_label" not in df.columns:
        return pd.DataFrame()

    counts = df.groupby(group_column)["sentiment_label"].value_counts().unstack(fill_value=0)

    for col in ["positive", "negative", "neutral"]:
        if col not in counts.columns:
            counts[col] = 0

    counts = counts[["positive", "negative", "neutral"]]
    counts["total"] = counts.sum(axis=1)
    counts["positive_pct"] = (counts["positive"] / counts["total"] * 100).round(1)
    counts["negative_pct"] = (counts["negative"] / counts["total"] * 100).round(1)
    counts["avg_score"] = df.groupby(group_column)["ensemble_score"].mean().round(4)

    return counts.reset_index()
