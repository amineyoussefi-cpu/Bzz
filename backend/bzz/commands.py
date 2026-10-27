"""Commands the Godot world understands, and validation before they are sent.

Structure (command names, argument names and types) is checked here; values (types, species, presets,
bounds, world size) are checked against the catalogue Godot generates, so no list is copied by hand.
Godot validates again on its side (godot/api/world_api.gd). Keep COMMANDS in sync with WorldApi.ARGS.
"""

NUM = (int, float)

# command name -> {arg: (accepted python types, required)}
COMMANDS: dict[str, dict[str, tuple[tuple[type, ...] | type, bool]]] = {
    "ping": {},
    "quit": {},
    "get_state": {},
    "get_catalog": {},
    "list_entities": {},
    "clear_world": {},
    "pause": {},
    "resume": {},
    "add_habitat": {"type": (str, True), "x": (NUM, True), "y": (NUM, True), "features": (dict, False)},
    "add_bee": {"x": (NUM, False), "y": (NUM, False), "personality": (dict, False),
                "name": (str, False), "role": (str, False)},
    "get_entity": {"id": (str, True)},
    "remove_entity": {"id": (str, True)},
    "move_entity": {"id": (str, True), "x": (NUM, True), "y": (NUM, True)},
    "update_habitat": {"id": (str, True), "features": (dict, True)},
    "answer_decision": {"bee_id": (str, True), "kind": (str, True), "answer": (dict, True)},
    "set_speed": {"speed": (NUM, True)},
    "get_events": {"since": (int, False)},
}

MAX_SEED = 2**31 - 1


def _is(value, types) -> bool:
    return isinstance(value, types) and not isinstance(value, bool)  # bool is an int in Python


def _one_of(kind: str, value, accepted) -> None:
    if value not in accepted:
        raise ValueError(f"unknown {kind} {value!r}; accepted: {', '.join(accepted)}")


def validate(cmd: str, args: dict, catalog: dict | None = None) -> None:
    if cmd not in COMMANDS:
        raise ValueError(f"unknown command: {cmd!r}")
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    spec = COMMANDS[cmd]
    extra = set(args) - set(spec)
    if extra:
        raise ValueError(f"unexpected args for {cmd!r}: {sorted(extra)}; accepted: {sorted(spec)}")
    for name, (types, required) in spec.items():
        if name not in args:
            if required:
                raise ValueError(f"missing arg {name!r} for {cmd!r}")
        elif not _is(args[name], types):
            raise ValueError(f"{name} has the wrong type")
    if catalog:
        _check_values(cmd, args, catalog)


def _check_values(cmd: str, args: dict, cat: dict) -> None:
    if ("x" in args) != ("y" in args):
        raise ValueError("give both x and y, or neither")
    if "x" in args:
        w, h = cat["world"]["width"], cat["world"]["height"]
        if not (0 <= args["x"] <= w and 0 <= args["y"] <= h):
            raise ValueError(f"position ({args['x']}, {args['y']}) is outside the world (0..{w}, 0..{h})")
    if cmd == "add_habitat":
        _one_of("habitat type", args["type"], [t["name"] for t in cat["habitat_types"]])
        for key, value in args.get("features", {}).items():
            _check_feature(key, value, cat["features"])
    elif cmd == "update_habitat":
        if not args["features"]:
            raise ValueError("features must be a non-empty object")
        for key, value in args["features"].items():
            _check_feature(key, value, cat["features"])
    elif cmd == "add_bee":
        if "role" in args:
            _one_of("role", args["role"], cat["roles"])
        if len(args.get("name", "")) > cat["max_name_length"]:
            raise ValueError(f"name must be at most {cat['max_name_length']} characters")
        if "personality" in args:
            _check_personality(args["personality"], cat)
    elif cmd == "set_speed":
        lo, hi = cat["speed"]["min"], cat["speed"]["max"]
        if not lo <= args["speed"] <= hi:
            raise ValueError(f"speed must be between {lo} and {hi} (got {args['speed']})")
    elif cmd == "get_events" and args.get("since", 0) < 0:
        raise ValueError("since must be a non-negative integer")


def _check_feature(key: str, value, features: dict) -> None:
    _one_of("feature", key, list(features))
    spec = features[key]
    if spec["type"] == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be true or false")
        return
    if not _is(value, NUM) or (spec["type"] == "int" and value != int(value)):
        raise ValueError(f"{key} must be {'an integer' if spec['type'] == 'int' else 'a number'}")
    if not spec["min"] <= value <= spec["max"]:
        raise ValueError(f"{key} must be between {spec['min']} and {spec['max']} (got {value})")


def _check_personality(p: dict, cat: dict) -> None:
    forms = '{"preset": name}, {"traits": {...}} or {"random": true, "seed": n}'
    if "preset" in p:
        if len(p) != 1:
            raise ValueError("personality preset takes no other key")
        _one_of("personality preset", p["preset"], list(cat["presets"]))
    elif "traits" in p:
        if len(p) != 1 or not isinstance(p["traits"], dict):
            raise ValueError('personality must be {"traits": {trait: value}}')
        names = [t["name"] for t in cat["traits"]]
        for t in p["traits"]:
            _one_of("trait", t, names)
        for t in names:
            v = p["traits"].get(t)
            if v is None:
                raise ValueError(f"missing trait {t}")
            if not _is(v, NUM) or not 0 <= v <= 1:
                raise ValueError(f"{t} must be a number between 0 and 1 (got {v})")
    elif p.get("random") is True:
        extra = set(p) - {"random", "seed"}
        if extra:
            raise ValueError(f"unexpected personality keys {sorted(extra)}")
        if "seed" in p and (not _is(p["seed"], int) or not 1 <= p["seed"] <= MAX_SEED):
            raise ValueError(f"seed must be an integer between 1 and {MAX_SEED}")
    else:
        raise ValueError(f"personality must be {forms}")
