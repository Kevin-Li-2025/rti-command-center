from __future__ import annotations

import asyncio
import logging

from rti.models.schemas import PipelineState, ConflictEvent, AirspaceZone
from rti.tools.gdelt import GDELTClient
from rti.tools.newsapi import NewsAPIClient
from rti.tools.opensky import OpenSkyClient, ZONES
from rti.tools.rss import RSSClient

log = logging.getLogger("rti.agents.geointel")


class GeoIntelAgent:
    """watches the world burn, reports back."""
    name = "geointel"

    def __init__(self, gdelt: GDELTClient, newsapi: NewsAPIClient,
                 opensky: OpenSkyClient, rss: RSSClient):
        self.gdelt = gdelt
        self.newsapi = newsapi
        self.opensky = opensky
        self.rss = rss

    async def run(self, state: PipelineState) -> PipelineState:
        # fan out all sources
        gdelt_arts, news_arts, rss_arts, density = await asyncio.gather(
            self.gdelt.get_conflict_articles(),
            self.newsapi.conflict_news(),
            self.rss.get_conflict_articles(),
            self.opensky.scan_all(),
        )

        events = []
        # gdelt
        for a in gdelt_arts:
            events.append(ConflictEvent(
                title=a.get("title", ""),
                url=a.get("url", ""),
                source=a.get("domain", a.get("source", "")),
                region=_tag_region(a.get("title", "")),
                tone=float(a.get("tone", 0)),
                published_at=a.get("seendate", ""),
            ))
        # newsapi
        for a in news_arts:
            src = a.get("source", {})
            events.append(ConflictEvent(
                title=a.get("title", ""),
                url=a.get("url", ""),
                source=src.get("name", "") if isinstance(src, dict) else str(src),
                region=_tag_region(a.get("title", "")),
                tone=-30.0,
                published_at=a.get("publishedAt", ""),
            ))
        # rss feeds
        for a in rss_arts:
            events.append(ConflictEvent(
                title=a.get("title", ""),
                url=a.get("url", ""),
                source=a.get("source", "RSS"),
                region=_tag_region(a.get("title", "")),
                tone=_estimate_tone(a.get("title", "")),
                published_at=a.get("publishedAt", ""),
            ))

        # airspace picture
        zones = []
        for name, bbox in ZONES.items():
            count = density.get(name, -1)
            zones.append(AirspaceZone(
                name=name, bbox=list(bbox),
                aircraft_count=count,
                status=_zone_status(name, count),
            ))

        state.conflict_events = events
        state.escalation_score = _escalation_score(events, density)
        state.affected_regions = list({e.region for e in events if e.region})
        state.airspace_zones = zones

        log.info(
            "%d events (gdelt=%d, news=%d, rss=%d), escalation=%d, %d zones",
            len(events), len(gdelt_arts), len(news_arts), len(rss_arts),
            state.escalation_score, len(zones),
        )
        return state


# baselines
_BASELINE = {
    "iran": 40, "persian_gulf": 120, "red_sea": 60,
    "eastern_med": 100, "iraq": 30, "levant": 50,
}

_REGION_KEYWORDS = {
    "Iran": ["iran", "tehran", "isfahan", "persian"],
    "Israel/Palestine": ["israel", "tel aviv", "gaza", "idf", "netanyahu"],
    "Yemen/Red Sea": ["yemen", "houthi", "red sea", "aden"],
    "Iraq": ["iraq", "baghdad"],
    "Syria": ["syria", "damascus"],
    "Lebanon": ["lebanon", "beirut", "hezbollah"],
    "UAE": ["dubai", "uae", "abu dhabi", "emirates"],
    "Saudi Arabia": ["saudi", "riyadh", "jeddah"],
    "Turkey": ["turkey", "istanbul", "ankara"],
}

# keywords for rss tone estimation
_SEVERE_WORDS = ["kill", "dead", "bomb", "missile", "attack", "strike", "casualt", "destroy"]
_MODERATE_WORDS = ["escalat", "tension", "conflict", "war", "military", "sanction", "threat"]


def _tag_region(title: str) -> str:
    t = title.lower()
    for region, kws in _REGION_KEYWORDS.items():
        if any(w in t for w in kws):
            return region
    return "Middle East"


def _estimate_tone(title: str) -> float:
    """rough tone from headline keywords. negative = bad."""
    t = title.lower()
    if any(w in t for w in _SEVERE_WORDS):
        return -45.0
    if any(w in t for w in _MODERATE_WORDS):
        return -25.0
    return -15.0


def _zone_status(name: str, count: int) -> str:
    base = _BASELINE.get(name, 50)
    if count < 0:
        return "unknown"
    ratio = count / base if base > 0 else 1
    if ratio < 0.15:
        return "closed"
    if ratio < 0.4:
        return "restricted"
    if ratio < 0.7:
        return "degraded"
    return "open"


def _escalation_score(events: list[ConflictEvent], density: dict[str, int]) -> int:
    if not events:
        return 0
    # tone: 0-50
    avg_tone = sum(e.tone for e in events) / len(events)
    tone_score = min(50, max(0, int(-avg_tone * 3)))
    # density drop: 0-50
    drops = []
    for zone, base in _BASELINE.items():
        c = density.get(zone, base)
        if c >= 0 and base > 0:
            drops.append(max(0.0, 1.0 - c / base))
    density_score = int(50 * (sum(drops) / len(drops))) if drops else 0
    return min(100, tone_score + density_score)
