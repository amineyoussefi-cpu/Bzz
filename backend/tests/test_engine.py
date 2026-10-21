"""Integration tests: need a `godot` 4.x binary on PATH (or GODOT_BIN). Run: python -m unittest discover backend/tests"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bzz import GodotEngine, GodotError


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = GodotEngine()
        self.engine.start()

    def tearDown(self):
        self.engine.stop()

    def test_ping(self):
        self.assertEqual(self.engine.send("ping"), "pong")

    def test_state_advances_and_world_starts_empty(self):
        a = self.engine.send("get_state")
        time.sleep(0.3)
        b = self.engine.send("get_state")
        self.assertGreater(b["physics_frames"], a["physics_frames"])
        self.assertEqual(b["node_count"], 0)

    def test_headless_mode_has_no_window_and_no_view(self):
        state = self.engine.send("get_state")
        self.assertEqual((state["display"], state["view_loaded"]), ("headless", False))

    def test_restart_refused_for_a_godot_in_its_own_window(self):
        remote = GodotEngine(host="127.0.0.1", port=1)
        remote._file = object()  # pretend to be connected to a windowed Godot
        remote.send = lambda cmd, **args: {"display": "window"}
        with self.assertRaisesRegex(GodotError, "relaunch it"):
            remote.restart()

    def test_invalid_command_rejected_before_send(self):
        with self.assertRaises(ValueError):
            self.engine.send("teleport")
        with self.assertRaises(ValueError):
            self.engine.send("ping", x=1)

    def test_restart(self):
        old_pid = self.engine.proc.pid
        self.engine.restart()
        self.assertNotEqual(self.engine.proc.pid, old_pid)
        self.assertEqual(self.engine.send("ping"), "pong")

    def test_stop_terminates_process(self):
        proc = self.engine.proc
        self.engine.stop()
        self.assertIsNotNone(proc.poll())
        with self.assertRaises(GodotError):
            self.engine.send("ping")


if __name__ == "__main__":
    unittest.main()
