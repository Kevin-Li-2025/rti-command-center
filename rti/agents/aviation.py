from __future__ import annotations

import logging
import random
from rti.models.schemas import (
    PipelineState, FlightInfo, RouteHealth, RouteStatus, AirspaceZone,
)
from rti.tools.aviationstack import AviationStackClient

log = logging.getLogger("rti.agents.aviation")

# 80+ routes across every major corridor that crosses conflict zones
WATCHED_ROUTES = [
    # gulf <-> europe
    ("DXB", "LHR"), ("DXB", "CDG"), ("DXB", "FRA"), ("DXB", "AMS"),
    ("DXB", "FCO"), ("DXB", "MUC"), ("DXB", "ZRH"), ("DXB", "MAD"),
    ("DXB", "BCN"), ("DXB", "VIE"), ("DXB", "MAN"),
    ("DOH", "LHR"), ("DOH", "CDG"), ("DOH", "FRA"), ("DOH", "MAN"),
    ("DOH", "FCO"), ("DOH", "BCN"),
    ("AUH", "LHR"), ("AUH", "CDG"), ("AUH", "FRA"),
    ("RUH", "LHR"), ("RUH", "CDG"), ("JED", "LHR"), ("JED", "CAI"),
    ("KWI", "LHR"), ("BAH", "LHR"), ("MCT", "LHR"),
    # gulf <-> north america
    ("DXB", "JFK"), ("DXB", "LAX"), ("DXB", "IAD"), ("DXB", "ORD"),
    ("DXB", "SFO"), ("DXB", "YYZ"), ("DXB", "DFW"),
    ("DOH", "JFK"), ("DOH", "LAX"), ("DOH", "ORD"), ("DOH", "IAD"),
    ("AUH", "JFK"), ("AUH", "IAD"), ("AUH", "ORD"),
    # gulf <-> south/se asia
    ("DXB", "BOM"), ("DXB", "DEL"), ("DXB", "SIN"), ("DXB", "HKG"),
    ("DXB", "BKK"), ("DXB", "KUL"), ("DXB", "MNL"), ("DXB", "CGK"),
    ("DXB", "CMB"), ("DXB", "DAC"), ("DXB", "KHI"), ("DXB", "ISB"),
    ("DOH", "SIN"), ("DOH", "HKG"), ("DOH", "BKK"),
    ("AUH", "BOM"), ("AUH", "DEL"), ("AUH", "SIN"),
    # gulf <-> east asia
    ("DXB", "NRT"), ("DXB", "ICN"), ("DXB", "PVG"), ("DXB", "PEK"),
    ("DXB", "TPE"), ("DOH", "NRT"), ("DOH", "ICN"), ("DOH", "PVG"),
    # transit hubs
    ("IST", "LHR"), ("IST", "JFK"), ("IST", "DXB"), ("IST", "CDG"),
    ("CAI", "LHR"), ("CAI", "CDG"), ("CAI", "DXB"), ("CAI", "JFK"),
    ("AMM", "LHR"), ("AMM", "DXB"), ("AMM", "CDG"),
    # directly impacted
    ("TLV", "LHR"), ("TLV", "JFK"), ("TLV", "IST"), ("TLV", "CDG"),
    ("IKA", "IST"), ("IKA", "DXB"),
    # intra-gulf
    ("DXB", "DOH"), ("DXB", "RUH"), ("DXB", "KWI"), ("DXB", "BAH"),
    ("DXB", "MCT"), ("DOH", "KWI"), ("AUH", "RUH"),
    # africa
    ("DXB", "NBO"), ("DXB", "ADD"), ("DOH", "NBO"),
    ("JED", "ADD"), ("JED", "AMM"),
]

# airports near conflict zones
_ZONE_MAP = {
    "DXB": ["persian_gulf"], "AUH": ["persian_gulf"],
    "DOH": ["persian_gulf"], "BAH": ["persian_gulf"],
    "KWI": ["persian_gulf", "iraq"], "MCT": ["persian_gulf"],
    "RUH": ["persian_gulf"], "JED": ["red_sea"],
    "IKA": ["iran"], "IST": ["eastern_med"],
    "CAI": ["red_sea", "eastern_med"],
    "TLV": ["levant", "eastern_med"], "AMM": ["levant"],
}

_LONG_HAUL = {
    "LHR", "CDG", "FRA", "AMS", "FCO", "MUC", "ZRH", "MAD", "BCN",
    "VIE", "MAN", "JFK", "LAX", "IAD", "ORD", "SFO", "YYZ", "DFW",
}
_GULF = {"DXB", "DOH", "AUH", "BAH", "KWI", "MCT", "RUH", "JED"}

# typical daily flights per route (rough estimates for simulation)
_TYPICAL_FLIGHTS = {
    "DXB": 14, "DOH": 10, "AUH": 8, "RUH": 6, "JED": 5,
    "LHR": 12, "JFK": 8, "CDG": 7, "FRA": 7, "IST": 9,
}


class AviationAgent:
    """tracks disruptions. uses real data when available, simulates when not."""
    name = "aviation"

    def __init__(self, avstack: AviationStackClient):
        self.avstack = avstack

    async def run(self, state: PipelineState) -> PipelineState:
        flights = []
        has_real_data = False

        if self.avstack.key:
            for hub in ("DXB", "DOH", "AUH"):
                for f in await self.avstack.flights(dep_iata=hub):
                    dep = f.get("departure") or {}
                    arr = f.get("arrival") or {}
                    flights.append(FlightInfo(
                        flight_iata=(f.get("flight") or {}).get("iata") or "",
                        airline=(f.get("airline") or {}).get("name") or "",
                        departure=dep.get("iata") or "",
                        arrival=arr.get("iata") or "",
                        status=f.get("status") or "",
                        delay_minutes=dep.get("delay"),
                    ))
            has_real_data = len(flights) > 0

        health = []
        for orig, dest in WATCHED_ROUTES:
            if has_real_data:
                rf = [f for f in flights if f.departure == orig and f.arrival == dest]
                if rf:
                    bad = sum(1 for f in rf if f.status in ("cancelled", "diverted"))
                    delays = [f.delay_minutes for f in rf if f.delay_minutes and f.delay_minutes > 0]
                    avg = sum(delays) / len(delays) if delays else 0
                    health.append(RouteHealth(
                        origin=orig, destination=dest,
                        status=_flight_status(bad, len(rf), avg),
                        disrupted_count=bad, total_count=len(rf),
                        avg_delay_min=round(avg, 1),
                    ))
                    continue

            # no real data for this route — simulate from airspace status
            health.append(_simulate_route(orig, dest, state.airspace_zones))

        state.flights = flights
        state.route_health = health
        log.info("%d real flights, %d routes assessed", len(flights), len(health))
        return state


def _simulate_route(orig: str, dest: str, zones: list[AirspaceZone]) -> RouteHealth:
    """generate realistic metrics based on airspace conditions."""
    status = _infer_from_airspace(orig, dest, zones)

    # estimate typical flight count for this route
    base_flights = min(_TYPICAL_FLIGHTS.get(orig, 4), _TYPICAL_FLIGHTS.get(dest, 4))
    total = base_flights + random.randint(-1, 2)
    total = max(2, total)

    if status == RouteStatus.DISRUPTED:
        # heavy disruption: 50-80% flights affected, big delays
        disrupted = int(total * random.uniform(0.5, 0.8))
        avg_delay = round(random.uniform(90, 240), 1)
    elif status == RouteStatus.DEGRADED:
        # moderate: 20-50% affected, moderate delays
        disrupted = int(total * random.uniform(0.2, 0.5))
        avg_delay = round(random.uniform(30, 120), 1)
    else:
        # normal: minor issues
        disrupted = random.randint(0, 1)
        avg_delay = round(random.uniform(0, 15), 1)

    return RouteHealth(
        origin=orig, destination=dest,
        status=status,
        disrupted_count=disrupted,
        total_count=total,
        avg_delay_min=avg_delay,
    )


def _flight_status(bad: int, total: int, avg_delay: float) -> RouteStatus:
    if total == 0:
        return RouteStatus.NORMAL
    r = bad / total
    if r > 0.5 or avg_delay > 180:
        return RouteStatus.DISRUPTED
    if r > 0.2 or avg_delay > 60:
        return RouteStatus.DEGRADED
    return RouteStatus.NORMAL


def _infer_from_airspace(orig: str, dest: str, zones: list[AirspaceZone]) -> RouteStatus:
    relevant = set()
    for apt in (orig, dest):
        relevant.update(_ZONE_MAP.get(apt, []))
    # long-haul <-> gulf usually overflies iran
    if (orig in _LONG_HAUL and dest in _GULF) or (orig in _GULF and dest in _LONG_HAUL):
        relevant.add("iran")

    for z in zones:
        if z.name in relevant:
            if z.status == "closed":
                return RouteStatus.DISRUPTED
            if z.status == "restricted":
                return RouteStatus.DEGRADED
    return RouteStatus.NORMAL
