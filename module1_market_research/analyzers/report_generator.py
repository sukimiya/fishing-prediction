"""Generates a Markdown market research report with charts from review data."""

from datetime import date
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from module1_market_research.analyzers.sentiment import sentiment_distribution
from module1_market_research.analyzers.topics import (
    extract_keywords_tfidf,
    extract_complaint_topics,
    extract_feature_requests,
)


# Chinese font fallback list
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _save_sentiment_chart(dist_df: pd.DataFrame, output_path: Path):
    """Save a grouped bar chart of sentiment distribution by app."""
    if dist_df.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(dist_df))
    width = 0.25

    ax.bar([i - width for i in x], dist_df["positive_pct"], width, label="正面", color="#4CAF50")
    ax.bar(x, dist_df["negative_pct"], width, label="负面", color="#F44336")
    ax.bar([i + width for i in x], 100 - dist_df["positive_pct"] - dist_df["negative_pct"],
           width, label="中性", color="#FFC107")

    ax.set_xticks(list(x))
    ax.set_xticklabels(dist_df["app_name"], rotation=30, ha="right")
    ax.set_ylabel("百分比 (%)")
    ax.set_title("各 App 评论情感分布")
    ax.legend()
    ax.set_ylim(0, 105)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _save_rating_distribution(df: pd.DataFrame, output_path: Path):
    """Save rating distribution histogram."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ratings = df["rating"].value_counts().sort_index()
    ax.bar(ratings.index, ratings.values, color="#2196F3", width=0.6)
    ax.set_xlabel("评分")
    ax.set_ylabel("评论数")
    ax.set_title("评分分布")
    ax.set_xticks([1, 2, 3, 4, 5])
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def generate_report(
    df: pd.DataFrame,
    output_dir: str = "outputs/module1",
    report_date: str = "",
) -> str:
    """Generate a full market research report as Markdown.

    Args:
        df: DataFrame with unified review schema + sentiment columns.
        output_dir: Directory to save report and charts.
        report_date: Date string for the filename.

    Returns:
        Path to the generated report file as a string.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not report_date:
        report_date = date.today().isoformat()

    # Analyze
    dist = sentiment_distribution(df)

    # Generate charts
    chart_path = out / f"sentiment_{report_date}.png"
    _save_sentiment_chart(dist, chart_path)

    rating_chart_path = out / f"rating_dist_{report_date}.png"
    _save_rating_distribution(df, rating_chart_path)

    # Build report
    lines = []
    _w = lines.append

    _w(f"# 钓鱼 App 市场调研报告 — {report_date}")
    _w("")
    _w(f"**数据来源**: Apple App Store 中国区 | **评论总数**: {len(df)}")
    _w("")

    # Overview
    _w("## 1. 概览")
    _w("")
    for _, row in dist.iterrows():
        _w(f"- **{row['app_name']}**: {row['total']} 条评论, "
           f"平均情感分 {row['avg_score']:.2f}, "
           f"正面 {row['positive_pct']:.0f}% / 负面 {row['negative_pct']:.0f}%")
    _w("")

    # Rating distribution
    _w("## 2. 评分分布")
    _w("")
    _w(f"![评分分布]({rating_chart_path.name})")
    _w("")
    rating_summary = df.groupby("app_name")["rating"].describe().round(1)
    _w(rating_summary.to_markdown())
    _w("")

    # Sentiment chart
    _w("## 3. 情感分析")
    _w("")
    _w(f"![情感分布]({chart_path.name})")
    _w("")

    # Top complaints from negative reviews
    _w("## 4. 用户核心痛点（负面评论高频词）")
    _w("")
    all_texts = df[df["sentiment_label"] == "negative"]["body"].dropna().astype(str).tolist()
    if all_texts:
        complaint_topics = extract_keywords_tfidf(all_texts, top_n=25)
        if complaint_topics:
            _w("| 关键词 | 权重 |")
            _w("|--------|------|")
            for word, weight in complaint_topics:
                _w(f"| {word} | {weight} |")
    else:
        _w("（暂无负面评论数据）")
    _w("")

    # Feature requests
    _w("## 5. 用户功能诉求")
    _w("")
    all_bodies = df["body"].dropna().astype(str).tolist()
    requests = extract_feature_requests(all_bodies)
    if requests:
        for req_text, _ in requests[:20]:
            _w(f"- {req_text}")
    else:
        _w("（未检测到明确功能请求）")
    _w("")

    # Per-app breakdown
    _w("## 6. 各 App 详情")
    _w("")
    for app_name in df["app_name"].unique():
        app_df = df[df["app_name"] == app_name]
        _w(f"### {app_name} ({len(app_df)} 条评论)")
        _w("")
        _w(f"- 平均评分: {app_df['rating'].mean():.1f}")
        _w(f"- 平均情感分: {app_df['ensemble_score'].mean():.3f}")
        _w(f"- 正面率: {(app_df['sentiment_label'] == 'positive').mean() * 100:.0f}%")
        _w(f"- 负面率: {(app_df['sentiment_label'] == 'negative').mean() * 100:.0f}%")

        # Top keywords for this app
        app_texts = app_df["body"].dropna().astype(str).tolist()
        if app_texts:
            kw = extract_keywords_tfidf(app_texts, top_n=15)
            if kw:
                _w("")
                _w("高频关键词:")
                for word, weight in kw:
                    _w(f"  - {word} ({weight})")
        _w("")

    _w("---")
    _w(f"*报告由 Fishing Prediction Project 自动生成于 {report_date}*")

    # Write file
    report_path = out / f"market_report_{report_date}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)
