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
        self.assertNotIn("species", c)
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

    # --- bees ------------------------------------------------------------------------
    def test_add_bee_personality_forms(self):
        a = self.send("add_bee", x=1, y=2, personality={"traits": TRAITS}, name="Ada")
        self.assertEqual((a["personality"], a["name"], a["role"], a["home_id"]), (TRAITS, "Ada", "follower", None))
        b = self.send("add_bee", x=1, y=2, personality={"preset": "prudente"}, role="scout")
        self.assertEqual((b["personality"]["pickiness"], b["role"]), (0.8, "scout"))
        c = self.send("add_bee", x=1, y=2)  # random by default
        detail = self.send("get_entity", id=c["id"])
        self.assertEqual(detail["personality_source"], "random")
        self.assertGreaterEqual(detail["seed"], 1)

    def test_same_seed_same_bee(self):
        p = {"random": True, "seed": 1234}
        a = self.send("add_bee", x=1, y=1, personality=p)
        b = self.send("add_bee", x=1, y=1, personality=p)
        c = self.send("add_bee", x=1, y=1, personality={"random": True, "seed": 99})
        self.assertEqual(a["personality"], b["personality"])
        self.assertNotEqual(a["personality"], c["personality"])
        # a random bee without seed can be reproduced from the seed it reports
        d = self.send("add_bee", x=1, y=1)
        seed = self.send("get_entity", id=d["id"])["seed"]
        e = self.send("add_bee", x=1, y=1, personality={"random": True, "seed": seed})
        self.assertEqual(d["personality"], e["personality"])

    def test_add_bee_refusals_python_and_godot(self):
        bad = [
            dict(x=5000, y=1),
            dict(x=1, y=1, role="king"),
            dict(x=1, y=1, name="x" * 41),
            dict(x=1, y=1, personality={"preset": "grumpy"}),
            dict(x=1, y=1, personality={"traits": {**TRAITS, "boldness": 1.2}}),
            dict(x=1, y=1, personality={"traits": {"pickiness": 0.5}}),
            dict(x=1, y=1, personality={"traits": {**TRAITS, "anger": 0.5}}),
            dict(x=1, y=1, personality={"random": True, "seed": 0}),
            dict(x=1, y=1, personality={"preset": "sociable", "seed": 3}),
            dict(x=1, y=1, personality={"mood": "happy"}),
        ]
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    self.send("add_bee", **args)
                with self.assertRaises(CommandRejected):
                    self.godot_only("add_bee", **args)
        self.assertEqual(self.count(), 0)

    # --- the swarm's branch --------------------------------------------------------------------
    def test_bees_without_position_cluster_on_the_central_branch(self):
        c = self.send("get_catalog")
        branch = (c["branch"]["x"], c["branch"]["y"])
        self.assertEqual(branch, (c["world"]["width"] / 2, c["world"]["height"] / 2))
        bees = [self.send("add_bee") for _ in range(20)]
        spots = {(b["x"], b["y"]) for b in bees}
        self.assertEqual(len(spots), 20)  # clustered, never stacked on one pixel
        self.assertTrue(all(((x - branch[0]) ** 2 + (y - branch[1]) ** 2) ** .5 <= 50 for x, y in spots))  # 20 bees: radius 11 * sqrt(19) ≈ 48
        self.assertEqual(self.send("add_bee", x=10, y=20)["x"], 10)  # an explicit position still wins
        with self.assertRaisesRegex(CommandRejected, "missing y"):
            self.godot_only("add_bee", x=10)
        with self.assertRaisesRegex(ValueError, "both x and y"):
            self.send("add_bee", x=10)

    # --- editing a habitat ----------------------------------------------------------------------
    def test_update_habitat_features(self):
        h = self.send("add_habitat", **TREE)
        d = self.send("update_habitat", id=h["id"], features={"sun_exposure": 0.05, "capacity": 3})
        self.assertEqual((d["features"]["sun_exposure"], d["features"]["capacity"]), (0.05, 3))
        self.assertEqual(d["description"]["sun_exposure"], "very shady")  # words follow the numbers
        self.assertEqual(d["features"]["cavity_volume_l"], 40.0)  # untouched features keep their value
        with self.assertRaisesRegex(CommandRejected, "between 0"):
            self.godot_only("update_habitat", id=h["id"], features={"humidity": 2})
        with self.assertRaisesRegex(ValueError, "between 0"):
            self.send("update_habitat", id=h["id"], features={"humidity": 2})
        with self.assertRaisesRegex(CommandRejected, "not a habitat"):
            self.send("update_habitat", id=self.send("add_bee")["id"], features={"humidity": .5})
        with self.assertRaisesRegex(CommandRejected, "unknown entity"):
            self.send("update_habitat", id="hab-999", features={"humidity": .5})
        self.assertEqual(self.send("get_entity", id=h["id"])["features"]["humidity"], 0.4)  # refused -> unchanged

    # --- moving ------------------------------------------------------------------------------
    def test_move_entity(self):
        b = self.send("add_bee", x=5, y=5)
        moved = self.send("move_entity", id=b["id"], x=300, y=200)
        self.assertEqual((moved["x"], moved["y"]), (300, 200))
        self.assertEqual(self.send("get_entity", id=b["id"])["x"], 300)
        with self.assertRaisesRegex(CommandRejected, "outside the world"):
            self.godot_only("move_entity", id=b["id"], x=-1, y=0)
        with self.assertRaisesRegex(CommandRejected, "unknown entity"):
            self.send("move_entity", id="bee-999", x=1, y=1)
        types = [e["type"] for e in self.send("get_events")["events"]]
        self.assertEqual(types, ["entity_added", "entity_moved"])

    # --- consultation & removal -----------------------------------------------------------
    def test_list_get_remove_clear(self):
        h = self.send("add_habitat", **TREE)
        b = self.send("add_bee", x=5, y=5)
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
                for i, r in enumerate(["scout", "follower", "follower", "follower"])]
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
