"""Decision tests: request building, applying/refusing decisions in Godot, pause, unavailable service.
They use FakeProvider (no model). The last class runs against the real OpenJev service only if it is up."""

import asyncio
import json
import os
import sys
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # fakes.py

from bzz import CommandRejected, GodotEngine
from bzz.decision import DecisionLoop, OpenJevProvider
from bzz.decision.prompting import NONE_OPTION, build_request, eligible_candidates, read_answer
from fakes import FakeProvider

SERVICE_URL = os.environ.get("DECISION_SERVICE_URL") or "http://127.0.0.1:8009"


def situation(n_habitats=3, eligible=True):
    habitats = [{"id": f"hab-{i}", "kind": "habitat", "type": "tree_cavity", "x": 10.0 * i, "y": 0.0,
                 "capacity": 1, "occupants": 0, "distance": 100.0 - i, "type_accepted": eligible, "full": False,
                 "eligible": eligible,
                 "features": {"cavity_volume_l": 40.0, "entrance_diameter_mm": 40.0, "entrance_height_m": 5.0,
                              "sun_exposure": 0.4, "humidity": 0.4, "floral_abundance": 0.6, "predator_risk": 0.2,
                              "previously_occupied": False, "capacity": 1}} for i in range(n_habitats)]
    bee = {"id": "bee-9", "kind": "bee", "species": "honey_bee", "name": "", "role": "follower", "x": 0, "y": 0,
           "home_id": None, "accepted_habitat_types": ["tree_cavity", "hive_box"], "acceptance_threshold": 0.7,
           "personality": {"pickiness": 0.8, "boldness": 0.1, "sociability": 0.5, "curiosity": 0.2},
           "preferences": [{"criterion": "cavity_volume_l", "ideal": 40, "tolerance": 35, "weight": 2},
                           {"criterion": "entrance_height_m", "ideal": 5, "tolerance": 5, "weight": 1}]}
    return {"tick": 0, "paused": False, "bee": bee, "habitats": habitats}


class PromptingTest(unittest.TestCase):
    def test_request_describes_bee_rules_and_candidates(self):
        sit = situation()
        req = build_request(sit, eligible_candidates(sit))
        state, q = req["state"], req["questions"]["best"]
        self.assertIn("honey bee", state["bee"])
        self.assertIn("cavity volume (L): ideal 40, tolerance 35, weight 2", state["preferences"])
        self.assertIn("0.70", state["acceptance threshold"])
        self.assertIn("pickiness 0.80 (high)", state["personality"])
        self.assertTrue(any("weighted average" in r for r in state["rules"]))
        self.assertEqual(q["type"], "choice")
        self.assertEqual(list(q["criteria"]), ["hab-2", "hab-1", "hab-0"])  # nearest first
        self.assertIn("cavity volume 40 L (at the ideal)", q["criteria"]["hab-0"])
        accept = req["questions"]["accept"]
        self.assertEqual(accept["type"], "noul")
        self.assertIn("0.70", accept["instructions"])

    def test_answer_combines_best_and_accept(self):
        answers = {"best": {"type": "choice", "choice": "hab-1", "probabilities": {"hab-1": 0.8, "hab-2": 0.2}},
                   "accept": {"type": "noul", "noul": 0.75}}
        self.assertEqual(read_answer(answers), ("hab-1", {"hab-1": 0.6, "hab-2": 0.15, NONE_OPTION: 0.25}, "hab-1"))
        answers["accept"]["noul"] = 0.3
        choice, probs, best = read_answer(answers)
        self.assertEqual((choice, best, probs[NONE_OPTION]), (None, "hab-1", 0.7))

    def test_reference_scores_are_never_sent(self):
        sit = situation()
        sit["habitats"][0]["reference_score"] = 0.123456  # even if present in the input, it must not leak
        text = json.dumps(build_request(sit, eligible_candidates(sit)))
        self.assertNotIn("0.123456", text)
        self.assertNotIn("score", text.lower())

    def test_swarm_request_adds_population_delay_and_distance(self):
        sit = situation()
        sit["bee"].update(kind="swarm", population=9000, days_left=1.5)
        req = build_request(sit, eligible_candidates(sit))
        self.assertIn("9000 workers", req["state"]["bee"])
        self.assertIn("1.5 days", req["state"]["time left"])
        self.assertIn("m from the cluster", req["state"]["candidates"]["hab-0"])
        self.assertIn("time", req["questions"]["accept"]["instructions"])
        self.assertNotIn("time left", build_request(situation(), eligible_candidates(situation()))["state"])

    def test_preselection_keeps_nearest_eligible(self):
        sit = situation(n_habitats=30)
        sit["habitats"][29]["eligible"] = False  # the nearest one is not eligible
        cands = eligible_candidates(sit, max_candidates=12)
        self.assertEqual(len(cands), 12)
        self.assertNotIn("hab-29", [h["id"] for h in cands])
        self.assertEqual(cands[0]["id"], "hab-28")
        self.assertEqual(eligible_candidates(situation(eligible=False)), [])


class DecisionGodotTest(unittest.TestCase):
    def setUp(self):
        # flights take a single tick here: flight timing itself is tested in godot/tests/test_entities.gd
        self.engine = GodotEngine(godot_params={"flight-speed-factor": 1000})
        self.engine.start()
        self.send = self.engine.send
        self.tree = self.send("add_habitat", type="tree_cavity", x=100, y=100)["id"]
        self.box = self.send("add_habitat", type="hive_box", x=300, y=100)["id"]
        self.soil = self.send("add_habitat", type="bare_soil", x=200, y=100)["id"]
        self.bee = self.send("add_bee", species="bumblebee", x=120, y=120, personality={"preset": "équilibrée"})["id"]

    def tearDown(self):
        self.engine.stop()

    def decisions(self):
        return [e["data"] for e in self.send("get_events")["events"] if e["type"] == "decision"]

    def entity(self, id):
        return self.send("get_entity", id=id)

    def wait_for(self, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while not predicate():
            self.assertLess(time.monotonic(), deadline, "condition not reached in time")
            time.sleep(0.02)

    def test_situation_marks_eligible_habitats(self):
        sit = self.send("get_decision_situation", bee_id=self.bee)
        eligible = {h["id"]: h["eligible"] for h in sit["habitats"]}
        self.assertEqual(eligible, {self.tree: True, self.box: True, self.soil: False})
        self.assertEqual(sit["bee"]["accepted_habitat_types"], ["rodent_burrow", "hive_box", "tree_cavity"])
        self.assertEqual(sit["bee"]["state"], "searching")
        self.assertAlmostEqual(sit["bee"]["acceptance_threshold"], 0.55)

    def test_valid_decision_flies_then_settles_and_is_compared(self):
        self.send("resume")
        provider = FakeProvider({self.bee: self.box})
        data = DecisionLoop(self.engine, provider).decide_for(self.bee)
        [ev] = self.decisions()
        self.assertEqual((ev["source"], ev["outcome"], ev["result"], ev["chosen_habitat_id"]),
                         ("fake", "chosen", "flying", self.box))
        self.assertEqual(ev["agreement"], ev["reference"]["choice"] == self.box)
        self.assertEqual(data["agreement"], ev["agreement"])
        self.assertEqual({c["habitat_id"] for c in ev["evaluated"]}, {self.tree, self.box})
        self.assertTrue(all("cavity_volume_l" in c["breakdown"] for c in ev["evaluated"]))
        self.assertIn(self.box, ev["context"]["distances"])
        self.wait_for(lambda: self.entity(self.bee)["home_id"] == self.box)  # settles on arrival
        types = [e["type"] for e in self.send("get_events")["events"]]
        self.assertLess(types.index("flight_started"), types.index("arrived"))
        self.assertEqual(self.entity(self.box)["occupant_ids"], [self.bee])
        self.assertNotIn("score", json.dumps(provider.requests).lower())  # never saw a reference score

    def test_no_choice_leaves_bee_searching(self):
        self.send("resume")
        DecisionLoop(self.engine, FakeProvider({self.bee: None})).decide_for(self.bee)
        self.assertEqual(self.entity(self.bee)["state"], "searching")
        [ev] = self.decisions()
        self.assertEqual((ev["outcome"], ev["result"], ev["chosen_habitat_id"]), ("refused", "none", None))

    def test_godot_rejects_invalid_decisions(self):
        self.send("resume")
        other = self.send("add_bee", species="bumblebee", x=1, y=1)["id"]
        self.send("apply_decision", bee_id=other, habitat_id=self.tree)
        self.wait_for(lambda: self.entity(other)["state"] == "settled")  # tree cavity now full
        cases = [("hab-999", "unknown habitat"), (self.soil, "does not accept"), (self.tree, "is full")]
        for habitat, msg in cases:
            with self.subTest(habitat=habitat):
                with self.assertRaisesRegex(CommandRejected, msg):
                    self.send("apply_decision", bee_id=self.bee, habitat_id=habitat, decision={"source": "test"})
        with self.assertRaisesRegex(CommandRejected, "already lives"):
            self.send("apply_decision", bee_id=other, habitat_id=self.box)
        rejected = [d for d in self.decisions() if d["result"] == "rejected"]
        self.assertEqual(len(rejected), 4)
        self.assertTrue(all(d["outcome"] == "refused" and "rejected by Godot" in d["reason"] for d in rejected))
        self.assertEqual(self.entity(self.bee)["state"], "searching")
        data = DecisionLoop(self.engine, FakeProvider({self.bee: self.soil})).decide_for(self.bee)
        self.assertEqual(data["result"], "rejected")

    def test_no_decision_while_paused(self):
        with self.assertRaisesRegex(CommandRejected, "paused"):
            self.send("apply_decision", bee_id=self.bee, habitat_id=self.tree)
        loop = DecisionLoop(self.engine, FakeProvider())
        self.assertIsNone(loop.decide_for(self.bee))

        async def run_briefly():
            task = asyncio.create_task(loop.run(poll=0.05))
            await asyncio.sleep(1.0)
            task.cancel()

        asyncio.run(run_briefly())
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.entity(self.bee)["state"], "searching")

    def test_loop_decides_for_searching_bees_and_clustered_swarms(self):
        deciders = [self.bee] + [self.send("add_bee", species="mining_bee", x=10 * i, y=10)["id"] for i in range(3)]
        deciders.append(self.send("add_swarm", x=500, y=500, population=10000)["id"])
        waiting = self.send("add_bee", species="mason_bee", x=5, y=5)["id"]  # no stem or dead wood: waiting
        self.assertEqual(self.entity(waiting)["state"], "waiting")
        loop = DecisionLoop(self.engine, FakeProvider(default=None), interval_ticks=10)  # FakeProvider: always none

        async def run_briefly():
            task = asyncio.create_task(loop.run(poll=0.05))
            await asyncio.sleep(1.0)
            task.cancel()

        self.send("resume")
        asyncio.run(run_briefly())
        decided = {d["bee_id"] for d in self.decisions()}
        self.assertEqual(decided, set(deciders))  # the waiting bee is never asked: nothing to choose from
        self.assertTrue(all(d["source"] == "fake" for d in self.decisions()))
        self.assertTrue(all(e["tick"] > 0 for e in self.send("get_events")["events"] if e["type"] == "decision"))

    def test_swarm_decision_is_collective_and_settles_on_arrival(self):
        swarm = self.send("add_swarm", x=100, y=300, population=12000, personality={"preset": "prudente"})["id"]
        self.send("resume")
        provider = FakeProvider({swarm: self.tree})
        data = DecisionLoop(self.engine, provider).decide_for(swarm)
        self.assertEqual(data["context"]["population"], 12000)
        self.assertGreater(data["context"]["days_left"], 0)
        state = provider.requests[0]["state"]
        self.assertIn("12000 workers", state["bee"])
        self.assertIn("time left", state)
        self.assertTrue(any("m from the cluster" in c for c in state["candidates"].values()))
        queen = self.entity(swarm)["queen"]
        self.assertEqual((queen["target_habitat_id"], queen["decision_support"]), (self.tree, 12000))
        self.wait_for(lambda: self.entity(swarm)["state"] == "settled")
        tree = self.entity(self.tree)
        self.assertEqual((tree["occupant_ids"], tree["occupants"], tree["capacity"]), ([swarm], 1, 1))

    def test_unavailable_service_means_no_decision(self):
        loop = DecisionLoop(self.engine, OpenJevProvider("http://127.0.0.1:9", timeout=1), interval_ticks=1)

        async def run_briefly():
            task = asyncio.create_task(loop.run(poll=0.05))
            await asyncio.sleep(1.0)
            task.cancel()

        self.send("resume")
        asyncio.run(run_briefly())
        status = loop.status()
        self.assertFalse(status["available"])
        self.assertIn("unreachable", status["error"])
        self.assertEqual(self.decisions(), [])  # and no silent fallback to the reference logic
        self.assertEqual(self.entity(self.bee)["state"], "searching")


def service_up() -> bool:
    try:
        with urllib.request.urlopen(SERVICE_URL + "/health", timeout=2) as r:
            return json.loads(r.read()).get("status") == "ok"
    except OSError:
        return False


@unittest.skipUnless(service_up(), f"OpenJev service not running at {SERVICE_URL}")
class OpenJevIntegrationTest(unittest.TestCase):
    def test_full_decision_with_the_real_model(self):
        with GodotEngine() as engine:
            tree = engine.send("add_habitat", type="tree_cavity", x=100, y=100)["id"]
            engine.send("add_habitat", type="hive_box", x=300, y=100, features={"cavity_volume_l": 5})
            bee = engine.send("add_swarm", x=120, y=120, population=10000, personality={"preset": "audacieuse"})["id"]
            engine.send("resume")
            provider = OpenJevProvider(SERVICE_URL)
            self.assertTrue(provider.status()["available"])
            t = time.perf_counter()
            data = DecisionLoop(engine, provider).decide_for(bee)
            self.assertLess(time.perf_counter() - t, 30)
            self.assertEqual(data["source"], "openjev")
            self.assertAlmostEqual(sum(data["probabilities"].values()), 1.0, places=2)
            self.assertIn(data["chosen_habitat_id"], [tree, None, *data["probabilities"]])
            swarm = engine.send("get_entity", id=bee)
            self.assertEqual(swarm["state"], "flying" if data["chosen_habitat_id"] else "cluster")


if __name__ == "__main__":
    unittest.main()
