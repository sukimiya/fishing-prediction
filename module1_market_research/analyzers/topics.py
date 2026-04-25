"""Topic extraction from Chinese app reviews using jieba + TF-IDF.

Identifies common complaint topics, feature requests, and key phrases
to understand what users are talking about.
"""

import re
from collections import Counter
from typing import Optional

import pandas as pd

try:
    import jieba
    import jieba.analyse
except ImportError:
    jieba = None


# Fishing domain-specific words that jieba may not know
_FISHING_DICT = {
    "路亚", "台钓", "海钓", "黑坑", "野钓", "鱼情", "钓点", "标点",
    "钓场", "鱼口", "打龟", "空军", "爆护", "鱼获", "放流", "正口",
    "探鱼器", "声呐", "水深", "水温", "气压", "溶氧", "潮汐",
    "饵料", "假饵", "拟饵", "路亚竿", "水滴轮", "纺车轮",
    "前导线", "碳线", "PE线", "尼龙线", "鱼探", "探鱼",
    "定位", "导航", "地图", "天气", "预报", "指数",
    "广告", "会员", "收费", "VIP", "订阅", "闪退", "卡顿",
}


def init_jieba():
    """Add fishing domain words to jieba's dictionary."""
    if jieba is None:
        return
    for word in _FISHING_DICT:
        jieba.add_word(word, freq=100)


def extract_keywords_tfidf(texts: list[str], top_n: int = 30) -> list[tuple[str, float]]:
    """Extract top keywords from a list of texts using jieba TF-IDF.

    Returns list of (word, weight) tuples sorted by weight descending.
    """
    if jieba is None or not texts:
        return []

    init_jieba()
    combined = " ".join(texts)

    keywords = jieba.analyse.extract_tags(
        combined, topK=top_n, withWeight=True
    )
    return [(word, round(weight, 4)) for word, weight in keywords]


def extract_complaint_topics(
    df: pd.DataFrame,
    text_column: str = "body",
    sentiment_column: str = "sentiment_label",
    top_n: int = 20,
) -> list[tuple[str, float]]:
    """Extract top keywords from negative reviews specifically.

    Useful for identifying what users complain about most.
    """
    if "negative" not in df[sentiment_column].values:
        return []

    negative_texts = df[df[sentiment_column] == "negative"][text_column].dropna().astype(str).tolist()
    if not negative_texts:
        return []

    return extract_keywords_tfidf(negative_texts, top_n=top_n)


def extract_feature_requests(texts: list[str]) -> list[tuple[str, int]]:
    """Find sentences that look like feature requests.

    Looks for patterns like "要是...就好了", "希望能", "建议增加", "能不能",
    "什么时候能", "没有", "缺少" etc.
    Returns list of (sentence, word_count) sorted by length (longer = more specific).
    """
    patterns = [
        r"要是.{2,30}就好了",
        r"希望.{4,50}",
        r"建议.{4,50}",
        r"能不能.{4,50}",
        r"什么时候.{4,50}",
        r"为什么不.{4,50}",
        r"没有.{4,40}功能",
        r"缺少.{4,40}",
        r"如果.{4,30}就",
        r"强烈要求.{4,50}",
        r"需要.{2,30}功能",
        r"加个.{2,30}功能",
        r"增加.{4,40}",
    ]

    requests = []
    for text in texts:
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                if len(m) >= 6:  # filter out short matches
                    requests.append((m.strip(), len(m)))

    # Deduplicate and sort by length
    seen = set()
    unique = []
    for req, length in requests:
        if req not in seen:
            seen.add(req)
            unique.append((req, length))
    unique.sort(key=lambda x: -x[1])
    return unique


def count_mentions(texts: list[str], keywords: list[str]) -> dict[str, int]:
    """Count how many texts mention each keyword."""
    counts = Counter()
    for text in texts:
        text_lower = text.lower()
        for kw in keywords:
            if kw in text_lower:
                counts[kw] += 1
    return dict(counts.most_common())
