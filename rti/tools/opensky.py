from __future__ import annotations

import asyncio
import logging
import httpx

from rti.core.cache import TTLCache
from rti.core.limiter import Limiters

log = logging.getLogger("rti.tools.opensky")

BASE = "https://opensky-network.org/api/states/all"
CACHE_TTL = 15 * 60  # 15min — conserve api budget

# bounding boxes: (lat_min, lon_min, lat_max, lon_max)
ZONES = {
    "iran":         (25.0, 44.0, 40.0, 63.5),
    "persian_gulf": (23.5, 48.0, 30.5, 57.0),
    "red_sea":      (12.0, 36.0, 28.0, 44.0),
    "eastern_med":  (30.0, 25.0, 37.0, 36.5),
    "iraq":         (29.0, 38.5, 37.5, 49.0),
    "levant":       (29.0, 34.0, 37.0, 42.5),
}


class OpenSkyClient:
    def __init__(self, cache: TTLCache, client: httpx.AsyncClient, user: str = "", password: str = ""):
        self.cache = cache
        self.http = client
        self.user = user
        self.password = password

    async def aircraft_count(self, zone: str) -> int:
        """how many planes are over this zone right now?"""
        if zone not in ZONES:
            return -1

        key = f"opensky:{zone}"

        async def _fetch():
            await Limiters.opensky.acquire()
            bbox = ZONES[zone]
            auth = (self.user, self.password) if self.user and self.password else None
            try:
                resp = await self.http.get(BASE, params={
                    "lamin": bbox[0], "lomin": bbox[1],
                    "lamax": bbox[2], "lomax": bbox[3],
                }, auth=auth, timeout=15)
                if resp.status_code != 200:
                    log.warning("opensky %d", resp.status_code)
                    return -1
                states = resp.json().get("states") or []
                return len(states)
            except Exception as e:
                log.error("opensky: %s", e)
                return -1

        return await self.cache.get_or_set(key, CACHE_TTL, _fetch)

    async def scan_all(self) -> dict[str, int]:
        """aircraft count for every zone we care about."""
        results = await asyncio.gather(
            *(self.aircraft_count(z) for z in ZONES)
        )
        return dict(zip(ZONES.keys(), results))
