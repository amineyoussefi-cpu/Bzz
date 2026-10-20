"""Read JSON commands from stdin, one per line ({"cmd": "ping", "args": {}}), forward them to Godot, print results."""

import json
import sys

from .engine import GodotEngine, GodotError


def main() -> None:
    with GodotEngine() as engine:
        for line in sys.stdin:
            if not line.strip():
                continue
            msg = {}
            try:
                msg = json.loads(line)
                if msg.get("cmd") == "restart":
                    engine.restart()
                    out = {"ok": True, "result": "restarted"}
                else:
                    out = {"ok": True, "result": engine.send(msg["cmd"], **msg.get("args", {}))}
            except (ValueError, KeyError, TypeError, AttributeError, GodotError) as e:
                out = {"ok": False, "error": str(e)}
            print(json.dumps(out), flush=True)
            if msg.get("cmd") == "quit" and out["ok"]:
                break


if __name__ == "__main__":
    main()
