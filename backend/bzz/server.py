"""HTTP API + WebSocket feed for the dashboard: python -m bzz.server

The dashboard is a client of this backend only; every action goes through GodotEngine (validation + Godot).
Godot's events are pulled by polling `get_events` with a cursor (see docs/api.md for why), then pushed to
every WebSocket client together with the state, entities and KPIs.

Decisions: a DecisionLoop asks the local OpenJev service (DECISION_SERVICE_URL) for every searching bee or clustered swarm while the
simulation runs, compares with the reference logic, and has Godot validate and apply the result.

Environment: BZZ_HTTP_HOST (default 127.0.0.1), DASHBOARD_PORT (default 8000), DASHBOARD_UPDATE_INTERVAL (seconds
between two snapshots, default 0.25), the GODOT_* and simulation variables (engine.py), and
DECISION_SERVICE_URL (default http://127.0.0.1:8009), DECISION_INTERVAL_TICKS (120), DECISION_CONCURRENCY (2),
DECISION_MAX_CANDIDATES (12), DECISION_TIMEOUT (30 s).
"""

import asyncio
import os
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from . import kpi
from .decision import DecisionLoop, DecisionProvider, OpenJevProvider
from .engine import CommandRejected, GodotEngine, GodotError

STATIC_DIR = Path(__file__).parent / "static"
POLL_INTERVAL = float(os.environ.get("DASHBOARD_UPDATE_INTERVAL") or 0.25)  # seconds between two polls/snapshots
FEED_SIZE = 200       # events kept for clients that connect later
KPI_EVENTS = 20000  # decision/movement events kept for the KPIs (shortcut: in memory, reset on backend restart)
KPI_EVENT_TYPES = {"decision", "arrived", "arrival_failed", "swarm_exposed"}


class Hub:
    """Polls Godot, keeps recent feeds, and pushes snapshots to the WebSocket clients."""

    def __init__(self, engine: GodotEngine, decisions: DecisionLoop):
        self.engine = engine
        self.decisions = decisions
        self.clients: set[WebSocket] = set()
        self.cursor = 0
        self.world_events: deque = deque(maxlen=FEED_SIZE)
        self.decision_events: deque = deque(maxlen=FEED_SIZE)
        self.kpi_events: deque = deque(maxlen=KPI_EVENTS)
        self.events_lost = False
        self.snapshot: dict | None = None
        self.generation = 0  # engine connection seen last; a new one means a new Godot, hence a new world

    def godot_status(self, state: dict | None = None) -> dict:
        e = self.engine
        return {"connected": e.connected, "display": state.get("display") if state else None,
                "mode": "remote" if e.remote else "local",
                "address": f"{e.host}:{e.port}" if e.remote else "spawned by the backend"}

    def poll(self) -> list[dict]:
        """Fetch new events and rebuild the snapshot; returns the new events (blocking, run in a thread).
        While Godot is unreachable (window closed, not launched yet), it retries the connection and publishes a
        "not connected" snapshot instead."""
        if not self.engine.connected and not self.engine.try_connect():
            self.snapshot = {"type": "snapshot", "godot": self.godot_status(), "state": None, "entities": [],
                             "decision_service": self.decisions.status(), "kpi": None,
                             "world_events": list(self.world_events), "decision_events": list(self.decision_events),
                             "events_lost": self.events_lost}
            return []
        if self.engine.generation != self.generation:  # (re)connected to a fresh Godot: start a new log
            self.generation = self.engine.generation
            self.cursor = 0
            self.events_lost = False
            for q in (self.world_events, self.decision_events, self.kpi_events):
                q.clear()
        res = self.engine.send("get_events", since=self.cursor)
        self.cursor = res["last_seq"]
        self.events_lost |= res["lost"]
        for ev in res["events"]:
            (self.decision_events if ev["type"] == "decision" else self.world_events).append(ev)
            if ev["type"] in KPI_EVENT_TYPES:
                self.kpi_events.append(ev)
        state = self.engine.send("get_state")
        entities = self.engine.send("list_entities")
        service = self.decisions.status()
        self.snapshot = {
            "type": "snapshot",
            "godot": self.godot_status(state),
            "state": state,
            "entities": entities,
            "decision_service": service,
            "kpi": kpi.compute(state, entities, list(self.kpi_events), self.engine.catalog, service),
            "world_events": list(self.world_events),
            "decision_events": list(self.decision_events),
            "events_lost": self.events_lost,
        }
        return res["events"]

    async def run(self) -> None:
        last_key = None
        while True:
            try:
                new = await asyncio.to_thread(self.poll)
            except (GodotError, OSError):  # connection lost mid-poll: the next poll publishes "not connected"
                await asyncio.sleep(POLL_INTERVAL)
                continue
            snap = self.snapshot
            key = (snap["godot"]["connected"], snap["state"] and snap["state"]["tick"],
                   snap["decision_service"].get("available"))
            if new or key != last_key:
                last_key = key
                await self.broadcast(snap)
            await asyncio.sleep(POLL_INTERVAL)

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:  # client gone mid-send
                self.clients.discard(ws)


def decision_loop_from_env(engine: GodotEngine, provider: DecisionProvider | None = None) -> DecisionLoop:
    env = os.environ.get
    provider = provider or OpenJevProvider(env("DECISION_SERVICE_URL") or "http://127.0.0.1:8009",
                                           timeout=float(env("DECISION_TIMEOUT") or 30))
    return DecisionLoop(engine, provider, interval_ticks=int(env("DECISION_INTERVAL_TICKS") or 120),
                        concurrency=int(env("DECISION_CONCURRENCY") or 2),
                        max_candidates=int(env("DECISION_MAX_CANDIDATES") or 12))


def create_app(engine: GodotEngine | None = None, provider: DecisionProvider | None = None) -> FastAPI:
    """`provider` replaces the OpenJev provider (tests use a fake one)."""
    engine = engine or GodotEngine()
    decisions = decision_loop_from_env(engine, provider)
    hub = Hub(engine, decisions)

    @asynccontextmanager
    async def lifespan(_app):
        if engine.remote:
            await asyncio.to_thread(engine.try_connect)  # Godot may start later: polling picks it up
        else:
            await asyncio.to_thread(engine.start)
        await asyncio.to_thread(decisions.check_service)
        await asyncio.to_thread(hub.poll)  # first snapshot before accepting clients
        tasks = [asyncio.create_task(hub.run()), asyncio.create_task(decisions.run())]
        yield
        for t in tasks:
            t.cancel()
        await asyncio.to_thread(engine.stop)

    app = FastAPI(title="Bzz backend", lifespan=lifespan)
    app.state.engine, app.state.hub, app.state.decisions = engine, hub, decisions

    def call(cmd: str, **args):
        try:
            return engine.send(cmd, **args)
        except ValueError as e:  # refused by the Python validation
            return JSONResponse({"error": str(e)}, status_code=400)
        except CommandRejected as e:  # refused by Godot
            return JSONResponse({"error": str(e)}, status_code=404 if str(e).startswith("unknown entity") else 400)
        except (GodotError, OSError) as e:
            return JSONResponse({"error": f"simulation non connectée : {e}"}, status_code=503)

    def body_call(cmd: str, payload):
        if not isinstance(payload, dict):
            return JSONResponse({"error": "request body must be a JSON object"}, status_code=400)
        return call(cmd, **payload)

    # sync handlers run in FastAPI's thread pool; the engine lock serialises them with the poller
    @app.get("/api/catalog")
    def catalog():
        return call("get_catalog")

    @app.get("/api/state")
    def state():
        return call("get_state")

    @app.get("/api/entities")
    def list_entities():
        return call("list_entities")

    @app.get("/api/entities/{entity_id}")
    def get_entity(entity_id: str):
        return call("get_entity", id=entity_id)

    @app.delete("/api/entities/{entity_id}")
    def remove_entity(entity_id: str):
        return call("remove_entity", id=entity_id)

    @app.post("/api/habitats", status_code=201)
    def add_habitat(payload=Body(...)):
        return body_call("add_habitat", payload)

    @app.post("/api/bees", status_code=201)
    def add_bee(payload=Body(...)):
        return body_call("add_bee", payload)

    @app.post("/api/swarms", status_code=201)
    def add_swarm(payload=Body(...)):
        return body_call("add_swarm", payload)

    @app.post("/api/world/clear")
    def clear_world():
        return call("clear_world")

    @app.post("/api/simulation/pause")
    def pause():
        return call("pause")

    @app.post("/api/simulation/resume")
    def resume():
        return call("resume")

    @app.post("/api/simulation/speed")
    def set_speed(payload=Body(...)):
        return body_call("set_speed", payload)

    @app.get("/api/events")
    def events(since: int = 0):
        return call("get_events", since=since)

    @app.get("/api/godot/status")
    def godot_status():
        return hub.snapshot["godot"] if hub.snapshot else hub.godot_status()

    @app.get("/api/decision/status")
    def decision_status():
        return decisions.status()

    @app.get("/api/kpi")
    def get_kpi():
        if not hub.snapshot or hub.snapshot["kpi"] is None:
            return JSONResponse({"error": "simulation non connectée"}, status_code=503)
        return hub.snapshot["kpi"]

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        hub.clients.add(websocket)
        if hub.snapshot:
            await websocket.send_json(hub.snapshot)
        try:
            while True:
                await websocket.receive_text()  # the feed is one-way; just wait for the client to leave
        except WebSocketDisconnect:
            hub.clients.discard(websocket)

    @app.get("/")
    def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host=os.environ.get("BZZ_HTTP_HOST", "127.0.0.1"),
                port=int(os.environ.get("DASHBOARD_PORT") or 8000))


if __name__ == "__main__":
    main()
