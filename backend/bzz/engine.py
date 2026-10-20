"""Launch, talk to, and stop a headless Godot instance.

Configured by environment variables (see .env.example):
  GODOT_HOST         if set, connect to an already running Godot (e.g. another container) instead of spawning one
  GODOT_PORT         port of that remote Godot (default 9876); a free port is picked when spawning
  GODOT_BIN          Godot executable when spawning (default "godot" on PATH)
  GODOT_PROJECT_DIR  Godot project when spawning (default: ../godot relative to this repo)
  GODOT_TIMEOUT      seconds to wait for Godot to accept connections (default 10)
"""

import itertools
import json
import os
import socket
import subprocess
import time
from pathlib import Path

from .commands import validate

DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[2] / "godot"


def _free_port() -> int:
    # shortcut: port could be taken between close and Godot's listen; retry start() if that ever bites
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class GodotError(RuntimeError):
    pass


class GodotEngine:
    def __init__(
        self,
        godot_bin: str | None = None,
        project_dir: Path | None = None,
        timeout: float | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        env = os.environ.get
        self.godot_bin = godot_bin or env("GODOT_BIN") or "godot"
        self.project_dir = Path(project_dir or env("GODOT_PROJECT_DIR") or DEFAULT_PROJECT_DIR)
        self.timeout = timeout or float(env("GODOT_TIMEOUT") or 10)
        self.host = host or env("GODOT_HOST") or None  # None -> spawn a local Godot
        self.port = port or int(env("GODOT_PORT") or 9876)
        self.proc: subprocess.Popen | None = None
        self.sock: socket.socket | None = None
        self._file = None
        self._ids = itertools.count(1)

    @property
    def remote(self) -> bool:
        return self.host is not None

    def start(self) -> None:
        if self._file:
            raise GodotError("already running")
        if self.remote:
            self._connect(self.host, self.port)
            return
        port = _free_port()
        self.proc = subprocess.Popen(
            [self.godot_bin, "--headless", "--path", str(self.project_dir), "--", f"--port={port}"]
        )
        self._connect("127.0.0.1", port)

    def _connect(self, host: str, port: int) -> None:
        deadline = time.monotonic() + self.timeout
        while True:
            if self.proc and self.proc.poll() is not None:
                self.proc = None
                raise GodotError("Godot exited during startup")
            try:
                self.sock = socket.create_connection((host, port), timeout=self.timeout)
                break
            except OSError:
                if time.monotonic() > deadline:
                    self.stop()
                    raise GodotError(f"Godot not reachable on {host}:{port} in time")
                time.sleep(0.1)
        self._file = self.sock.makefile("rwb")

    def send(self, cmd: str, **args) -> object:
        validate(cmd, args)
        if not self._file:
            raise GodotError("not running")
        req_id = next(self._ids)
        self._file.write(json.dumps({"id": req_id, "cmd": cmd, "args": args}).encode() + b"\n")
        self._file.flush()
        line = self._file.readline()
        if not line:
            raise GodotError("connection closed by Godot")
        resp = json.loads(line)
        if resp.get("id") != req_id:
            raise GodotError(f"response id mismatch: {resp}")
        if not resp["ok"]:
            raise GodotError(resp["error"])
        return resp["result"]

    def stop(self, quit_remote: bool = False) -> None:
        """Quit a spawned Godot; a remote one is only disconnected unless quit_remote."""
        if self._file:
            if not self.remote or quit_remote:
                try:
                    self.send("quit")
                except (OSError, GodotError, ValueError):
                    pass
            self._file.close()
            self.sock.close()
            self._file = self.sock = None
        if self.proc:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None

    def restart(self) -> None:
        # remote: Godot quits and its supervisor (compose restart policy) brings it back; we reconnect
        self.stop(quit_remote=True)
        if self.remote:
            time.sleep(0.5)  # let the old process release the port before reconnecting
        self.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
