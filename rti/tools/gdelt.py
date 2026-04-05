from __future__ import annotations

import asyncio
import logging
import httpx

from rti.core.cache import TTLCache
from rti.core.limiter import Limiters

log = logging.getLogger("rti.tools.gdelt")

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
CACHE_TTL = 20 * 60  # gdelt updates every 15min, so 20 is fine

CONFLICT_QUERIES = [
    '"middle east" conflict OR war OR strike OR military',
    'airspace closure OR "no fly zone" OR NOTAM',
    'Iran OR Israel OR "Red Sea" OR Houthi military',
]


class GDELTClient:
    def __init__(self, cache: TTLCache, client: httpx.AsyncClient):
        self.cache = cache
        self.http = client

    async def search(
        self, query: str, timespan: str = "24hours", limit: int = 50
    ) -> list[dict]:
        key = f"gdelt:{query}:{timespan}"

        async def _fetch():
            await Limiters.gdelt.acquire()
            try:
                resp = await self.http.get(BASE, params={
                    "query": query,
                    "mode": "ArtList",
                    "format": "json",
                    "timespan": timespan,
                    "sort": "DateDesc",
                    "maxrecords": str(limit),
                }, timeout=15)
                if resp.status_code != 200:
                    log.warning("gdelt %d", resp.status_code)
                    return []
                return resp.json().get("articles", [])
            except Exception as e:
                log.error("gdelt: %s", e)
                return []

        return await self.cache.get_or_set(key, CACHE_TTL, _fetch)

    async def get_conflict_articles(self) -> list[dict]:
        """pull all conflict queries, merge and dedupe by url."""
        batches = await asyncio.gather(
            *(self.search(q) for q in CONFLICT_QUERIES)
        )
        seen, merged = set(), []
        for batch in batches:
            for a in batch:
                url = a.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    merged.append(a)
        return merged
