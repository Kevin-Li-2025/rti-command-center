from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI
from rti.config import settings
from rti.models.schemas import (
    PipelineState, RiskAssessment, Severity, PriceDirection,
)

log = logging.getLogger("rti.agents.analyst")

# layer-1: fast structured extraction
SYS_FAST = """You are a travel risk analyst. Extract structured risk data from geopolitical + aviation inputs.

Return ONLY valid JSON:
{
  "risk_assessments": [
    {"route":"DXB-LHR","risk_level":"low|medium|high|critical","reasoning":"brief","recommendation":"brief","price_direction":"up|down|stable|volatile"}
  ]
}

Top 10-15 most impacted routes. No markdown, no explanation."""

# layer-2: deep analysis (only when escalation is high)
SYS_DEEP = """You are a senior travel risk analyst producing a high-stakes intelligence brief.

Given the structured risk data and raw intelligence, produce JSON:
{
  "situation_summary": "<2-3 paragraph analysis>",
  "recommendations": ["<top 5 actionable tips>"]
}

Be specific about regions, airlines, and alternative routing. Only valid JSON."""


class AnalystAgent:
    """two-layer reasoning: fast extraction + conditional deep analysis."""
    name = "analyst"

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

    async def run(self, state: PipelineState) -> PipelineState:
        prompt = _build_prompt(state)

        # layer 1: cheap/fast structured extraction
        try:
            state = await self._layer1(state, prompt)
        except Exception as e:
            log.error("layer-1 failed: %s", e)
            state.situation_summary = f"Analysis unavailable — {e}"
            return state

        # layer 2: deep reasoning only when things are bad
        if state.escalation_score >= settings.escalation_threshold:
            try:
                state = await self._layer2(state, prompt)
            except Exception as e:
                log.error("layer-2 failed: %s", e)
                state.situation_summary = _fallback_summary(state)
        else:
            # low escalation — template summary, no LLM call
            state.situation_summary = _fallback_summary(state)
            state.recommendations = _fallback_recs(state)

        log.info("analyst done, %d assessments, escalation=%d",
                 len(state.risk_assessments), state.escalation_score)
        return state

    async def _layer1(self, state: PipelineState, prompt: str) -> PipelineState:
        """fast model — structured risk extraction only."""
        resp = await self.client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": SYS_FAST},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        raw = _clean_json(resp.choices[0].message.content or "{}")
        data = json.loads(raw)

        for r in data.get("risk_assessments", []):
            state.risk_assessments.append(RiskAssessment(
                route=r.get("route", ""),
                risk_level=_sev(r.get("risk_level", "medium")),
                reasoning=r.get("reasoning", ""),
                recommendation=r.get("recommendation", ""),
                price_direction=_dir(r.get("price_direction", "stable")),
            ))
        return state

    async def _layer2(self, state: PipelineState, prompt: str) -> PipelineState:
        """full model — situation summary + strategic recommendations."""
        # include layer-1 results for context
        risk_ctx = "\n".join(
            f"- {r.route}: {r.risk_level.value} — {r.reasoning}"
            for r in state.risk_assessments[:15]
        )
        deep_prompt = f"{prompt}\n\n## LAYER-1 RISK ASSESSMENTS\n{risk_ctx}"

        resp = await self.client.chat.completions.create(
            model=settings.active_model,
            messages=[
                {"role": "system", "content": SYS_DEEP},
                {"role": "user", "content": deep_prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )
        raw = _clean_json(resp.choices[0].message.content or "{}")
        data = json.loads(raw)

        state.situation_summary = data.get("situation_summary", "")
        state.recommendations = data.get("recommendations", [])
        return state


# helpers

def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def _fallback_summary(s: PipelineState) -> str:
    n_disrupted = sum(1 for r in s.route_health if r.status.value != "normal")
    regions = ", ".join(s.affected_regions[:5]) or "Middle East"
    return (
        f"Monitoring {len(s.conflict_events)} conflict events across {regions}. "
        f"Escalation score: {s.escalation_score}/100. "
        f"{n_disrupted}/{len(s.route_health)} routes showing disruption or degradation. "
        f"Airspace conditions are being tracked across {len(s.airspace_zones)} zones."
    )


def _fallback_recs(s: PipelineState) -> list[str]:
    recs = ["Monitor situation — escalation is below threshold."]
    closed = [z.name for z in s.airspace_zones if z.status == "closed"]
    if closed:
        recs.append(f"Avoid routing through: {', '.join(closed)}.")
    recs.append("Maintain standard operational procedures.")
    return recs


def _build_prompt(s: PipelineState) -> str:
    events_str = "\n".join(
        f"- [{e.region}] {e.title} (tone={e.tone:.1f})"
        for e in s.conflict_events[:30]
    ) or "No events found."

    zones_str = "\n".join(
        f"- {z.name}: {z.aircraft_count} aircraft, status={z.status}"
        for z in s.airspace_zones
    )

    routes_str = "\n".join(
        f"- {r.origin}-{r.destination}: {r.status.value} "
        f"(disrupted={r.disrupted_count}/{r.total_count}, delay={r.avg_delay_min}min)"
        for r in s.route_health if r.status.value != "normal"
    ) or "All routes currently normal."

    return f"""## GEOPOLITICAL INTELLIGENCE
Escalation Score: {s.escalation_score}/100
Affected Regions: {', '.join(s.affected_regions) or 'None detected'}

### Recent Events (top 30)
{events_str}

### Airspace Zones
{zones_str}

## AVIATION DATA
### Disrupted/Degraded Routes
{routes_str}

Analyze the situation and produce your JSON assessment."""


def _sev(v: str) -> Severity:
    try:
        return Severity(v.lower())
    except ValueError:
        return Severity.MEDIUM


def _dir(v: str) -> PriceDirection:
    try:
        return PriceDirection(v.lower())
    except ValueError:
        return PriceDirection.STABLE
