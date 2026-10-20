"""Launch, talk to, and stop a headless Godot instance."""

import itertools
import json
import os
import socket
import subprocess
import time
from pathlib import Path

from .commands import validate

PROJECT_DIR = Path(__file__).resolve().parents[2] / "godot"


def _free_port() -> int:
    # shortcut: port could be taken between close and Godot's listen; retry start() if that ever bites
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class GodotError(RuntimeError):
    pass


class GodotEngine:
    def __init__(self, godot_bin: str | None = None, project_dir: Path = PROJECT_DIR, timeout: float = 10.0):
        self.godot_bin = godot_bin or os.environ.get("GODOT_BIN", "godot")
        self.project_dir = Path(project_dir)
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self.sock: socket.socket | None = None
        self._file = None
        self._ids = itertools.count(1)

    def start(self) -> None:
        if self.proc:
            raise GodotError("already running")
        port = _free_port()
        self.proc = subprocess.Popen(
            [self.godot_bin, "--headless", "--path", str(self.project_dir), "--", f"--port={port}"]
        )
        deadline = time.monotonic() + self.timeout
        while True:
            if self.proc.poll() is not None:
                self.proc = None
                raise GodotError("Godot exited during startup")
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=self.timeout)
                break
            except OSError:
                if time.monotonic() > deadline:
                    self.stop()
                    raise GodotError("Godot did not start listening in time")
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

    def stop(self) -> None:
        if self._file:
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
        self.stop()
        self.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
