from __future__ import annotations

import asyncio
import logging
import time

import httpx

from rti.config import settings
from rti.core.cache import TTLCache
from rti.core.graph import DAGRunner
from rti.core.bus import bus, PIPELINE_DONE, ESCALATION_SPIKE
from rti.models.schemas import PipelineState, IntelBriefing
from rti.tools.gdelt import GDELTClient
from rti.tools.newsapi import NewsAPIClient
from rti.tools.aviationstack import AviationStackClient
from rti.tools.opensky import OpenSkyClient
from rti.tools.rss import RSSClient
from rti.agents.geointel import GeoIntelAgent
from rti.agents.aviation import AviationAgent
from rti.agents.analyst import AnalystAgent

log = logging.getLogger("rti.orchestrator")


class Orchestrator:
    """wires up the agent graph, runs the pipeline, caches results."""

    def __init__(self):
        self.cache = TTLCache(settings.cache_dir)
        self.http = httpx.AsyncClient(
            headers={"User-Agent": "RTI/1.0"},
            follow_redirects=True,
        )
        self.latest: IntelBriefing | None = None
        self._last_run = 0.0
        self._min_interval = 60  # don't re-run within 60s
        self._build_graph()

    def _build_graph(self):
        gdelt = GDELTClient(self.cache, self.http)
        newsapi = NewsAPIClient(settings.newsapi_key, self.cache, self.http)
        avstack = AviationStackClient(settings.aviationstack_key, self.cache, self.http)
        opensky = OpenSkyClient(self.cache, self.http, settings.opensky_user, settings.opensky_pass)
        rss = RSSClient(self.cache, self.http)

        geo = GeoIntelAgent(gdelt, newsapi, opensky, rss)
        avi = AviationAgent(avstack)
        analyst = AnalystAgent()

        self.dag = DAGRunner()
        self.dag.add("geointel", geo)
        self.dag.add("aviation", avi, deps=["geointel"])
        self.dag.add("analyst", analyst, deps=["geointel", "aviation"])

    async def run_pipeline(self) -> IntelBriefing:
        # skip if we just ran
        now = time.time()
        if self.latest and (now - self._last_run) < self._min_interval:
            log.info("skipped — last run was %ds ago", int(now - self._last_run))
            return self.latest

        t0 = time.time()
        log.info("--- pipeline started ---")

        state = PipelineState()
        state = await self.dag.run(state)

        elapsed_ms = int((time.time() - t0) * 1000)

        briefing = IntelBriefing(
            escalation_score=state.escalation_score,
            situation_summary=state.situation_summary,
            conflict_events=state.conflict_events[:50],
            airspace_zones=state.airspace_zones,
            route_health=state.route_health,
            risk_assessments=state.risk_assessments,
            recommendations=state.recommendations,
            pipeline_duration_ms=elapsed_ms,
        )

        self.latest = briefing
        self._last_run = time.time()

        # log cache stats
        stats = self.cache.stats()
        log.info("--- pipeline done in %dms | cache: %s ---", elapsed_ms, stats)

        # fire events
        await bus.publish(PIPELINE_DONE, briefing)
        if state.escalation_score >= 70:
            await bus.publish(ESCALATION_SPIKE, state.escalation_score)

        return briefing

    async def shutdown(self):
        await self.http.aclose()
