"""Commands the Godot world understands, and validation before they are sent."""

# command name -> allowed argument names; keep in sync with godot/main.gd _handle()
COMMANDS: dict[str, set[str]] = {
    "ping": set(),
    "get_state": set(),
    "quit": set(),
}


def validate(cmd: str, args: dict) -> None:
    if cmd not in COMMANDS:
        raise ValueError(f"unknown command: {cmd!r}")
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    extra = set(args) - COMMANDS[cmd]
    if extra:
        raise ValueError(f"unexpected args for {cmd!r}: {sorted(extra)}")
