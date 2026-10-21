"""The backend survives Godot being closed and relaunched (window mode), without restarting."""

import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # fakes.py

from bzz import GodotEngine, GodotError
from bzz.engine import DEFAULT_PROJECT_DIR

try:
    from fastapi.testclient import TestClient

    from bzz.server import create_app
except ImportError:
    TestClient = None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RemoteGodot:
    """A Godot server started outside the engine, like the user's window (headless here: no window in tests)."""

    def __init__(self, port: int):
        self.port = port
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen(["godot", "--headless", "--path", str(DEFAULT_PROJECT_DIR), "--",
                                      f"--port={self.port}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def close(self):  # like closing the window
        self.proc.terminate()
        self.proc.wait(5)


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.1)


class EngineReconnectTest(unittest.TestCase):
    def test_engine_reconnects_to_a_relaunched_godot(self):
        godot = RemoteGodot(free_port())
        engine = GodotEngine(host="127.0.0.1", port=godot.port)
        self.assertFalse(engine.try_connect())  # Godot not launched yet: no blocking, no crash
        godot.start()
        try:
            wait_for(engine.try_connect)
            first = engine.generation
            engine.send("add_habitat", type="tree_cavity", x=1, y=1)
            godot.close()
            with self.assertRaises(GodotError):
                engine.send("get_state")
            self.assertFalse(engine.connected)
            godot.start()
            wait_for(engine.try_connect)
            self.assertEqual(engine.generation, first + 1)
            self.assertEqual(engine.send("get_state")["habitats"], 0)  # a relaunched Godot is a new world
        finally:
            godot.close()


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class ServerReconnectTest(unittest.TestCase):
    def test_backend_starts_before_godot_and_follows_its_restarts(self):
        from fakes import FakeProvider

        godot = RemoteGodot(free_port())
        app = create_app(GodotEngine(host="127.0.0.1", port=godot.port), provider=FakeProvider())
        status = lambda: client.get("/api/godot/status").json()  # noqa: E731
        with TestClient(app) as client:
            self.assertFalse(status()["connected"])  # started without Godot
            self.assertEqual(client.get("/api/state").status_code, 503)
            godot.start()
            try:
                wait_for(lambda: status()["connected"])
                self.assertEqual(status()["display"], "headless")
                self.assertEqual(client.post("/api/habitats", json={"type": "hive_box", "x": 5, "y": 5}).status_code, 201)
                godot.close()
                wait_for(lambda: not status()["connected"])
                with client.websocket_connect("/ws") as ws:
                    self.assertFalse(ws.receive_json()["godot"]["connected"])
                godot.start()
                wait_for(lambda: status()["connected"])
                self.assertEqual(client.get("/api/entities").json(), [])
            finally:
                godot.close()


if __name__ == "__main__":
    unittest.main()
