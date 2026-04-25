"""Apple App Store China review scraper via public RSS feed.

Uses the official but undocumented Apple RSS feed:
  https://itunes.apple.com/rss/customerreviews/page=<n>/id=<app_id>/sortby=mostrecent/json

Apple returns reviews in two formats:
  A) entries = list of review dicts (most apps)
  B) entries = list of field-names, feed-level dicts hold values (1-review apps)
"""

from datetime import datetime
from typing import Optional

import httpx

from module1_market_research.scrapers.base import BaseScraper


class AppStoreChinaScraper(BaseScraper):
    """Scrapes reviews from Apple App Store China."""

    BASE_URL = "https://itunes.apple.com/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
    # Keys that indicate a flat-format entry (Format B)
    _FIELD_NAMES = {
        "author", "updated", "im:rating", "im:version", "id",
        "title", "content", "link", "im:voteSum", "im:contentType", "im:voteCount",
    }

    def __init__(self, country: str = "cn", **kwargs):
        super().__init__(**kwargs)
        self.country = country

    @property
    def store_name(self) -> str:
        return f"apple_app_store_{self.country}"

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_page(self, app_id: str, page: int) -> list[dict]:
        """Fetch one page of raw reviews via Apple RSS."""
        if not app_id:
            return []

        url = self.BASE_URL.format(page=page, app_id=app_id)
        with self.make_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()

        feed = data.get("feed", {})
        if not feed:
            return []

        entries = feed.get("entry")
        if not entries:
            return []

        # entry is a bare string → no more reviews (page beyond available)
        if isinstance(entries, str):
            return []

        # entry is a dict with a single review (not wrapped in a list)
        if isinstance(entries, dict):
            entries = [entries]

        # Detect flat format: entries[0] is a string → Format B
        if isinstance(entries, list) and entries and isinstance(entries[0], str):
            raw = self._parse_flat_format(feed, entries)
            return raw if raw else []

        # Format A: entries are dicts
        raw = self._parse_dict_format(entries)
        return raw

    # ------------------------------------------------------------------
    # Format parsers
    # ------------------------------------------------------------------

    def _parse_dict_format(self, entries: list[dict]) -> list[dict]:
        """Format A: each entry is a review dict."""
        raw = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Skip app metadata entry
            if "im:name" in entry:
                continue
            if "content" in entry and "im:rating" in entry:
                raw.append(entry)
        return raw

    def _parse_flat_format(self, feed: dict, field_names: list[str]) -> list[dict]:
        """Format B: flat field-list — reconstruct a single review dict.

        Entry array is like: ["author", "updated", "im:rating", ...]
        Values are at feed[field_name] like: {"label": "5", ...}
        """
        review = {}
        for name in field_names:
            if name in feed:
                review[name] = feed[name]
        # Only return if it has rating content
        if "content" in review and "im:rating" in review:
            return [review]
        return []

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize(self, raw_reviews: list[dict], app_id: str) -> list[dict]:
        """Convert Apple RSS entries to unified schema."""
        result = []
        for r in raw_reviews:
            try:
                entry = self._normalize_entry(r)
                entry["app_name"] = self._get_app_name(app_id)
                entry["store"] = self.store_name
                result.append(entry)
            except (ValueError, KeyError, TypeError):
                continue
        return result

    @staticmethod
    def _normalize_entry(r: dict) -> dict:
        """Extract fields from a single review entry, handling nested label wrappers.

        Apple RSS wraps values in {'label': ...} dicts.
        But some values (like author) have {'name': {'label': ...}, 'uri': ...}.
        """
        def _extract(obj, *keys):
            """Drill into nested dicts to find the label value."""
            current = obj
            for k in keys:
                if isinstance(current, dict):
                    current = current.get(k, {})
                else:
                    return ""
            if isinstance(current, dict):
                return current.get("label", current.get("value", ""))
            return str(current) if current is not None else ""

        date_str = _extract(r, "updated")
        parsed = AppStoreChinaScraper._parse_date(date_str) if date_str else ""

        raw_rating = _extract(r, "im:rating")
        # Also try direct access for flat format
        if not raw_rating:
            raw_rating = _extract(r, "im:rating", "label")

        return {
            "app_name": "",  # filled in by caller
            "store": "",     # filled in by caller
            "rating": max(1, min(5, int(float(raw_rating)))) if raw_rating else 0,
            "title": _extract(r, "title"),
            "body": _extract(r, "content"),
            "date": parsed,
            "language": "zh",
            "author": _extract(r, "author", "name") or _extract(r, "author", "uri", "label"),
            "version": _extract(r, "im:version"),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: str) -> str:
        """Parse ISO 8601 date to YYYY-MM-DD."""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return date_str[:10] if len(date_str) >= 10 else ""

    @staticmethod
    def _get_app_name(app_id: str) -> str:
        """Lookup app name by ID. Falls back to app_id if unknown."""
        KNOWN = {
            "1488431932": "钓鱼天气预报",
            "6469984171": "正口-让路亚更简单",
            "6443960894": "钓鱼佬",
            "1028971150": "钓鱼人",
            "477967747": "Fishbrain",
        }
        return KNOWN.get(app_id, f"app_{app_id}")
