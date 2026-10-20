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

    def test_state_advances_and_world_is_empty(self):
        a = self.engine.send("get_state")
        time.sleep(0.3)
        b = self.engine.send("get_state")
        self.assertGreater(b["physics_frames"], a["physics_frames"])
        self.assertEqual(b["node_count"], 0)

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
