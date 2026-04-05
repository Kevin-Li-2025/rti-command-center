from __future__ import annotations

import logging
import httpx

from rti.core.cache import TTLCache
from rti.core.limiter import Limiters

log = logging.getLogger("rti.tools.newsapi")

BASE = "https://newsapi.org/v2/everything"
CACHE_TTL = 4 * 60 * 60  # 4h — we only get 100 req/day


class NewsAPIClient:
    def __init__(self, api_key: str, cache: TTLCache, client: httpx.AsyncClient):
        self.key = api_key
        self.cache = cache
        self.http = client

    async def search(self, query: str, page_size: int = 20) -> list[dict]:
        if not self.key:
            log.warning("no newsapi key configured, skipping")
            return []

        cache_key = f"newsapi:{query}"

        async def _fetch():
            await Limiters.newsapi.acquire()
            try:
                resp = await self.http.get(BASE, params={
                    "q": query,
                    "apiKey": self.key,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": page_size,
                }, timeout=15)
                if resp.status_code != 200:
                    log.warning("newsapi %d: %s", resp.status_code, resp.text[:200])
                    return []
                return resp.json().get("articles", [])
            except Exception as e:
                log.error("newsapi: %s", e)
                return []

        return await self.cache.get_or_set(cache_key, CACHE_TTL, _fetch)

    async def conflict_news(self) -> list[dict]:
        return await self.search(
            "middle east conflict OR airspace OR Iran Israel war OR flight cancellation"
        )

    async def aviation_news(self) -> list[dict]:
        return await self.search(
            "flight disruption OR airline cancel OR airspace closure"
        )
