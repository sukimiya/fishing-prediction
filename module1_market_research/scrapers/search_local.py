"""Local fishing search: 青浦/金山/奉贤 — quick one-shot script."""

import sys
from datetime import datetime
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from module1_market_research.scrapers.xiaohongshu import XiaohongshuScraper

LOCAL_KEYWORDS = [
    # 青浦区
    "青浦 路亚",
    "青浦 钓鱼",
    "淀山湖 路亚",
    "淀山湖 钓鱼",
    # 金山区
    "金山 路亚",
    "金山 钓鱼",
    # 奉贤区
    "奉贤 路亚",
    "奉贤 钓鱼",
    # 上海全域
    "上海 野钓",
    "上海 路亚",
]

scraper = XiaohongshuScraper(headless=True, slow_mo=300)
print("Starting local fishing search...")
df = scraper.crawl(keywords=LOCAL_KEYWORDS, max_notes_per_keyword=40)

if df.empty:
    print("No notes found. Cookies may have expired — run login first.")
    sys.exit(1)

out_dir = Path("data/module1/raw_reviews")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"local_shanghai_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
df.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"\nSaved {len(df)} notes to {out_path}")

# Summary
fishing_df = df[df["has_fishing_info"]]
print(f"\nFishing-related: {len(fishing_df)} / {len(df)}")

# Per-area breakdown
for kw in LOCAL_KEYWORDS:
    kw_df = df[df["keyword"] == kw]
    if not kw_df.empty:
        fish = kw_df[kw_df["has_fishing_info"]]
        print(f"\n  [{kw}] total={len(kw_df)} fishing={len(fish)} species={fish['species'].value_counts().to_dict() if not fish.empty else {}}")

if not fishing_df.empty:
    print(f"\nSpecies distribution:\n{fishing_df['species'].value_counts().to_string()}")
    print(f"\nCatch results:\n{fishing_df['catch_result'].value_counts().to_string()}")
