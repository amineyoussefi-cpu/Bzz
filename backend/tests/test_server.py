"""HTTP API and WebSocket feed tests (need the web dependencies: pip install -r backend/requirements.txt)."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # fakes.py

try:
    from fastapi.testclient import TestClient

    from bzz.server import create_app
except ImportError:  # web dependencies not installed: the stdlib-only tests still run
    TestClient = None


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class ServerTest(unittest.TestCase):
    def setUp(self):
        from fakes import FakeProvider

        self.client = TestClient(create_app(provider=FakeProvider(default=None)))  # never the real model
        self.client.__enter__()  # runs the lifespan: starts Godot and the event poller

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_dashboard_and_catalog(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn("text/html", self.client.get("/").headers["content-type"])
        cat = self.client.get("/api/catalog").json()
        self.assertIn("honey_bee", [s["name"] for s in cat["species"]])

    def test_crud_and_errors(self):
        c = self.client
        r = c.post("/api/habitats", json={"type": "hive_box", "x": 10, "y": 10})
        self.assertEqual(r.status_code, 201)
        hab = r.json()["id"]
        r = c.post("/api/bees", json={"species": "bumblebee", "x": 20, "y": 20, "personality": {"preset": "curieuse"}})
        self.assertEqual(r.status_code, 201)
        bee = r.json()["id"]
        self.assertEqual([e["id"] for e in c.get("/api/entities").json()], [hab, bee])
        self.assertEqual(c.get(f"/api/entities/{bee}").json()["personality"]["curiosity"], 0.9)

        r = c.post("/api/bees", json={"species": "wasp", "x": 1, "y": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("accepted: honey_bee", r.json()["error"])
        self.assertEqual(c.post("/api/habitats", json={"type": "hive_box", "x": 1}).status_code, 400)
        self.assertEqual(c.post("/api/habitats", json=[1, 2]).status_code, 400)
        self.assertEqual(c.get("/api/entities/nope").status_code, 404)

        self.assertEqual(c.delete(f"/api/entities/{hab}").json()["kind"], "habitat")
        self.assertEqual(c.delete(f"/api/entities/{hab}").status_code, 404)
        self.assertEqual(c.post("/api/world/clear").json(), {"removed": 1})
        r = c.post("/api/swarms", json={"x": 50, "y": 50, "population": 8000, "name": "A"})
        self.assertEqual((r.status_code, r.json()["kind"], r.json()["state"]), (201, "swarm", "cluster"))
        r = c.post("/api/bees", json={"species": "honey_bee", "x": 1, "y": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("add_swarm", r.json()["error"])

    def test_decisions_flow_to_the_feed_when_running(self):
        c = self.client
        c.post("/api/habitats", json={"type": "tree_cavity", "x": 5, "y": 5})
        bee = c.post("/api/bees", json={"species": "bumblebee", "x": 6, "y": 6}).json()["id"]
        self.assertEqual(c.get("/api/decision/status").json()["provider"], "fake")
        c.post("/api/simulation/resume")
        with c.websocket_connect("/ws") as ws:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                snap = ws.receive_json()
                if snap["decision_events"]:
                    break
        ev = snap["decision_events"][0]
        self.assertEqual((ev["type"], ev["data"]["bee_id"], ev["data"]["source"]), ("decision", bee, "fake"))
        self.assertEqual(snap["kpi"]["decisions"]["refused"], 1)  # FakeProvider(default=None) always refuses
        self.assertIsNotNone(snap["kpi"]["decisions"]["agreement_rate"])

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
            c.post("/api/bees", json={"species": "mining_bee", "x": 6, "y": 6,
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
            self.assertEqual(k["bees_by_species"]["mining_bee"], 1)
            self.assertEqual(k["trait_distribution"]["curiosity"], [0, 0, 0, 0, 1])
            self.assertEqual((k["bees_settled"], k["bees_homeless"]), (0, 1))
            self.assertEqual(k["occupancy"][0]["rate"], 0)
            self.assertEqual([e["type"] for e in snap["world_events"]], ["entity_added", "entity_added"])
            self.assertEqual(snap["decision_events"], [])
            self.assertEqual(k["decisions"]["count"], 0)  # paused: no decision
            self.assertEqual(snap["decision_service"]["provider"], "fake")
            self.assertTrue(k["decisions"]["service"]["available"])


class KpiMovementTest(unittest.TestCase):
    def test_movement_and_states(self):
        from bzz import kpi

        catalog = {"traits": [{"name": "boldness"}], "species": [{"name": "mining_bee"}, {"name": "honey_bee"}],
                   "habitat_types": [{"name": "bare_soil"}]}
        state = {"tick": 400, "ticks_per_second": 60, "paused": False, "speed": 1, "day_ticks": 100}
        p = {"boldness": 0.5}
        entities = [
            {"id": "bee-1", "kind": "bee", "species": "mining_bee", "personality": p, "home_id": None, "state": "flying"},
            {"id": "bee-2", "kind": "bee", "species": "mining_bee", "personality": p, "home_id": None, "state": "waiting"},
            {"id": "swarm-3", "kind": "swarm", "species": "honey_bee", "name": "", "personality": p, "home_id": None,
             "state": "cluster", "population": 9000, "days_left": 1.25, "waiting": False},
        ]
        events = [
            {"type": "arrived", "data": {"flight_ticks": 25, "found_after_days": 1.0}},
            {"type": "arrived", "data": {"flight_ticks": 75, "found_after_days": 2.0}},
            {"type": "arrival_failed", "data": {"flight_ticks": 10, "reason": "full"}},
            {"type": "swarm_exposed", "data": {}},
        ]
        k = kpi.compute(state, entities, events, catalog)
        self.assertEqual(k["bees_by_state"], {"searching": 0, "waiting": 1, "flying": 1, "settled": 0})
        self.assertEqual(k["swarms_by_state"]["cluster"], 1)
        self.assertEqual(k["swarms"][0]["days_left"], 1.25)
        m = k["movement"]
        self.assertEqual((m["arrivals"], m["arrival_failures"], m["swarms_exposed"]), (2, 1, 1))
        self.assertEqual((m["avg_days_to_habitat"], m["avg_flight_hours"]), (1.5, 12.0))  # 50 ticks = half a day
        self.assertEqual(m["failures_by_reason"], {"full": 1, "removed": 0})


class KpiDecisionFormatTest(unittest.TestCase):
    """The decision KPIs already understand the documented event format, though nothing emits it yet."""

    def test_decision_aggregation(self):
        from bzz import kpi

        catalog = {"traits": [{"name": "boldness"}], "species": [{"name": "honey_bee"}],
                   "habitat_types": [{"name": "tree_cavity"}]}
        state = {"tick": 120, "ticks_per_second": 60, "paused": False, "speed": 1, "day_ticks": 100}
        bees = [{"id": "bee-1", "kind": "bee", "species": "honey_bee", "personality": {"boldness": 0.9}, "home_id": "hab-2",
                 "state": "settled"}]
        ev = lambda outcome, chosen, score: {"seq": 1, "tick": 10, "type": "decision", "data": {
            "bee_id": "bee-1", "evaluated": [{"habitat_id": "hab-2", "score": score, "breakdown": {}}],
            "chosen_habitat_id": chosen, "outcome": outcome, "reason": "", "source": "test", "result": "none",
            "agreement": outcome == "chosen"}}
        k = kpi.compute(state, bees, [ev("chosen", "hab-2", 0.8), ev("refused", None, 0.2)], catalog)
        self.assertEqual(k["sim"]["seconds"], 2)
        self.assertEqual((k["sim"]["day"], k["sim"]["hour"]), (2, 4.8))  # tick 120 with 100-tick days
        d = k["decisions"]
        self.assertEqual((d["count"], d["chosen"], d["refused"], d["avg_chosen_score"]), (2, 1, 1, 0.8))
        self.assertEqual(d["by_species"]["honey_bee"], {"chosen": 1, "refused": 1})
        self.assertEqual(d["by_trait"]["boldness"][4], {"chosen": 1, "refused": 1})
        self.assertEqual(d["agreement_rate"], 0.5)
        self.assertEqual(d["agreement_by_species"]["honey_bee"], {"agree": 1, "total": 2, "rate": 0.5})


if __name__ == "__main__":
    unittest.main()
