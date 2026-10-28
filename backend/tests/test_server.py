"""HTTP API and WebSocket feed tests (need the web dependencies: pip install -r backend/requirements.txt)."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient

    from bzz.server import create_app
except ImportError:  # web dependencies not installed: the stdlib-only tests still run
    TestClient = None


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class ServerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())
        self.client.__enter__()  # runs the lifespan: starts Godot and the event poller

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_dashboard_and_catalog(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn("text/html", self.client.get("/").headers["content-type"])
        cat = self.client.get("/api/catalog").json()
        self.assertNotIn("species", cat)

    def test_crud_and_errors(self):
        c = self.client
        r = c.post("/api/habitats", json={"type": "hive_box", "x": 10, "y": 10})
        self.assertEqual(r.status_code, 201)
        hab = r.json()["id"]
        r = c.post("/api/bees", json={"x": 20, "y": 20, "personality": {"preset": "curieuse"}})
        self.assertEqual(r.status_code, 201)
        bee = r.json()["id"]
        self.assertEqual([e["id"] for e in c.get("/api/entities").json()], [hab, bee])
        self.assertEqual(c.get(f"/api/entities/{bee}").json()["personality"]["curiosity"], 0.9)

        r = c.post("/api/bees", json={"x": 1, "y": 9999})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(c.post("/api/habitats", json={"type": "hive_box", "x": 1}).status_code, 400)
        self.assertEqual(c.post("/api/habitats", json=[1, 2]).status_code, 400)
        self.assertEqual(c.get("/api/entities/nope").status_code, 404)

        self.assertEqual(c.delete(f"/api/entities/{hab}").json()["kind"], "habitat")
        self.assertEqual(c.delete(f"/api/entities/{hab}").status_code, 404)
        self.assertEqual(c.post("/api/world/clear").json(), {"removed": 1})

    def test_simulation_control_and_events(self):
        c = self.client
        self.assertFalse(c.post("/api/simulation/resume").json()["paused"])
        self.assertEqual(c.post("/api/simulation/speed", json={"speed": 4}).json(), {"speed": 4})
        self.assertEqual(c.post("/api/simulation/speed", json={"speed": 40}).status_code, 400)
        self.assertTrue(c.post("/api/simulation/pause").json()["paused"])
        types = [e["type"] for e in c.get("/api/events?since=0").json()["events"]]
        self.assertEqual(types, ["resumed", "speed_changed", "paused"])
        self.assertEqual(c.get("/api/events?since=-1").status_code, 400)

    def test_websocket_pushes_snapshots_with_kpi(self):
        c = self.client
        with c.websocket_connect("/ws") as ws:
            first = ws.receive_json()
            self.assertEqual(first["type"], "snapshot")
            self.assertEqual(first["entities"], [])
            c.post("/api/habitats", json={"type": "bare_soil", "x": 5, "y": 5})
            c.post("/api/bees", json={"x": 6, "y": 6,
                                      "personality": {"traits": {"pickiness": 0.1, "boldness": 0.3,
                                                                 "sociability": 0.5, "curiosity": 0.95}}})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                snap = ws.receive_json()
                # entities and events are fetched by separate requests: one may lag the other by a poll
                if len(snap["entities"]) == 2 and len(snap["world_events"]) == 2:
                    break
            k = snap["kpi"]
            self.assertEqual(k["habitats_by_type"]["bare_soil"], 1)
            self.assertNotIn("bees_by_species", k)
            self.assertEqual(k["trait_distribution"]["curiosity"], [0, 0, 0, 0, 1])
            self.assertEqual((k["bees_settled"], k["bees_homeless"]), (0, 1))
            self.assertEqual(k["occupancy"][0]["rate"], 0)
            self.assertEqual([e["type"] for e in snap["world_events"]], ["entity_added", "entity_added"])
            self.assertEqual(snap["decision_events"], [])
            self.assertEqual(k["decisions"]["count"], 0)
            self.assertEqual(k["decisions"]["mechanism"], "llm")


class StubOllama:
    """Stands in for OllamaLLM; `down` simulates an unreachable server."""

    url, model, down = "http://ollama.test", "qwen2.5:0.5b", False

    def installed(self):
        if self.down:
            raise OSError("connection refused")
        return [{"name": "qwen2.5:0.5b", "size": 1}, {"name": "llama3.2:1b", "size": 2}]

    def pull(self, name):
        if name == "nope:1b":
            raise ValueError("file does not exist")


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class ModelsApiTest(unittest.TestCase):
    """Model routes need no Godot: the client is not entered, so the lifespan (Godot start) does not run."""

    def setUp(self):
        self.llm = StubOllama()
        self.client = TestClient(create_app(llm=self.llm))

    def test_list_and_switch_model(self):
        c = self.client
        m = c.get("/api/models").json()
        self.assertEqual((m["available"], m["current"], len(m["installed"])), (True, "qwen2.5:0.5b", 2))
        self.assertEqual(c.put("/api/models/current", json={"model": "llama3.2:1b"}).json(), {"current": "llama3.2:1b"})
        self.assertEqual(self.llm.model, "llama3.2:1b")
        self.assertEqual(c.put("/api/models/current", json={"model": "gemma3:1b"}).status_code, 400)  # not installed
        self.assertEqual(c.put("/api/models/current", json={"model": "bad name; rm"}).status_code, 400)
        self.assertEqual(c.put("/api/models/current", json=["x"]).status_code, 400)

    def test_pull(self):
        c = self.client
        self.assertEqual(c.post("/api/models/pull", json={"model": "gemma3:1b"}).json(), {"pulled": "gemma3:1b"})
        r = c.post("/api/models/pull", json={"model": "nope:1b"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("does not exist", r.json()["error"])

    def test_ollama_down(self):
        self.llm.down = True
        m = self.client.get("/api/models").json()
        self.assertEqual((m["available"], m["installed"]), (False, []))
        self.assertEqual(self.client.put("/api/models/current", json={"model": "qwen2.5:0.5b"}).status_code, 503)


class FakeEngine:
    def __init__(self, reject=False):
        self.sent, self.reject = [], reject

    def send(self, cmd, **args):
        from bzz.engine import CommandRejected
        self.sent.append((cmd, args))
        if cmd == "get_state":
            return {"paused": False}
        if self.reject:
            raise CommandRejected("bee bee-1 is not waiting for evaluate_site")


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class HubBrainTest(unittest.TestCase):
    """The hub turns a decision_needed event into one brain call and an answer_decision command."""

    def setUp(self):
        from bzz.brain import Brain
        from bzz.server import Hub
        self.brain = Brain(lambda messages, schema, seed: '{"score": 4}')
        self.Hub = Hub

    def need(self):
        return {"bee_id": "bee-1", "kind": "evaluate_site", "personality": {"pickiness": .5, "boldness": .5,
                "sociability": .5, "curiosity": .5}, "situation": {"habitat": {"id": "hab-1", "description": {"a": "large cavity"}}}}

    def test_answer_sent_back(self):
        engine = FakeEngine()
        hub = self.Hub(engine, self.brain)
        self.assertFalse(hub.answer_next())  # nothing pending
        hub.pending.append(self.need())
        self.assertTrue(hub.answer_next())
        self.assertEqual(engine.sent, [("answer_decision", {"bee_id": "bee-1", "kind": "evaluate_site", "answer": {"score": 4}})])
        self.assertEqual(hub.answered, 1)

    def test_step_mode_holds_each_question_until_released(self):
        engine = FakeEngine()
        hub = self.Hub(engine, self.brain)
        hub.step_mode = True
        hub.pending.append({**self.need(), "tick": 7})
        self.assertFalse(hub.answer_next())  # held: the world is paused, nothing is asked
        self.assertIn(("pause", {}), engine.sent)
        self.assertEqual(hub.next_question()["kind"], "evaluate_site")
        self.assertIn("large cavity", hub.next_question()["messages"][1]["content"])
        hub.released = 1
        self.assertTrue(hub.answer_next())
        self.assertEqual(engine.sent[-2][0], "answer_decision")
        self.assertEqual(engine.sent[-1], ("resume", {}))  # bees act on the answer until the next question
        self.assertEqual(self.brain.calls["bee-1"][-1]["tick"], 7)

    def test_stale_question_is_dropped(self):
        hub = self.Hub(FakeEngine(reject=True), self.brain)
        hub.pending.append(self.need())
        self.assertTrue(hub.answer_next())  # refused by Godot, no exception
        self.assertEqual(len(hub.pending), 0)


class KpiDecisionFormatTest(unittest.TestCase):
    """The decision KPIs already understand the documented event format, though nothing emits it yet."""

    def test_decision_aggregation(self):
        from bzz import kpi

        catalog = {"traits": [{"name": "boldness"}], "habitat_types": [{"name": "tree_cavity"}]}
        state = {"tick": 120, "ticks_per_second": 60, "paused": False, "speed": 1}
        bees = [{"id": "bee-1", "kind": "bee", "personality": {"boldness": 0.9}, "home_id": "hab-2"}]
        ev = lambda outcome, chosen, score: {"seq": 1, "tick": 10, "type": "decision", "data": {
            "bee_id": "bee-1", "evaluated": [{"habitat_id": "hab-2", "score": score, "breakdown": {}}],
            "chosen_habitat_id": chosen, "outcome": outcome, "reason": "", "source": "test", "result": "none"}}
        k = kpi.compute(state, bees, [ev("chosen", "hab-2", 0.8), ev("refused", None, 0.2)], catalog)
        self.assertEqual(k["sim"]["seconds"], 2)
        d = k["decisions"]
        self.assertEqual((d["count"], d["chosen"], d["refused"], d["avg_chosen_score"]), (2, 1, 1, 0.8))
        self.assertNotIn("by_species", d)
        self.assertEqual(d["by_trait"]["boldness"][4], {"chosen": 1, "refused": 1})


if __name__ == "__main__":
    unittest.main()
