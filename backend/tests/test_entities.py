"""Runs the GDScript unit tests of the bee/habitat model (godot/tests/test_entities.gd)."""

import os
import subprocess
import unittest
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("GODOT_PROJECT_DIR") or Path(__file__).resolve().parents[2] / "godot")
GODOT = os.environ.get("GODOT_BIN") or "godot"


class EntitiesTest(unittest.TestCase):
    def test_gdscript_entities(self):
        # import registers class_name scripts, which --script mode needs
        subprocess.run([GODOT, "--headless", "--path", str(PROJECT_DIR), "--import"], capture_output=True, timeout=120)
        r = subprocess.run(
            [GODOT, "--headless", "--path", str(PROJECT_DIR), "--script", "res://tests/test_entities.gd"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("entity tests: OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
