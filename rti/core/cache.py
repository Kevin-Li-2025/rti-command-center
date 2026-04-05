from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger("rti.cache")


class TTLCache:
    """mem -> disk two-tier cache. no redis needed."""

    def __init__(self, cache_dir: str | Path = ".cache"):
        self._mem: dict[str, tuple[float, Any]] = {}
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _disk_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self._dir / f"{h}.json"

    def _fresh(self, ts: float, ttl: int) -> bool:
        return (time.time() - ts) < ttl

    async def get_or_set(
        self,
        key: str,
        ttl_seconds: int,
        fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        # mem hit?
        if key in self._mem:
            ts, val = self._mem[key]
            if self._fresh(ts, ttl_seconds):
                self.hits += 1
                return val

        # disk hit?
        dp = self._disk_path(key)
        if dp.exists():
            try:
                data = json.loads(dp.read_text())
                if self._fresh(data["ts"], ttl_seconds):
                    self._mem[key] = (data["ts"], data["val"])
                    self.hits += 1
                    return data["val"]
            except (json.JSONDecodeError, KeyError):
                pass

        # miss — fetch
        self.misses += 1
        val = await fn()
        now = time.time()
        self._mem[key] = (now, val)
        try:
            dp.write_text(json.dumps({"ts": now, "val": val}, default=str))
        except TypeError:
            pass
        return val

    def get_stale(self, key: str) -> Any | None:
        """return cached value even if expired. useful for fast startup."""
        if key in self._mem:
            return self._mem[key][1]
        dp = self._disk_path(key)
        if dp.exists():
            try:
                return json.loads(dp.read_text())["val"]
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def bust(self, key: str) -> None:
        self._mem.pop(key, None)
        self._disk_path(key).unlink(missing_ok=True)

    def clear_all(self) -> None:
        self._mem.clear()
        for f in self._dir.glob("*.json"):
            f.unlink()

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "mem_keys": len(self._mem)}
