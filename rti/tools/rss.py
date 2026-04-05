from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from rti.core.cache import TTLCache
from rti.core.limiter import Limiters

log = logging.getLogger("rti.tools.rss")

CACHE_TTL = 30 * 60  # 30min

# free rss feeds — no api key needed
FEEDS = [
    ("https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "BBC"),
    ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml", "NYT"),
    ("https://news.google.com/rss/search?q=middle+east+conflict&hl=en", "Google News"),
]

CONFLICT_KEYWORDS = [
    "war", "conflict", "military", "strike", "airspace", "missile",
    "iran", "israel", "houthi", "hezbollah", "gaza", "syria",
    "lebanon", "yemen", "red sea", "bomb", "attack", "escalat",
    "flight cancel", "aviation", "no-fly", "sanction", "ceasefire",
    "casualt", "troops", "naval", "drone", "intercept",
]


class RSSClient:
    """pull conflict news from free rss feeds."""

    def __init__(self, cache: TTLCache, client: httpx.AsyncClient):
        self.cache = cache
        self.http = client

    async def fetch_feed(self, url: str, source: str) -> list[dict]:
        key = f"rss:{source}"

        async def _fetch():
            try:
                resp = await self.http.get(url, timeout=10)
                if resp.status_code != 200:
                    log.warning("rss %s: %d", source, resp.status_code)
                    return []
                return _parse_rss(resp.text, source)
            except Exception as e:
                log.error("rss %s: %s", source, e)
                return []

        return await self.cache.get_or_set(key, CACHE_TTL, _fetch)

    async def get_conflict_articles(self) -> list[dict]:
        """fetch all feeds, filter for conflict-related content."""
        batches = await asyncio.gather(
            *(self.fetch_feed(url, src) for url, src in FEEDS)
        )
        # merge + dedupe by title
        seen, merged = set(), []
        for batch in batches:
            for a in batch:
                t = a.get("title", "")
                if t and t not in seen:
                    seen.add(t)
                    merged.append(a)
        # filter for conflict keywords
        return [a for a in merged if _is_conflict(a.get("title", ""))]


def _parse_rss(xml_text: str, source: str) -> list[dict]:
    """parse rss xml into article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_text)
        # handle both rss and atom formats
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items[:30]:
            title = _tag_text(item, "title") or _tag_text(item, "{http://www.w3.org/2005/Atom}title")
            link = _tag_text(item, "link") or _tag_text(item, "{http://www.w3.org/2005/Atom}link")
            pub = _tag_text(item, "pubDate") or _tag_text(item, "{http://www.w3.org/2005/Atom}updated") or ""
            if title:
                articles.append({
                    "title": title.strip(),
                    "url": (link or "").strip(),
                    "source": source,
                    "publishedAt": pub,
                })
    except ET.ParseError as e:
        log.warning("rss parse failed for %s: %s", source, e)
    return articles


def _tag_text(el, tag: str) -> str | None:
    child = el.find(tag)
    return child.text if child is not None else None


def _is_conflict(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in CONFLICT_KEYWORDS)
