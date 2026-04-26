"""Xiaohongshu (小红书) fishing note scraper using Playwright API interception.

Strategy:
  1. Login via desktop browser QR code → save cookies
  2. Search by navigating to homepage, typing keyword, pressing Enter
  3. Intercept the edith.xiaohongshu.com/api/sns/web/v1/search/notes API response
  4. Extract structured data from the JSON response (title, user, likes, etc.)
  5. Parse fishing info from titles using NLP keyword matching

Usage:
    python -m module1_market_research.scrapers.xiaohongshu login
    python -m module1_market_research.scrapers.xiaohongshu search --keyword 路亚
    python -m module1_market_research.scrapers.xiaohongshu search --keyword 路亚 --max-notes 100
"""

import argparse
import json
import re
import sys
import time
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
    """Scrape fishing notes from Xiaohongshu via API interception."""

    BASE_URL = "https://www.xiaohongshu.com"
    COOKIE_PATH = Path("data/module1/cached_pages/xiaohongshu_cookies.json")

    # Desktop context params for search
    VIEWPORT = {"width": 1280, "height": 800}
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, headless: bool = True, slow_mo: int = 200):
        self.headless = headless
        self.slow_mo = slow_mo
        self.cookie_dir = Path("data/module1/cached_pages")
        self.cookie_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _make_context(self, playwright):
        """Create a desktop browser context."""
        browser = playwright.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
        context = browser.new_context(
            viewport=self.VIEWPORT,
            user_agent=self.UA,
            locale="zh-CN",
        )
        return browser, context

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self):
        """Open browser and wait for user to scan QR code."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=500)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=self.UA,
                locale="zh-CN",
            )
            page = context.new_page()
            page.goto("https://www.xiaohongshu.com/login", wait_until="networkidle")

            print()
            print("=" * 50)
            print("  请在浏览器中扫码登录小红书")
            print("  如果看不到二维码，点击「扫码登录」选项卡")
            print("  登录完成后按 Enter 继续...")
            print("=" * 50)

            input()

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
    # Search via API interception
    # ------------------------------------------------------------------

    def _search_on_page(self, page, keyword: str, max_notes: int = 50) -> list[dict]:
        """Perform a single keyword search on an already-loaded page.

        Types keyword in search box, presses Enter, captures API response.
        Returns list of parsed notes.
        """
        results = []
        accumulator = []

        def on_response(response):
            url = response.url
            if "/api/sns/web/v1/search/notes" in url and response.status == 200:
                try:
                    data = response.json()
                    accumulator.append(data)
                except Exception:
                    pass

        page.on("response", on_response)

        # Go to homepage
        print(f"  Searching: {keyword}")
        try:
            page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
        except Exception:
            # Retry once if timeout
            try:
                page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"  Page load failed: {e}")
                page.remove_listener("response", on_response)
                return []

        # Type and submit search
        try:
            page.evaluate('document.getElementById("search-input").focus()')
            page.wait_for_timeout(200)
            page.keyboard.type(keyword, delay=60)
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")
        except Exception as e:
            print(f"  Search failed: {e}")
            page.remove_listener("response", on_response)
            return []

        # Wait for API response
        page.wait_for_timeout(3000)

        # Parse results
        for resp_data in accumulator:
            if resp_data.get("data", {}).get("items"):
                for item in resp_data["data"]["items"]:
                    note = self._parse_search_item(item, keyword)
                    if note:
                        results.append(note)

        # Pagination: scroll to load more
        remaining = max_notes - len(results)
        scroll_attempts = 0
        while remaining > 0 and scroll_attempts < 3:
            page.evaluate("window.scrollBy(0, 2000)")
            page.wait_for_timeout(2000)
            scroll_attempts += 1

            new_count = 0
            for resp_data in accumulator:
                items = resp_data.get("data", {}).get("items", [])
                for item in items:
                    note = self._parse_search_item(item, keyword)
                    if note and note["id"] not in {r["id"] for r in results}:
                        results.append(note)
                        new_count += 1

            if new_count == 0:
                break
            remaining = max_notes - len(results)

        page.remove_listener("response", on_response)
        return results[:max_notes]

    def search_by_keyword(self, keyword: str, max_notes: int = 50) -> list[dict]:
        """Search notes for a single keyword (owns its browser session)."""
        with sync_playwright() as p:
            browser, context = self._make_context(p)
            cookies = self._load_cookies()
            if cookies:
                context.add_cookies(cookies)
            else:
                print("  No saved cookies. Run 'login' first.")
                browser.close()
                return []

            page = context.new_page()
            page.goto(self.BASE_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)

            results = self._search_on_page(page, keyword, max_notes)
            print(f"  Found {len(results)} notes for '{keyword}'")
            browser.close()

        return results

    @staticmethod
    def _parse_search_item(item: dict, keyword: str) -> Optional[dict]:
        """Parse a single search result item from the API response."""
        try:
            note_id = item.get("id", "")
            note_card = item.get("note_card", {})
            if not note_card:
                return None

            title = note_card.get("display_title", "")
            user_info = note_card.get("user", {})
            interact = note_card.get("interact_info", {})

            # Get publish time from corner_tag_info
            publish_time = ""
            tags = note_card.get("corner_tag_info", [])
            for tag in tags:
                if tag.get("type") == "publish_time":
                    publish_time = tag.get("text", "")

            return {
                "id": note_id,
                "keyword": keyword,
                "title": title,
                "nickname": user_info.get("nickname", ""),
                "user_id": user_info.get("user_id", ""),
                "likes": interact.get("liked_count", "0"),
                "collects": interact.get("collected_count", "0"),
                "comments": interact.get("comment_count", "0"),
                "shares": interact.get("shared_count", "0"),
                "note_type": note_card.get("type", ""),
                "publish_time": publish_time,
                "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                "fetched_at": datetime.now().isoformat(),
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # NLP parsing (from title only, since full text is not accessible)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_fishing_info(title: str) -> dict:
        """Parse fishing-related information from note title.

        Returns dict with species, catch_result, location, has_fishing_info.
        """
        result = {
            "species": "",
            "catch_result": "",
            "location": "",
            "has_fishing_info": False,
        }

        if not title:
            return result

        # Fish species keywords
        species_kw = {
            "翘嘴": "翘嘴", "鲈鱼": "鲈鱼", "鳜鱼": "鳜鱼",
            "黑鱼": "黑鱼", "鳡鱼": "鳡鱼", "红尾": "红尾",
            "马口": "马口", "白条": "白条", "青梢": "青梢",
            "鲶鱼": "鲶鱼", "军鱼": "军鱼",
        }

        for kw, name in species_kw.items():
            if kw in title:
                result["species"] = name
                result["has_fishing_info"] = True
                break

        # Catch result
        if any(kw in title for kw in POSITIVE_CATCH):
            result["catch_result"] = "positive"
            result["has_fishing_info"] = True
        elif any(kw in title for kw in NEGATIVE_CATCH):
            result["catch_result"] = "negative"
            result["has_fishing_info"] = True

        # Location from text (match hashtags like #xxx水库)
        loc_match = LOCATION_PATTERN.search(title)
        if loc_match:
            result["location"] = loc_match.group(1)

        # Check if this is fishing related at all
        if not result["has_fishing_info"]:
            fishing_keywords_in_text = {"路亚", "钓鱼", "打龟", "空军", "爆护", "竿", "饵"}
            if any(kw in title for kw in fishing_keywords_in_text):
                result["has_fishing_info"] = True

        return result

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def crawl(self, keywords: list[str] = None, max_notes_per_keyword: int = 30) -> pd.DataFrame:
        """Full crawl pipeline: search API → parse → DataFrame.

        Reuses a single browser session across all keywords.
        """
        keywords = keywords or FISHING_KEYWORDS
        all_notes = []

        with sync_playwright() as p:
            browser, context = self._make_context(p)
            cookies = self._load_cookies()
            if cookies:
                context.add_cookies(cookies)
            else:
                print("  No saved cookies. Run 'login' first.")
                return pd.DataFrame()

            page = context.new_page()
            page.goto(self.BASE_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)

            all_pages = [page]
            for i, kw in enumerate(keywords):
                print(f"\n--- Keyword: {kw} ---")
                if i > 0:
                    p = context.new_page()
                    all_pages.append(p)
                else:
                    p = all_pages[0]
                notes = self._search_on_page(p, kw, max_notes=max_notes_per_keyword)

                for note in notes:
                    info = self.parse_fishing_info(note["title"])
                    all_notes.append({
                        "keyword": kw,
                        "title": note["title"],
                        "location": info["location"],
                        "species": info["species"],
                        "catch_result": info["catch_result"],
                        "has_fishing_info": info["has_fishing_info"],
                        "likes": note["likes"],
                        "collects": note["collects"],
                        "comments": note["comments"],
                        "shares": note["shares"],
                        "note_type": note["note_type"],
                        "publish_time": note["publish_time"],
                        "author": note["nickname"],
                        "url": note["url"],
                        "fetched_at": note["fetched_at"],
                    })

            browser.close()

        df = pd.DataFrame(all_notes)
        return df


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def cmd_login(args):
    scraper = XiaohongshuScraper(headless=False)
    scraper.login()


def _load_keywords(path: str = None) -> list[str]:
    """Load keywords from keyword.txt, falling back to FISHING_KEYWORDS."""
    if path is None:
        path = Path(__file__).parent / "keyword.txt"
    p = Path(path)
    if p.exists():
        return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return FISHING_KEYWORDS


def cmd_search(args):
    scraper = XiaohongshuScraper(
        headless=args.headless,
        slow_mo=args.slow_mo,
    )
    if args.keyword:
        keywords = [args.keyword]
    else:
        keywords = _load_keywords()  # try keyword.txt first, fallback to hardcoded
    df = scraper.crawl(keywords=keywords, max_notes_per_keyword=args.max_notes)

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
    p_search.add_argument("--keyword", "-k", default=None, help="Search keyword (default: all fishing keywords)")
    p_search.add_argument("--max-notes", "-n", type=int, default=30, help="Max notes to scrape")
    p_search.add_argument("--headless", action="store_true", help="Run without GUI")
    p_search.add_argument("--slow-mo", type=int, default=200, help="Slow down browser (ms)")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
