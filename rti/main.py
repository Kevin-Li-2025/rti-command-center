from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from weakref import WeakSet

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from rti.config import settings
from rti.agents.orchestrator import Orchestrator
from rti.store import Store
from rti.core.bus import bus, PIPELINE_DONE
from rti.models.schemas import IntelBriefing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rti")

orch: Orchestrator
store: Store
_scheduler_task: asyncio.Task | None = None
_ws_broadcast_task: asyncio.Task | None = None

# connected websocket clients
_ws_clients: WeakSet[WebSocket] = WeakSet()


async def _broadcast(briefing: IntelBriefing):
    """push briefing to all connected websockets."""
    payload = briefing.model_dump_json()
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


async def _ws_listener():
    """subscribe to pipeline events and broadcast to ws clients."""
    q = bus.subscribe(PIPELINE_DONE)
    while True:
        briefing = await q.get()
        await _broadcast(briefing)


async def _scheduler():
    """autonomous pipeline loop."""
    interval = settings.pipeline_interval_hours * 3600
    while True:
        try:
            briefing = await orch.run_pipeline()
            await store.save(briefing)
            log.info("scheduled run saved, next in %dh", settings.pipeline_interval_hours)
        except Exception as e:
            log.error("scheduled run failed: %s", e)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orch, store, _scheduler_task, _ws_broadcast_task
    orch = Orchestrator()
    store = Store()
    await store.init()
    _scheduler_task = asyncio.create_task(_scheduler())
    _ws_broadcast_task = asyncio.create_task(_ws_listener())
    log.info("RTI online — %s via %s", settings.active_model, settings.llm_provider)
    yield
    _scheduler_task.cancel()
    _ws_broadcast_task.cancel()
    await orch.shutdown()
    await store.close()
    log.info("RTI shutdown")


app = FastAPI(
    title="RTI — Resilience Travel Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="rti/static"), name="static")


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    log.info("ws client connected (%d total)", len(_ws_clients))

    # send latest briefing immediately on connect
    if orch.latest:
        await ws.send_text(orch.latest.model_dump_json())

    try:
        while True:
            # keep alive — client can send pings or commands
            msg = await ws.receive_text()
            if msg == "run":
                briefing = await orch.run_pipeline()
                await store.save(briefing)
    except WebSocketDisconnect:
        _ws_clients.discard(ws)
        log.info("ws client disconnected")


@app.get("/api/v1/briefing", response_model=IntelBriefing)
async def get_briefing():
    if orch.latest:
        return orch.latest
    saved = await store.get_latest()
    if saved:
        return saved
    raise HTTPException(404, "no briefing yet — trigger a run first via POST /api/v1/run")


@app.get("/api/v1/routes/{route}")
async def get_route(route: str):
    briefing = orch.latest or await store.get_latest()
    if not briefing:
        raise HTTPException(404, "no data yet")

    origin, _, dest = route.upper().partition("-")
    if not dest:
        raise HTTPException(400, "use format ORIGIN-DEST e.g. DXB-LHR")

    health = next(
        (r for r in briefing.route_health if r.origin == origin and r.destination == dest),
        None,
    )
    risk = next(
        (r for r in briefing.risk_assessments if r.route.upper() == route.upper()),
        None,
    )
    return {
        "route": route.upper(),
        "health": health,
        "risk": risk,
        "escalation_score": briefing.escalation_score,
    }


@app.get("/api/v1/events")
async def get_events(limit: int = 30):
    briefing = orch.latest or await store.get_latest()
    if not briefing:
        raise HTTPException(404, "no data yet")
    return {"events": briefing.conflict_events[:limit]}


@app.get("/api/v1/airspace")
async def get_airspace():
    briefing = orch.latest or await store.get_latest()
    if not briefing:
        raise HTTPException(404, "no data yet")
    return {"zones": briefing.airspace_zones}


@app.post("/api/v1/run", response_model=IntelBriefing)
async def trigger_run():
    briefing = await orch.run_pipeline()
    await store.save(briefing)
    return briefing


@app.get("/api/v1/history")
async def get_history(limit: int = 20):
    return {"runs": await store.get_history(limit)}


@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.active_model, "provider": settings.llm_provider}
