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
        self.assertIn("honey_bee", [s["name"] for s in cat["species"]])

    def test_crud_and_errors(self):
        c = self.client
        r = c.post("/api/habitats", json={"type": "hive_box", "x": 10, "y": 10})
        self.assertEqual(r.status_code, 201)
        hab = r.json()["id"]
        r = c.post("/api/bees", json={"species": "honey_bee", "x": 20, "y": 20, "personality": {"preset": "curieuse"}})
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
            self.assertEqual(k["decisions"]["count"], 0)
            self.assertIsNone(k["decisions"]["mechanism"])


class KpiDecisionFormatTest(unittest.TestCase):
    """The decision KPIs already understand the documented event format, though nothing emits it yet."""

    def test_decision_aggregation(self):
        from bzz import kpi

        catalog = {"traits": [{"name": "boldness"}], "species": [{"name": "honey_bee"}],
                   "habitat_types": [{"name": "tree_cavity"}]}
        state = {"tick": 120, "ticks_per_second": 60, "paused": False, "speed": 1}
        bees = [{"id": "bee-1", "kind": "bee", "species": "honey_bee", "personality": {"boldness": 0.9}, "home_id": "hab-2"}]
        ev = lambda outcome, chosen, score: {"seq": 1, "tick": 10, "type": "decision", "data": {
            "bee_id": "bee-1", "evaluated": [{"habitat_id": "hab-2", "score": score, "breakdown": {}}],
            "chosen_habitat_id": chosen, "outcome": outcome, "reason": "", "source": "test", "result": "none"}}
        k = kpi.compute(state, bees, [ev("chosen", "hab-2", 0.8), ev("refused", None, 0.2)], catalog)
        self.assertEqual(k["sim"]["seconds"], 2)
        d = k["decisions"]
        self.assertEqual((d["count"], d["chosen"], d["refused"], d["avg_chosen_score"]), (2, 1, 1, 0.8))
        self.assertEqual(d["by_species"]["honey_bee"], {"chosen": 1, "refused": 1})
        self.assertEqual(d["by_trait"]["boldness"][4], {"chosen": 1, "refused": 1})


if __name__ == "__main__":
    unittest.main()
