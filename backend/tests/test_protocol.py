"""Protocol tests for the world toolbox commands, against a real headless Godot (see docs/api.md)."""

import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bzz import CommandRejected, GodotEngine

TREE = {"type": "tree_cavity", "x": 100, "y": 100}
TRAITS = {"pickiness": 0.2, "boldness": 0.4, "sociability": 0.6, "curiosity": 0.8}


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.engine = GodotEngine()
        self.engine.start()
        self.send = self.engine.send

    def tearDown(self):
        self.engine.stop()

    def godot_only(self, cmd, **args):
        """Send without the Python value checks, to prove Godot validates too."""
        catalog, self.engine.catalog = self.engine.catalog, None
        try:
            return self.send(cmd, **args)
        finally:
            self.engine.catalog = catalog

    def count(self):
        return len(self.send("list_entities"))

    # --- catalogue ---------------------------------------------------------------------
    def test_catalog_uses_readable_names(self):
        c = self.send("get_catalog")
        self.assertIn("tree_cavity", [t["name"] for t in c["habitat_types"]])
        self.assertIn("honey_bee", [s["name"] for s in c["species"]])
        self.assertEqual(c["roles"], ["scout", "follower"])
        self.assertEqual([t["name"] for t in c["traits"]], ["pickiness", "boldness", "sociability", "curiosity"])
        self.assertIn("équilibrée", c["presets"])
        self.assertEqual(c["world"], {"width": 1000, "height": 700})
        tree = next(t for t in c["habitat_types"] if t["name"] == "tree_cavity")
        self.assertEqual(tree["defaults"]["cavity_volume_l"], 40)

    # --- habitats --------------------------------------------------------------------
    def test_add_habitat_with_defaults_and_overrides(self):
        h = self.send("add_habitat", type="bare_soil", x=10, y=20, features={"capacity": 12, "humidity": 0.1})
        self.assertEqual((h["kind"], h["type"], h["capacity"], h["x"], h["y"]), ("habitat", "bare_soil", 12, 10, 20))
        d = self.send("get_entity", id=h["id"])
        self.assertEqual(d["features"]["humidity"], 0.1)
        self.assertEqual(d["features"]["sun_exposure"], 0.9)  # default kept

    def test_add_habitat_refusals_python_and_godot(self):
        bad = [
            dict(type="nest", x=1, y=1),
            dict(type="tree_cavity", x=-1, y=1),
            dict(type="tree_cavity", x=1, y=701),
            dict(type="tree_cavity", x=1, y=1, features={"humidity": 1.5}),
            dict(type="tree_cavity", x=1, y=1, features={"capacity": 2.5}),
            dict(type="tree_cavity", x=1, y=1, features={"colour": 1}),
            dict(type="tree_cavity", x=1, y=1, features={"previously_occupied": 1}),
        ]
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    self.send("add_habitat", **args)
                with self.assertRaises(CommandRejected):
                    self.godot_only("add_habitat", **args)
        self.assertEqual(self.count(), 0)  # nothing partially created

    def test_error_lists_accepted_values(self):
        with self.assertRaisesRegex(ValueError, "accepted: tree_cavity, hive_box"):
            self.send("add_habitat", type="nest", x=1, y=1)
        with self.assertRaisesRegex(CommandRejected, "accepted: honey_bee, bumblebee"):
            self.godot_only("add_bee", species="wasp", x=1, y=1)

    # --- bees ------------------------------------------------------------------------
    def test_add_bee_personality_forms(self):
        a = self.send("add_bee", species="honey_bee", x=1, y=2, personality={"traits": TRAITS}, name="Ada")
        self.assertEqual((a["personality"], a["name"], a["role"], a["home_id"]), (TRAITS, "Ada", "follower", None))
        b = self.send("add_bee", species="bumblebee", x=1, y=2, personality={"preset": "prudente"}, role="scout")
        self.assertEqual((b["personality"]["pickiness"], b["role"]), (0.8, "scout"))
        c = self.send("add_bee", species="mason_bee", x=1, y=2)  # random by default
        detail = self.send("get_entity", id=c["id"])
        self.assertEqual(detail["personality_source"], "random")
        self.assertGreaterEqual(detail["seed"], 1)
        self.assertEqual(detail["accepted_habitat_types"], ["hollow_stem", "dead_wood"])
        self.assertTrue(detail["preferences"])

    def test_same_seed_same_bee(self):
        p = {"random": True, "seed": 1234}
        a = self.send("add_bee", species="honey_bee", x=1, y=1, personality=p)
        b = self.send("add_bee", species="honey_bee", x=1, y=1, personality=p)
        c = self.send("add_bee", species="honey_bee", x=1, y=1, personality={"random": True, "seed": 99})
        self.assertEqual(a["personality"], b["personality"])
        self.assertNotEqual(a["personality"], c["personality"])
        # a random bee without seed can be reproduced from the seed it reports
        d = self.send("add_bee", species="honey_bee", x=1, y=1)
        seed = self.send("get_entity", id=d["id"])["seed"]
        e = self.send("add_bee", species="honey_bee", x=1, y=1, personality={"random": True, "seed": seed})
        self.assertEqual(d["personality"], e["personality"])

    def test_add_bee_refusals_python_and_godot(self):
        bad = [
            dict(species="wasp", x=1, y=1),
            dict(species="honey_bee", x=5000, y=1),
            dict(species="honey_bee", x=1, y=1, role="king"),
            dict(species="honey_bee", x=1, y=1, name="x" * 41),
            dict(species="honey_bee", x=1, y=1, personality={"preset": "grumpy"}),
            dict(species="honey_bee", x=1, y=1, personality={"traits": {**TRAITS, "boldness": 1.2}}),
            dict(species="honey_bee", x=1, y=1, personality={"traits": {"pickiness": 0.5}}),
            dict(species="honey_bee", x=1, y=1, personality={"traits": {**TRAITS, "anger": 0.5}}),
            dict(species="honey_bee", x=1, y=1, personality={"random": True, "seed": 0}),
            dict(species="honey_bee", x=1, y=1, personality={"preset": "sociable", "seed": 3}),
            dict(species="honey_bee", x=1, y=1, personality={"mood": "happy"}),
        ]
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    self.send("add_bee", **args)
                with self.assertRaises(CommandRejected):
                    self.godot_only("add_bee", **args)
        self.assertEqual(self.count(), 0)

    # --- consultation & removal -----------------------------------------------------------
    def test_list_get_remove_clear(self):
        h = self.send("add_habitat", **TREE)
        b = self.send("add_bee", species="honey_bee", x=5, y=5)
        self.assertEqual([e["id"] for e in self.send("list_entities")], [h["id"], b["id"]])
        self.assertEqual(self.send("get_entity", id=h["id"])["occupant_ids"], [])
        removed = self.send("remove_entity", id=h["id"])
        self.assertEqual((removed["id"], removed["kind"], removed["released_bee_ids"]), (h["id"], "habitat", []))
        with self.assertRaisesRegex(CommandRejected, "unknown entity"):
            self.send("get_entity", id=h["id"])
        with self.assertRaisesRegex(CommandRejected, "unknown entity"):
            self.send("remove_entity", id=h["id"])
        self.send("add_habitat", **TREE)
        self.assertEqual(self.send("clear_world"), {"removed": 2})
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.send("get_state")["node_count"], 0)
        # ids are never reused
        again = self.send("add_habitat", **TREE)
        self.assertNotIn(again["id"], {h["id"], b["id"]})

    # --- clock & events -----------------------------------------------------------------
    def test_pause_resume_speed(self):
        s = self.send("get_state")
        self.assertTrue(s["paused"])
        time.sleep(0.2)
        self.assertEqual(self.send("get_state")["tick"], s["tick"])  # paused: simulation time frozen
        self.send("resume")
        time.sleep(0.3)
        running = self.send("get_state")
        self.assertFalse(running["paused"])
        self.assertGreater(running["tick"], s["tick"])
        self.assertEqual(self.send("set_speed", speed=2), {"speed": 2})
        with self.assertRaises(ValueError):
            self.send("set_speed", speed=100)
        with self.assertRaises(CommandRejected):
            self.godot_only("set_speed", speed=0)
        self.send("pause")
        t = self.send("get_state")["tick"]
        time.sleep(0.2)
        self.assertEqual(self.send("get_state")["tick"], t)

    def test_events_cursor_and_ticks(self):
        h = self.send("add_habitat", **TREE)
        self.send("resume")
        time.sleep(0.2)
        self.send("pause")
        self.send("remove_entity", id=h["id"])
        self.send("clear_world")
        res = self.send("get_events", since=0)
        types = [e["type"] for e in res["events"]]
        self.assertEqual(types, ["entity_added", "resumed", "paused", "entity_removed", "world_cleared"])
        self.assertEqual([e["seq"] for e in res["events"]], [1, 2, 3, 4, 5])
        self.assertEqual(res["events"][0]["tick"], 0)  # stamped with simulation time, not wall clock
        self.assertGreater(res["events"][3]["tick"], 0)
        self.assertFalse(res["lost"])
        later = self.send("get_events", since=3)
        self.assertEqual([e["seq"] for e in later["events"]], [4, 5])
        self.assertEqual(self.send("get_events", since=5)["events"], [])

    # --- no decision yet ------------------------------------------------------------------
    def test_no_decision_is_taken(self):
        for t, x in [("tree_cavity", 100), ("hive_box", 200), ("bare_soil", 300), ("hollow_stem", 400), ("dead_wood", 500)]:
            self.send("add_habitat", type=t, x=x, y=100)
        bees = [self.send("add_bee", species=s, x=50 + 10 * i, y=600, role=r)
                for i, (s, r) in enumerate([("honey_bee", "scout"), ("honey_bee", "follower"),
                                            ("bumblebee", "follower"), ("mining_bee", "follower")])]
        self.send("set_speed", speed=8)
        self.send("resume")
        time.sleep(1.0)
        state = self.send("get_state")
        self.assertGreater(state["tick"], 200)
        self.assertIsNone(state["decision_mechanism"])
        after = {e["id"]: e for e in self.send("list_entities")}
        for b in bees:
            self.assertIsNone(after[b["id"]]["home_id"])
            self.assertEqual((after[b["id"]]["x"], after[b["id"]]["y"]), (b["x"], b["y"]))
        self.assertTrue(all(e["occupants"] == 0 for e in after.values() if e["kind"] == "habitat"))
        self.assertNotIn("decision", [e["type"] for e in self.send("get_events")["events"]])


class WorldSizeTest(unittest.TestCase):
    def test_world_size_from_environment(self):
        os.environ.update(WORLD_WIDTH="200", WORLD_HEIGHT="150")
        try:
            with GodotEngine(host=None) as engine:
                self.assertEqual(engine.catalog["world"], {"width": 200, "height": 150})
                with self.assertRaises(ValueError):
                    engine.send("add_habitat", **TREE | {"x": 300})
                engine.send("add_habitat", **TREE | {"x": 200, "y": 150})
        finally:
            del os.environ["WORLD_WIDTH"], os.environ["WORLD_HEIGHT"]


if __name__ == "__main__":
    unittest.main()
