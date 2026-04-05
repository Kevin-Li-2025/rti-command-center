from __future__ import annotations

import logging
import httpx

from rti.core.cache import TTLCache
from rti.core.limiter import Limiters

log = logging.getLogger("rti.tools.avstack")

BASE = "http://api.aviationstack.com/v1/flights"
CACHE_TTL = 12 * 60 * 60  # 12h — only ~3 calls/day budget


class AviationStackClient:
    def __init__(self, api_key: str, cache: TTLCache, client: httpx.AsyncClient):
        self.key = api_key
        self.cache = cache
        self.http = client

    async def flights(
        self, dep_iata: str | None = None, arr_iata: str | None = None
    ) -> list[dict]:
        if not self.key:
            log.warning("no aviationstack key, skipping")
            return []

        cache_key = f"avstack:{dep_iata or '*'}:{arr_iata or '*'}"

        async def _fetch():
            await Limiters.avstack.acquire()
            params: dict = {"access_key": self.key}
            if dep_iata:
                params["dep_iata"] = dep_iata
            if arr_iata:
                params["arr_iata"] = arr_iata
            try:
                resp = await self.http.get(BASE, params=params, timeout=20)
                if resp.status_code != 200:
                    log.warning("avstack %d", resp.status_code)
                    return []
                return resp.json().get("data", [])
            except Exception as e:
                log.error("avstack: %s", e)
                return []

        return await self.cache.get_or_set(cache_key, CACHE_TTL, _fetch)
