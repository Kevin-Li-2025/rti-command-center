from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger("rti.bus")


class EventBus:
    """in-process pub/sub via asyncio queues. no kafka needed (yet)."""

    def __init__(self):
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[topic].append(q)
        return q

    async def publish(self, topic: str, data: Any) -> None:
        for q in self._subs.get(topic, []):
            await q.put(data)


# singleton
bus = EventBus()

# topics
PIPELINE_DONE = "pipeline.done"
ESCALATION_SPIKE = "escalation.spike"
ROUTE_DISRUPTED = "route.disrupted"
