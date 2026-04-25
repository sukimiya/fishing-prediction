"""Base scraper with caching, rate limiting, and unified review schema."""

import json
import hashlib
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class BaseScraper(ABC):
    """Abstract base scraper for app store reviews.

    Subclasses must implement fetch_page() to get raw reviews from their
    specific store, then normalize() to convert them into the unified schema.
    """

    UNIFIED_SCHEMA = [
        "app_name", "store", "rating", "title", "body",
        "date", "language", "author", "version",
    ]

    def __init__(self, cache_dir: str = "data/module1/cached_pages", cache_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self._last_request_time: Optional[float] = None
        self.min_request_interval = 1.0  # seconds between requests

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_reviews(self, app_id: str, max_pages: int = 10) -> list[dict]:
        """Fetch and normalize reviews for a given app.

        Returns a list of dicts in the unified schema.
        """
        all_reviews = []
        for page in range(1, max_pages + 1):
            cache_key = self._cache_key(app_id, page)
            cached = self._load_from_cache(cache_key)
            if cached is not None:
                all_reviews.extend(cached)
                continue

            raw = self._fetch_page_with_retry(app_id, page)
            if not raw:
                break

            normalized = self.normalize(raw, app_id)
            self._save_to_cache(cache_key, normalized)
            all_reviews.extend(normalized)
            self._rate_limit()

        return all_reviews

    # ------------------------------------------------------------------
    # Subclass responsibilities
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_page(self, app_id: str, page: int) -> list[dict]:
        """Fetch one page of raw reviews from the store API.

        Must return a list of raw dicts (store-specific format).
        Should return an empty list when no more pages are available.
        """

    @abstractmethod
    def normalize(self, raw_reviews: list[dict], app_id: str) -> list[dict]:
        """Convert store-specific raw reviews into the unified schema.

        Each returned dict must have all keys listed in UNIFIED_SCHEMA.
        """

    @property
    @abstractmethod
    def store_name(self) -> str:
        """Human-readable store name, e.g. 'apple_app_store_china'."""

    # ------------------------------------------------------------------
    # Rate limiting & caching
    # ------------------------------------------------------------------

    def _rate_limit(self):
        """Ensure minimum interval between requests."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    def _fetch_page_with_retry(self, app_id: str, page: int) -> list[dict]:
        """Wrapper that adds retry logic around fetch_page()."""
        return self.fetch_page(app_id, page)

    def _cache_key(self, app_id: str, page: int) -> str:
        raw = f"{self.store_name}:{app_id}:page{page}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _cache_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"

    def _load_from_cache(self, cache_key: str) -> Optional[list[dict]]:
        path = self._cache_path(cache_key)
        if not path.exists():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime > self.cache_ttl:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_to_cache(self, cache_key: str, data: list[dict]):
        path = self._cache_path(cache_key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    @staticmethod
    def make_client() -> httpx.Client:
        """Create a default HTTPX client with sensible defaults."""
        return httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
