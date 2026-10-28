"""HTTP API + WebSocket feed for the dashboard: python -m bzz.server

The dashboard is a client of this backend only; every action goes through GodotEngine (validation + Godot).
Godot's events are pulled by polling `get_events` with a cursor (see docs/api.md for why), then pushed to
every WebSocket client together with the state, entities and KPIs.

Environment: BZZ_HTTP_HOST (default 127.0.0.1), DASHBOARD_PORT (default 8000), plus the GODOT_* variables
and OLLAMA_URL / BZZ_MODEL for the bee brain's LLM (see brain.py).
"""

import asyncio
import os
import re
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.error import HTTPError

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from . import kpi
from .brain import Brain, OllamaLLM
from .engine import CommandRejected, GodotEngine, GodotError

STATIC_DIR = Path(__file__).parent / "static"
POLL_INTERVAL = 0.15  # seconds between two event polls (the map animates between two snapshots)
FEED_SIZE = 200       # events kept for clients that connect later
MODEL_NAME = re.compile(r"[A-Za-z0-9][\w.\-/:]{0,99}")  # Ollama names, e.g. qwen2.5:0.5b, hf.co/user/model


class Hub:
    """Polls Godot, keeps recent feeds, and pushes snapshots to the WebSocket clients.

    It is also the bees' link to the brain: "decision_needed" events are queued, answered one at a time by
    the LLM (one call each) and sent back with answer_decision.
    """

    def __init__(self, engine: GodotEngine, brain: Brain | None = None):
        self.engine = engine
        self.brain = brain
        self.pending: deque = deque()  # decision_needed data (+ tick) waiting for the brain
        self.answered = 0
        # step mode: the world pauses at each question and waits for release() before asking the LLM
        self.step_mode = False
        self.released = 0
        self.clients: set[WebSocket] = set()
        self.cursor = 0
        self.world_events: deque = deque(maxlen=FEED_SIZE)
        self.decision_events: deque = deque(maxlen=FEED_SIZE)
        self.events_lost = False
        self.snapshot: dict | None = None

    def poll(self) -> list[dict]:
        """Fetch new events and rebuild the snapshot; returns the new events (blocking, run in a thread)."""
        res = self.engine.send("get_events", since=self.cursor)
        self.cursor = res["last_seq"]
        self.events_lost |= res["lost"]
        for ev in res["events"]:
            if ev["type"] == "decision_needed":
                self.pending.append({**ev["data"], "tick": ev["tick"]})
            else:
                (self.decision_events if ev["type"] == "decision" else self.world_events).append(ev)
        state = self.engine.send("get_state")
        entities = self.engine.send("list_entities")
        self.snapshot = {
            "type": "snapshot",
            "state": state,
            "entities": entities,
            "kpi": kpi.compute(state, entities, list(self.decision_events), self.engine.catalog),
            "world_events": list(self.world_events),
            "decision_events": list(self.decision_events),
            "events_lost": self.events_lost,
            "brain": {"model": getattr(self.brain.llm, "model", None) if self.brain else None, "answered": self.answered,
                      "fallbacks": self.brain.failures if self.brain else 0, "pending": len(self.pending),
                      "step_mode": self.step_mode, "next": self.next_question()},
        }
        return res["events"]

    def next_question(self) -> dict | None:
        """In step mode, the question about to be sent, with its exact prompt (shown by the dashboard)."""
        if not (self.step_mode and self.pending and self.brain):
            return None
        d = self.pending[0]
        return {"bee_id": d["bee_id"], "kind": d["kind"], "tick": d["tick"],
                "messages": self.brain.prompt({"id": d["bee_id"], "personality": d["personality"]}, d["kind"], d["situation"])}

    def answer_next(self) -> bool:
        """Answers the oldest pending decision (blocking: one LLM call). False when there is nothing to do."""
        if not self.pending or not self.brain:
            return False
        if self.step_mode:
            if not self.released:  # hold the question; freeze the world so nothing runs ahead of it
                if not self.engine.send("get_state")["paused"]:
                    self.engine.send("pause")
                return False
            self.released -= 1
        d = self.pending.popleft()
        answer = self.brain.decide({"id": d["bee_id"], "personality": d["personality"]}, d["kind"], d["situation"],
                                   d.get("tick"))
        try:
            self.engine.send("answer_decision", bee_id=d["bee_id"], kind=d["kind"], answer=answer)
        except CommandRejected:
            pass  # the bee moved on meanwhile (swarm left, bee removed): its question is void
        self.answered += 1
        if self.step_mode and not self.pending:
            self.engine.send("resume")  # let the bees act on the answer until the next question
        return True

    async def think(self) -> None:
        # one decision at a time: a small local model answers fastest without parallel requests
        while True:
            try:
                busy = await asyncio.to_thread(self.answer_next)
            except (GodotError, OSError):
                busy = False
            if not busy:
                await asyncio.sleep(0.05)

    async def run(self) -> None:
        last_tick = None
        while True:
            try:
                new = await asyncio.to_thread(self.poll)
                if new or self.snapshot["state"]["tick"] != last_tick:
                    last_tick = self.snapshot["state"]["tick"]
                    await self.broadcast(self.snapshot)
            except (GodotError, OSError):
                pass  # Godot restarting: keep polling
            await asyncio.sleep(POLL_INTERVAL)

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:  # client gone mid-send
                self.clients.discard(ws)


def create_app(engine: GodotEngine | None = None, llm: OllamaLLM | None = None) -> FastAPI:
    engine = engine or GodotEngine()
    llm = llm or OllamaLLM()
    hub = Hub(engine, Brain(llm))

    @asynccontextmanager
    async def lifespan(_app):
        await asyncio.to_thread(engine.start)
        await asyncio.to_thread(hub.poll)  # first snapshot before accepting clients
        tasks = [asyncio.create_task(hub.run()), asyncio.create_task(hub.think())]
        yield
        for task in tasks:
            task.cancel()
        await asyncio.to_thread(engine.stop)

    app = FastAPI(title="Bzz backend", lifespan=lifespan)
    app.state.engine, app.state.hub, app.state.llm = engine, hub, llm

    def call(cmd: str, **args):
        try:
            return engine.send(cmd, **args)
        except ValueError as e:  # refused by the Python validation
            return JSONResponse({"error": str(e)}, status_code=400)
        except CommandRejected as e:  # refused by Godot
            return JSONResponse({"error": str(e)}, status_code=404 if str(e).startswith("unknown entity") else 400)
        except (GodotError, OSError) as e:
            return JSONResponse({"error": f"simulation unavailable: {e}"}, status_code=503)

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

    @app.put("/api/entities/{entity_id}/position")
    def move_entity(entity_id: str, payload=Body(...)):
        if not isinstance(payload, dict):
            return JSONResponse({"error": "request body must be a JSON object"}, status_code=400)
        return call("move_entity", **{**payload, "id": entity_id})

    @app.put("/api/habitats/{entity_id}/features")
    def update_habitat(entity_id: str, payload=Body(...)):
        if not isinstance(payload, dict):
            return JSONResponse({"error": "request body must be a JSON object of features"}, status_code=400)
        return call("update_habitat", id=entity_id, features=payload)

    @app.post("/api/habitats", status_code=201)
    def add_habitat(payload=Body(...)):
        return body_call("add_habitat", payload)

    @app.post("/api/bees", status_code=201)
    def add_bee(payload=Body(...)):
        return body_call("add_bee", payload)

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

    @app.get("/api/kpi")
    def get_kpi():
        return hub.snapshot["kpi"] if hub.snapshot else JSONResponse({"error": "not ready"}, status_code=503)

    # --- what each bee thinks (brain log) and step mode -------------------------------------
    @app.get("/api/bees/{bee_id}/brain")
    def bee_brain(bee_id: str):
        brain = hub.brain
        return {"model": brain.models.get(bee_id), "notebook": list(brain.notebooks.get(bee_id, [])),
                "calls": list(brain.calls.get(bee_id, []))}

    @app.post("/api/step-mode")
    def set_step_mode(payload=Body(...)):
        if not isinstance(payload, dict) or not isinstance(payload.get("on"), bool):
            return JSONResponse({"error": 'body must be {"on": true|false}'}, status_code=400)
        hub.step_mode, hub.released = payload["on"], 0
        return {"step_mode": hub.step_mode}

    @app.post("/api/step-mode/next")
    def step_next():
        if not hub.step_mode:
            return JSONResponse({"error": "step mode is off"}, status_code=400)
        if not hub.pending:
            return JSONResponse({"error": "no question is waiting"}, status_code=400)
        hub.released += 1
        return {"released": hub.released}

    # --- LLM models (Ollama) ---------------------------------------------------------
    def model_name(payload):
        name = payload.get("model") if isinstance(payload, dict) else None
        if not isinstance(name, str) or not MODEL_NAME.fullmatch(name):
            return None, JSONResponse({"error": "body must be {\"model\": \"<ollama model name>\"}"}, status_code=400)
        return name, None

    def ollama_down(e: Exception):
        if isinstance(e, (HTTPError, ValueError)):  # Ollama answered with an error (e.g. unknown model): not an outage
            detail = e.read().decode(errors="replace")[:300] if isinstance(e, HTTPError) else str(e)
            return JSONResponse({"error": f"Ollama refused: {detail or e}"}, status_code=400)
        return JSONResponse({"error": f"Ollama unavailable at {llm.url}: {e}"}, status_code=503)

    @app.get("/api/models")
    def models():
        try:
            installed = llm.installed()
        except (OSError, ValueError, KeyError) as e:
            return {"current": llm.model, "url": llm.url, "available": False, "installed": [], "error": str(e)}
        return {"current": llm.model, "url": llm.url, "available": True, "installed": installed}

    def installed_model(payload):
        """(name, None) if the body names an installed model, else (None, error response)."""
        name, err = model_name(payload)
        if err:
            return None, err
        try:
            names = [m["name"] for m in llm.installed()]
        except (OSError, ValueError, KeyError) as e:
            return None, ollama_down(e)
        if name not in names:
            return None, JSONResponse({"error": f"model {name} is not installed; download it first"}, status_code=400)
        return name, None

    @app.put("/api/models/current")
    def set_model(payload=Body(...)):
        name, err = installed_model(payload)
        if err:
            return err
        llm.model = name
        return {"current": name}

    @app.put("/api/bees/{bee_id}/model")
    def set_bee_model(bee_id: str, payload=Body(...)):
        """{"model": name} gives this bee its own model; {"model": null} puts it back on the default."""
        if isinstance(payload, dict) and payload.get("model") is None:
            hub.brain.models.pop(bee_id, None)
            return {"bee_id": bee_id, "model": None}
        name, err = installed_model(payload)
        if err:
            return err
        hub.brain.models[bee_id] = name
        return {"bee_id": bee_id, "model": name}

    @app.post("/api/models/pull")
    def pull_model(payload=Body(...)):
        name, err = model_name(payload)
        if err:
            return err
        try:
            llm.pull(name)
        except (OSError, ValueError, KeyError) as e:
            return ollama_down(e)
        return {"pulled": name}

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
