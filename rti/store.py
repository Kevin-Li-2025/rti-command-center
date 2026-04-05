from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite

from rti.config import settings
from rti.models.schemas import IntelBriefing

log = logging.getLogger("rti.store")


class Store:
    """sqlite for run history. nothing fancy."""

    def __init__(self, db_path: str | None = None):
        self.path = str(db_path or settings.db_path)
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self.path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                escalation_score INTEGER,
                data TEXT NOT NULL
            )
        """)
        await self._db.commit()
        log.info("store ready at %s", self.path)

    async def save(self, briefing: IntelBriefing):
        if not self._db:
            return
        await self._db.execute(
            "INSERT INTO briefings (timestamp, escalation_score, data) VALUES (?, ?, ?)",
            (briefing.timestamp, briefing.escalation_score, briefing.model_dump_json()),
        )
        await self._db.commit()

    async def get_latest(self) -> IntelBriefing | None:
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT data FROM briefings ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if row:
                return IntelBriefing.model_validate_json(row[0])
        return None

    async def get_history(self, limit: int = 20) -> list[dict]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT id, timestamp, escalation_score FROM briefings ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return [
                {"id": r[0], "timestamp": r[1], "escalation_score": r[2]}
                async for r in cur
            ]

    async def close(self):
        if self._db:
            await self._db.close()
