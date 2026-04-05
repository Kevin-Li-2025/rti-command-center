from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RouteStatus(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    DISRUPTED = "disrupted"
    CLOSED = "closed"


class PriceDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    VOLATILE = "volatile"


# --- data objects ---

class ConflictEvent(BaseModel):
    title: str
    url: str = ""
    source: str = ""
    region: str = ""
    tone: float = 0.0  # negative = bad vibes
    published_at: str = ""


class AirspaceZone(BaseModel):
    name: str
    bbox: list[float] = Field(default_factory=list)
    aircraft_count: int = 0
    status: str = "unknown"


class FlightInfo(BaseModel):
    flight_iata: str | None = ""
    airline: str | None = ""
    departure: str | None = ""
    arrival: str | None = ""
    status: str | None = ""
    delay_minutes: int | None = None


class RouteHealth(BaseModel):
    origin: str
    destination: str
    status: RouteStatus = RouteStatus.NORMAL
    disrupted_count: int = 0
    total_count: int = 0
    avg_delay_min: float = 0.0


class RiskAssessment(BaseModel):
    route: str
    risk_level: Severity = Severity.LOW
    reasoning: str = ""
    recommendation: str = ""
    price_direction: PriceDirection = PriceDirection.STABLE


class IntelBriefing(BaseModel):
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    escalation_score: int = 0
    situation_summary: str = ""
    conflict_events: list[ConflictEvent] = Field(default_factory=list)
    airspace_zones: list[AirspaceZone] = Field(default_factory=list)
    route_health: list[RouteHealth] = Field(default_factory=list)
    risk_assessments: list[RiskAssessment] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    pipeline_duration_ms: int = 0


# --- pipeline state ---

class PipelineState(BaseModel):
    """mutable bag of data flowing through the agent graph."""
    conflict_events: list[ConflictEvent] = Field(default_factory=list)
    escalation_score: int = 0
    affected_regions: list[str] = Field(default_factory=list)
    airspace_zones: list[AirspaceZone] = Field(default_factory=list)
    flights: list[FlightInfo] = Field(default_factory=list)
    route_health: list[RouteHealth] = Field(default_factory=list)
    risk_assessments: list[RiskAssessment] = Field(default_factory=list)
    situation_summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
