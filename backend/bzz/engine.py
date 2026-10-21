"""Launch, talk to, and stop a Godot instance (headless, or in its own window).

Configured by environment variables (see .env.example):
  GODOT_HOST         if set, connect to an already running Godot (e.g. another container) instead of spawning one
  GODOT_PORT         port of that remote Godot (default 9876); a free port is picked when spawning
  GODOT_BIN          Godot executable when spawning (default "godot" on PATH)
  GODOT_PROJECT_DIR  Godot project when spawning (default: ../godot relative to this repo)
  GODOT_TIMEOUT      seconds to wait for Godot to accept connections (default 10)
  GODOT_DISPLAY      headless (default here: tests, CI, servers) or window (Godot opens its read-only view);
                     used when spawning Godot. In window mode Godot normally runs on the host (godot/start.sh)
                     and the backend connects to it through GODOT_HOST.
  WORLD_WIDTH/HEIGHT, DAY_TICKS, FLIGHT_SPEED_FACTOR, SWARM_SPEED_MPS, SWARM_CLUSTER_DAYS
                     simulation parameters passed to a spawned Godot when set (defaults live in Godot:
                     WorldApi.DEFAULT_SIZE / DEFAULT_CONFIG)

One TCP connection is shared by every caller (HTTP requests, the event poller, stdin): a lock makes each
request/response pair atomic, so concurrent callers never read each other's responses.
If the connection drops (window closed, Godot restarted), it is marked lost; try_connect() reconnects to a remote
Godot as soon as it is back, without restarting the backend.
"""

import itertools
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from .commands import validate

# environment variable -> Godot command-line flag, passed only when set
GODOT_PARAMS = {"WORLD_WIDTH": "world-width", "WORLD_HEIGHT": "world-height", "DAY_TICKS": "day-ticks",
                "FLIGHT_SPEED_FACTOR": "flight-speed-factor", "SWARM_SPEED_MPS": "swarm-speed-mps",
                "SWARM_CLUSTER_DAYS": "swarm-cluster-days"}

DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[2] / "godot"
DISPLAY_MODES = ("headless", "window")


def _free_port() -> int:
    # shortcut: port could be taken between close and Godot's listen; retry start() if that ever bites
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class GodotError(RuntimeError):
    pass


class CommandRejected(GodotError):
    """Godot answered ok=false (validation error, unknown entity...)."""


class GodotEngine:
    def __init__(
        self,
        godot_bin: str | None = None,
        project_dir: Path | None = None,
        timeout: float | None = None,
        host: str | None = None,
        port: int | None = None,
        godot_params: dict | None = None,
        display: str | None = None,
    ):
        env = os.environ.get
        self.godot_bin = godot_bin or env("GODOT_BIN") or "godot"
        self.project_dir = Path(project_dir or env("GODOT_PROJECT_DIR") or DEFAULT_PROJECT_DIR)
        self.timeout = timeout or float(env("GODOT_TIMEOUT") or 10)
        self.host = host or env("GODOT_HOST") or None  # None -> spawn a local Godot
        self.port = port or int(env("GODOT_PORT") or 9876)
        # flag -> value for a spawned Godot: from the environment, then overridden by `godot_params`
        self.godot_params = {flag: v for var, flag in GODOT_PARAMS.items() if (v := env(var))}
        self.godot_params.update(godot_params or {})
        self.proc: subprocess.Popen | None = None
        self.sock: socket.socket | None = None
        self._file = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.catalog: dict | None = None  # fetched at start; used to validate values before sending
        self.display = display or env("GODOT_DISPLAY") or "headless"
        if self.display not in DISPLAY_MODES:
            raise ValueError(f"GODOT_DISPLAY must be one of {DISPLAY_MODES} (got {self.display!r})")
        self.generation = 0  # +1 per successful connection: a new Godot means a new world (event cursor reset)

    @property
    def connected(self) -> bool:
        return self._file is not None

    @property
    def remote(self) -> bool:
        return self.host is not None

    def start(self) -> None:
        if self._file:
            raise GodotError("already running")
        if self.remote:
            self._connect(self.host, self.port)
        else:
            if not (self.project_dir / ".godot" / "global_script_class_cache.cfg").exists():
                # fresh checkout: class_name scripts are only known after an import
                subprocess.run([self.godot_bin, "--headless", "--path", str(self.project_dir), "--import"],
                               capture_output=True, timeout=120)
            port = _free_port()
            params = [f"--{flag}={v}" for flag, v in self.godot_params.items()]
            headless = ["--headless"] if self.display == "headless" else []
            self.proc = subprocess.Popen(
                [self.godot_bin, *headless, "--path", str(self.project_dir), "--", f"--port={port}", *params]
            )
            self._connect("127.0.0.1", port)
        self._after_connect()

    def _after_connect(self) -> None:
        self.generation += 1
        self.catalog = None
        self.catalog = self.send("get_catalog")

    def try_connect(self, timeout: float = 1.0) -> bool:
        """One quick attempt to (re)connect to a remote Godot; True if connected. Never blocks for long, so the
        backend can start before Godot and pick it up as soon as it is launched (or relaunched)."""
        if self._file:
            return True
        if not self.remote:
            return False  # a spawned Godot is restarted with restart(), not here
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        except OSError:
            return False
        self.sock.settimeout(self.timeout)
        self._file = self.sock.makefile("rwb")
        try:
            self._after_connect()
        except (GodotError, OSError):
            self._drop()
            return False
        return True

    def _drop(self) -> None:
        """Forget a broken connection (the caller holds the lock or no one else uses it)."""
        for f in (self._file, self.sock):
            try:
                if f:
                    f.close()
            except OSError:
                pass
        self._file = self.sock = None

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
        validate(cmd, args, self.catalog)
        with self._lock:
            if not self._file:
                raise GodotError("not connected to Godot")
            req_id = next(self._ids)
            try:
                self._file.write(json.dumps({"id": req_id, "cmd": cmd, "args": args}).encode() + b"\n")
                self._file.flush()
                line = self._file.readline()
            except OSError as e:
                self._drop()
                raise GodotError(f"connection to Godot lost: {e}") from None
            if not line:
                self._drop()
                raise GodotError("connection closed by Godot")
        resp = json.loads(line)
        if resp.get("id") != req_id:
            raise GodotError(f"response id mismatch: {resp}")
        if not resp["ok"]:
            raise CommandRejected(resp["error"])
        return resp["result"]

    def stop(self, quit_remote: bool = False) -> None:
        """Quit a spawned Godot; a remote one is only disconnected unless quit_remote."""
        if self._file:
            if not self.remote or quit_remote:
                try:
                    self.send("quit")
                except (OSError, GodotError, ValueError):
                    pass
            with self._lock:
                self._drop()
        if self.proc:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None

    def restart(self) -> None:
        """Spawned Godot: relaunched. Remote headless Godot: quit, its supervisor (Compose) brings it back and we
        reconnect. Remote Godot in a window: refused, since only the user can relaunch it."""
        if self.remote and self._file and self.send("get_state").get("display") == "window":
            raise GodotError("Godot runs in its own window: close it and relaunch it with godot/start.sh "
                             "(or godot\\start.ps1); the backend reconnects by itself")
        self.stop(quit_remote=True)
        if self.remote:
            time.sleep(0.5)  # let the old process release the port before reconnecting
        self.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
