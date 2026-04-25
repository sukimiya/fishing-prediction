"""Xiaohongshu (小红书) fishing note scraper using Playwright.

Strategy:
  1. Launch mobile-mode Chromium via Playwright
  2. First run: open login page, wait for user to scan QR code
  3. Save cookies → subsequent runs skip login
  4. Search fishing keywords and extract note content
  5. Parse with NLP to identify species, location, catch results

Usage:
    python -m module1_market_research.scrapers.xiaohongshu --login
    python -m module1_market_research.scrapers.xiaohongshu --search 路亚
    python -m module1_market_research.scrapers.xiaohongshu --search 路亚 --max-notes 50
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


# Fishing-related keywords to search
FISHING_KEYWORDS = [
    "路亚", "路亚钓鱼", "路亚翘嘴", "路亚鲈鱼",
    "钓鱼爆护", "野钓", "路亚打龟", "路亚空军",
    "路亚鳜鱼", "路亚黑鱼", "路亚鳡鱼",
]

# Keywords that indicate a catch result
POSITIVE_CATCH = {"爆护", "上鱼", "钓获", "上了条", "连竿", "米级", "巨物"}
NEGATIVE_CATCH = {"空军", "打龟", "龟了", "白板", "没口"}
LOCATION_PATTERN = re.compile(r"[#＃]([^#\s]{2,10}(?:水库|湖|河|江|塘|浜|钓场|路亚基地|坑))")


class XiaohongshuScraper:
    """Scrape fishing notes from Xiaohongshu."""

    BASE_URL = "https://www.xiaohongshu.com"
    COOKIE_PATH = Path("data/module1/cached_pages/xiaohongshu_cookies.json")

    def __init__(self, headless: bool = False, slow_mo: int = 500):
        self.headless = headless
        self.slow_mo = slow_mo
        self.cookie_dir = Path("data/module1/cached_pages")
        self.cookie_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _make_context(self, playwright):
        """Create a browser context with mobile viewport."""
        browser = playwright.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
        context = browser.new_context(
            viewport={"width": 375, "height": 812},  # iPhone X
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            locale="zh-CN",
        )
        return browser, context

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self):
        """Open browser and wait for user to scan QR code.

        Call this once to save cookies for subsequent runs.
        """
        with sync_playwright() as p:
            browser, context = self._make_context(p)
            page = context.new_page()
            page.goto(self.BASE_URL)

            print("\n" + "=" * 50)
            print("  请在浏览器中扫码登录小红书")
            print("  登录完成后按 Enter 继续...")
            print("=" * 50)

            # Wait for user to press Enter
            input()

            # Save cookies
            cookies = context.cookies()
            self._save_cookies(cookies)
            print(f"  Cookies saved ({len(cookies)} entries)")

            browser.close()

    def _load_cookies(self) -> Optional[list]:
        if self.COOKIE_PATH.exists():
            with open(self.COOKIE_PATH, "r") as f:
                return json.load(f)
        return None

    def _save_cookies(self, cookies: list):
        with open(self.COOKIE_PATH, "w") as f:
            json.dump(cookies, f, indent=2)

    # ------------------------------------------------------------------
    # Search & scrape
    # ------------------------------------------------------------------

    def search_notes(self, keyword: str, max_notes: int = 30) -> list[dict]:
        """Search for a keyword and extract note metadata from search results.

        Returns list of {title, link} dicts.
        """
        with sync_playwright() as p:
            browser, context = self._make_context(p)

            # Load saved cookies
            cookies = self._load_cookies()
            if cookies:
                context.add_cookies(cookies)
            else:
                print("  No saved cookies. Run --login first.")
                browser.close()
                return []

            page = context.new_page()

            # Search
            search_url = f"{self.BASE_URL}/search/result?keyword={keyword}&source=web_search_result_notes"
            print(f"  Searching: {keyword}")
            page.goto(search_url, timeout=30000)
            page.wait_for_timeout(3000)

            # Scroll to load more
            notes = []
            seen_urls = set()

            for scroll in range(5):  # up to 5 scrolls
                # Extract note cards
                cards = page.query_selector_all("a[href*='/explore/']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href and href not in seen_urls:
                        seen_urls.add(href)
                        full_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                        # Try to get title from the card
                        title_el = card.query_selector("span, div")
                        title = title_el.inner_text() if title_el else ""
                        notes.append({
                            "url": full_url,
                            "title": title.strip()[:100],
                            "keyword": keyword,
                        })

                if len(notes) >= max_notes:
                    notes = notes[:max_notes]
                    break

                # Scroll down
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(2000)

            print(f"  Found {len(notes)} notes")
            browser.close()
            return notes

    # ------------------------------------------------------------------
    # Detail extraction
    # ------------------------------------------------------------------

    def extract_note_detail(self, url: str) -> Optional[dict]:
        """Open a single note and extract full content.

        Returns dict with title, text, location, time, likes, images.
        """
        with sync_playwright() as p:
            browser, context = self._make_context(p)

            cookies = self._load_cookies()
            if cookies:
                context.add_cookies(cookies)
            else:
                browser.close()
                return None

            page = context.new_page()

            try:
                page.goto(url, timeout=30000)
                page.wait_for_timeout(3000)
            except PwTimeout:
                print(f"  Timeout: {url[:60]}")
                browser.close()
                return None

            result = {"url": url, "keyword": "", "fetched_at": datetime.now().isoformat()}

            # Title
            try:
                title_el = page.query_selector("#detail-title, .title, h1")
                result["title"] = title_el.inner_text().strip() if title_el else ""
            except Exception:
                result["title"] = ""

            # Body text
            try:
                body_el = page.query_selector(".content, .note-text, article")
                result["text"] = body_el.inner_text().strip() if body_el else ""
            except Exception:
                result["text"] = ""

            # Location
            try:
                loc_el = page.query_selector(".location, [class*='location']")
                result["location_raw"] = loc_el.inner_text().strip() if loc_el else ""
            except Exception:
                result["location_raw"] = ""

            # Likes
            try:
                like_el = page.query_selector("[class*='like'] span, [class*='like']")
                result["likes"] = like_el.inner_text().strip() if like_el else "0"
            except Exception:
                result["likes"] = "0"

            # Time
            try:
                time_el = page.query_selector("time, [class*='date'], [class*='time']")
                result["post_time"] = time_el.get_attribute("datetime") or time_el.inner_text().strip() if time_el else ""
            except Exception:
                result["post_time"] = ""

            browser.close()
            return result

    # ------------------------------------------------------------------
    # NLP parsing
    # ------------------------------------------------------------------

    @staticmethod
    def parse_fishing_info(text: str, location_raw: str = "") -> dict:
        """Parse fishing-related information from note text.

        Returns dict with species, catch_result, location, confidence.
        """
        result = {
            "species": "",
            "catch_result": "",  # positive, negative, unknown
            "location": "",
            "has_fishing_info": False,
        }

        if not text:
            return result

        # Fish species keywords
        species_kw = {
            "翘嘴": "翘嘴", "鲈鱼": "鲈鱼", "鳜鱼": "鳜鱼",
            "黑鱼": "黑鱼", "鳡鱼": "鳡鱼", "红尾": "红尾",
            "马口": "马口", "白条": "白条", "青梢": "青梢",
            "鲶鱼": "鲶鱼", "军鱼": "军鱼",
        }

        for kw, name in species_kw.items():
            if kw in text:
                result["species"] = name
                result["has_fishing_info"] = True
                break

        # Catch result
        if any(kw in text for kw in POSITIVE_CATCH):
            result["catch_result"] = "positive"
            result["has_fishing_info"] = True
        elif any(kw in text for kw in NEGATIVE_CATCH):
            result["catch_result"] = "negative"
            result["has_fishing_info"] = True

        # Location from text
        loc_match = LOCATION_PATTERN.search(text)
        if loc_match:
            result["location"] = loc_match.group(1)
        elif location_raw:
            result["location"] = location_raw

        # Check if this is fishing related at all
        if not result["has_fishing_info"]:
            fishing_keywords_in_text = {"路亚", "钓鱼", "打龟", "空军", "爆护", "竿", "饵"}
            if any(kw in text for kw in fishing_keywords_in_text):
                result["has_fishing_info"] = True

        return result

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def crawl(self, keywords: list[str] = None, max_notes_per_keyword: int = 30) -> pd.DataFrame:
        """Full crawl pipeline: search → detail → parse → DataFrame."""
        keywords = keywords or FISHING_KEYWORDS
        all_notes = []

        for kw in keywords:
            print(f"\n--- Keyword: {kw} ---")
            notes = self.search_notes(kw, max_notes=max_notes_per_keyword)
            for note in notes:
                detail = self.extract_note_detail(note["url"])
                if detail and detail.get("text"):
                    info = self.parse_fishing_info(
                        detail.get("text", ""),
                        detail.get("location_raw", ""),
                    )
                    all_notes.append({
                        "keyword": kw,
                        "title": detail.get("title", ""),
                        "text": detail.get("text", ""),
                        "location": info["location"] or detail.get("location_raw", ""),
                        "species": info["species"],
                        "catch_result": info["catch_result"],
                        "has_fishing_info": info["has_fishing_info"],
                        "likes": detail.get("likes", "0"),
                        "post_time": detail.get("post_time", ""),
                        "url": note["url"],
                        "fetched_at": detail.get("fetched_at", ""),
                    })

        df = pd.DataFrame(all_notes)
        return df


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def cmd_login(args):
    scraper = XiaohongshuScraper(headless=False)
    scraper.login()


def cmd_search(args):
    scraper = XiaohongshuScraper(headless=args.headless, slow_mo=args.slow_mo)
    kw = args.keyword or "路亚"
    df = scraper.crawl(keywords=[kw], max_notes_per_keyword=args.max_notes)

    if df.empty:
        print("No notes found.")
        return

    out_dir = Path("data/module1/raw_reviews")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"xiaohongshu_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved {len(df)} notes to {out_path}")

    # Summary
    fishing_df = df[df["has_fishing_info"]]
    print(f"\nFishing-related notes: {len(fishing_df)} / {len(df)}")
    if not fishing_df.empty:
        print(f"Species found: {fishing_df['species'].value_counts().to_dict()}")
        print(f"Catch results: {fishing_df['catch_result'].value_counts().to_dict()}")


def main():
    parser = argparse.ArgumentParser(description="Xiaohongshu Fishing Note Scraper")
    sub = parser.add_subparsers(dest="command")

    p_login = sub.add_parser("login", help="First-time login (scan QR code)")
    p_login.set_defaults(func=cmd_login)

    p_search = sub.add_parser("search", help="Search and scrape fishing notes")
    p_search.add_argument("--keyword", "-k", default="路亚", help="Search keyword")
    p_search.add_argument("--max-notes", "-n", type=int, default=30, help="Max notes to scrape")
    p_search.add_argument("--headless", action="store_true", help="Run without GUI")
    p_search.add_argument("--slow-mo", type=int, default=500, help="Slow down browser (ms)")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
