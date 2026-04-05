from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger("rti.limiter")


class TokenBucket:
    """token-bucket rate limiter with daily budget tracking."""

    def __init__(self, rate: float, capacity: int, daily_limit: int = 0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        # daily budget
        self.daily_limit = daily_limit
        self.daily_used = 0
        self._day_start = time.time()

    def _reset_day_if_needed(self):
        elapsed = time.time() - self._day_start
        if elapsed >= 86400:
            self.daily_used = 0
            self._day_start = time.time()

    def has_budget(self) -> bool:
        """still have API calls left today?"""
        if not self.daily_limit:
            return True
        self._reset_day_if_needed()
        return self.daily_used < self.daily_limit

    async def acquire(self) -> None:
        async with self._lock:
            self._reset_day_if_needed()
            self.daily_used += 1

            now = time.monotonic()
            self.tokens = min(
                self.capacity,
                self.tokens + (now - self.last_refill) * self.rate,
            )
            self.last_refill = now

            if self.tokens < 1.0:
                wait = (1.0 - self.tokens) / self.rate
                log.debug("throttled %.1fs", wait)
                await asyncio.sleep(wait)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class Limiters:
    """per-api buckets. conservative to stay on free tiers."""
    gdelt = TokenBucket(rate=10 / 60, capacity=5, daily_limit=500)
    newsapi = TokenBucket(rate=90 / 86400, capacity=3, daily_limit=90)
    avstack = TokenBucket(rate=3 / 86400, capacity=1, daily_limit=3)
    opensky = TokenBucket(rate=100 / 86400, capacity=10, daily_limit=100)
