class_name WorldApi
extends RefCounted
## World toolbox behind the TCP protocol: catalogue, adding/removing habitats and bees,
## simulation clock (pause/resume/speed) and the event log polled by the backend.
## Commands are documented in docs/api.md.

const DEFAULT_SIZE := Vector2(1000, 700)  # world size unless --world-width/--world-height are given
const EVENT_LOG_SIZE := 1000
const BASE_TICKS_PER_SECOND := 60
const SPEED_MIN := 0.25
const SPEED_MAX := 8.0
const MAX_NAME_LENGTH := 40

## Allowed arguments per command (the Python whitelist in backend/bzz/commands.py mirrors it).
const ARGS := {
	"get_state": [], "get_catalog": [], "list_entities": [], "clear_world": [], "pause": [], "resume": [],
	"add_habitat": ["type", "x", "y", "features"],
	"add_bee": ["x", "y", "personality", "name", "role"],
	"get_entity": ["id"], "remove_entity": ["id"], "move_entity": ["id", "x", "y"],
	"set_speed": ["speed"], "get_events": ["since"],
}

var world: Node2D
var size := DEFAULT_SIZE
var entities := {}  # id -> Habitat | Bee, in creation order
var next_id := 1    # never reset, so ids stay unique for the whole run
var tick := 0       # simulation time: advances only while running
var paused := true  # the world is built paused, then resumed
var speed := 1.0
var events: Array[Dictionary] = []
var next_seq := 1


func _init(p_world: Node2D, p_size := DEFAULT_SIZE) -> void:
	world = p_world
	size = p_size


## Called every physics frame.
func step() -> void:
	if not paused:
		tick += 1


## {"ok": true, "result": ...} or {"ok": false, "error": "..."}.
func handle(cmd: String, args: Dictionary) -> Dictionary:
	if cmd not in ARGS:
		return _err("unknown command: %s" % cmd)
	for key in args:
		if key not in ARGS[cmd]:
			return _err("unexpected arg for %s: %s; accepted: %s" % [cmd, key, ", ".join(ARGS[cmd])])
	return call("_cmd_" + cmd, args)


func _ok(result) -> Dictionary:
	return {"ok": true, "result": result}


func _err(msg: String) -> Dictionary:
	return {"ok": false, "error": msg}


func _emit(type: String, data := {}) -> void:
	events.append({"seq": next_seq, "tick": tick, "type": type, "data": data})
	next_seq += 1
	if events.size() > EVENT_LOG_SIZE:
		events.pop_front()


# --- state & catalogue ----------------------------------------------------------

func _cmd_get_state(_args: Dictionary) -> Dictionary:
	var habitats := entities.values().filter(func(e): return e is Habitat).size()
	return _ok({
		"physics_frames": Engine.get_physics_frames(),
		"process_frames": Engine.get_process_frames(),
		"node_count": world.get_child_count(),
		"tick": tick, "paused": paused, "speed": speed,
		"ticks_per_second": BASE_TICKS_PER_SECOND,
		"world": {"width": size.x, "height": size.y},
		"habitats": habitats, "bees": entities.size() - habitats,
		"last_event_seq": next_seq - 1,
		"decision_mechanism": null,  # no decision mechanism yet (next step); the dashboard shows this
	})


func _cmd_get_catalog(_args: Dictionary) -> Dictionary:
	var habitat_types := []
	for t in Habitat.Type.values():
		habitat_types.append({"name": HabitatCatalog.type_name(t), "defaults": HabitatCatalog.defaults(t)})
	return _ok({
		"habitat_types": habitat_types,
		"features": HabitatCatalog.FEATURES,
		"roles": BeeRole.names(),
		"default_role": BeeRole.names()[BeeRole.Id.FOLLOWER],
		"traits": BeePersonality.TRAITS.map(func(t): return {"name": t, "min": 0.0, "max": 1.0}),
		"presets": BeePersonality.PRESETS,
		"world": {"width": size.x, "height": size.y},
		"speed": {"min": SPEED_MIN, "max": SPEED_MAX, "default": 1.0},
		"ticks_per_second": BASE_TICKS_PER_SECOND,
		"max_name_length": MAX_NAME_LENGTH,
	})


# --- adding entities ----------------------------------------------------------------
# Everything is validated before anything is created, so a refused command leaves nothing behind.

func _position_error(args: Dictionary) -> String:
	for key in ["x", "y"]:
		if key not in args:
			return "missing %s" % key
		if typeof(args[key]) not in [TYPE_INT, TYPE_FLOAT]:
			return "%s must be a number" % key
	if args.x < 0 or args.x > size.x or args.y < 0 or args.y > size.y:
		return "position (%s, %s) is outside the world (0..%s, 0..%s)" % [args.x, args.y, size.x, size.y]
	return ""


func _cmd_add_habitat(args: Dictionary) -> Dictionary:
	var type_name = args.get("type")
	var t := HabitatCatalog.type_from_name(type_name) if typeof(type_name) == TYPE_STRING else -1
	if t == -1:
		return _err("unknown habitat type %s; accepted: %s" % [type_name, ", ".join(HabitatCatalog.type_names())])
	var pos_err := _position_error(args)
	if pos_err:
		return _err(pos_err)
	var features = args.get("features", {})
	if typeof(features) != TYPE_DICTIONARY:
		return _err("features must be an object")
	var feat_err := HabitatCatalog.validate_features(features)
	if feat_err:
		return _err(feat_err)

	var h := HabitatCatalog.create(t, features)
	_register(h, "hab", Vector2(args.x, args.y))
	var summary := _summary(h)
	_emit("entity_added", summary)
	return _ok(summary)


func _cmd_add_bee(args: Dictionary) -> Dictionary:
	var pos_err := _position_error(args)
	if pos_err:
		return _err(pos_err)
	var bee_name = args.get("name", "")
	if typeof(bee_name) != TYPE_STRING or bee_name.length() > MAX_NAME_LENGTH:
		return _err("name must be a string of at most %d characters" % MAX_NAME_LENGTH)
	var role := BeeRole.Id.FOLLOWER
	if "role" in args:
		role = BeeRole.from_name(args.role) if typeof(args.role) == TYPE_STRING else -1
		if role == -1:
			return _err("unknown role %s; accepted: %s" % [args.role, ", ".join(BeeRole.names())])
	var parsed := _parse_personality(args.get("personality", {"random": true}))
	if "error" in parsed:
		return _err(parsed.error)

	var bee := Bee.create(parsed.personality, parsed.seed)
	bee.bee_name = bee_name
	if role != bee.role:
		bee.set_role(role)
	bee.set_meta("seed", parsed.seed)
	bee.set_meta("personality_source", parsed.source)
	_register(bee, "bee", Vector2(args.x, args.y))
	var summary := _summary(bee)
	_emit("entity_added", summary)
	return _ok(summary)


## {"personality": BeePersonality|null, "seed": int, "source": String} or {"error": String}.
## Forms: {"preset": name} | {"traits": {...}} | {"random": true, "seed"?: int >= 1}.
func _parse_personality(p) -> Dictionary:
	if typeof(p) != TYPE_DICTIONARY or p.size() == 0:
		return {"error": "personality must be {\"preset\": name}, {\"traits\": {...}} or {\"random\": true, \"seed\": n}"}
	var seed_value := randi_range(1, 2147483647)  # a fresh seed is always recorded, so any bee can be reproduced
	if "preset" in p:
		if p.size() != 1:
			return {"error": "personality preset takes no other key"}
		if typeof(p.preset) != TYPE_STRING or p.preset not in BeePersonality.PRESETS:
			return {"error": "unknown personality preset %s; accepted: %s" % [p.preset, ", ".join(BeePersonality.PRESETS.keys())]}
		return {"personality": BeePersonality.from_traits(BeePersonality.PRESETS[p.preset]), "seed": seed_value, "source": "preset:" + p.preset}
	if "traits" in p:
		if p.size() != 1:
			return {"error": "personality traits take no other key"}
		if typeof(p.traits) != TYPE_DICTIONARY:
			return {"error": "traits must be an object"}
		var err := BeePersonality.validate_traits(p.traits)
		if err:
			return {"error": err}
		return {"personality": BeePersonality.from_traits(p.traits), "seed": seed_value, "source": "traits"}
	if p.get("random") == true:
		for key in p:
			if key not in ["random", "seed"]:
				return {"error": "unexpected personality key %s" % key}
		if "seed" in p:
			if typeof(p.seed) not in [TYPE_INT, TYPE_FLOAT] or p.seed != floorf(p.seed) or p.seed < 1 or p.seed > 2147483647:
				return {"error": "seed must be an integer between 1 and 2147483647"}
			seed_value = int(p.seed)
		return {"personality": null, "seed": seed_value, "source": "random"}
	return {"error": "personality must be {\"preset\": name}, {\"traits\": {...}} or {\"random\": true, \"seed\": n}"}


func _register(node: Node2D, prefix: String, pos: Vector2) -> void:
	var id := "%s-%d" % [prefix, next_id]
	next_id += 1
	node.set_meta("id", id)
	node.name = id
	node.position = pos
	world.add_child(node)
	entities[id] = node


# --- reading -----------------------------------------------------------------------

func _summary(e: Node2D) -> Dictionary:
	var d := {"id": e.get_meta("id"), "x": e.position.x, "y": e.position.y}
	if e is Habitat:
		d.merge({"kind": "habitat", "type": HabitatCatalog.type_name(e.habitat_type),
			"capacity": e.capacity, "occupants": e.occupants.size()})
	else:
		d.merge({"kind": "bee", "name": e.bee_name,
			"role": BeeRole.names()[e.role], "personality": e.personality.to_dict(),
			"home_id": e.home.get_meta("id") if e.home else null})
	return d


func _cmd_list_entities(_args: Dictionary) -> Dictionary:
	return _ok(entities.values().map(_summary))


func _cmd_get_entity(args: Dictionary) -> Dictionary:
	var e = entities.get(args.get("id"))
	if e == null:
		return _err("unknown entity %s" % args.get("id"))
	var d := _summary(e)
	if e is Habitat:
		d["features"] = HabitatCatalog.features_of(e)
		d["description"] = HabitatCatalog.describe(e)
		d["occupant_ids"] = e.occupants.map(func(b): return b.get_meta("id"))
	else:
		d["seed"] = e.get_meta("seed")
		d["personality_source"] = e.get_meta("personality_source")
	return _ok(d)


# --- moving ----------------------------------------------------------------------------

func _cmd_move_entity(args: Dictionary) -> Dictionary:
	var e = entities.get(args.get("id"))
	if e == null:
		return _err("unknown entity %s" % args.get("id"))
	var pos_err := _position_error(args)
	if pos_err:
		return _err(pos_err)
	e.position = Vector2(args.x, args.y)
	_emit("entity_moved", {"id": args.id, "x": e.position.x, "y": e.position.y})
	return _ok(_summary(e))


# --- removing -------------------------------------------------------------------------

func _free_entity(e: Node2D) -> Array:
	var released := []
	if e is Habitat:
		for b: Bee in e.occupants.duplicate():
			b.home = null
			released.append(b.get_meta("id"))
		e.occupants.clear()
	elif e is Bee and e.home:
		e.home.occupants.erase(e)
		e.home = null
	entities.erase(e.get_meta("id"))
	world.remove_child(e)
	e.free()
	return released


func _cmd_remove_entity(args: Dictionary) -> Dictionary:
	var e = entities.get(args.get("id"))
	if e == null:
		return _err("unknown entity %s" % args.get("id"))
	var data := {"id": e.get_meta("id"), "kind": "habitat" if e is Habitat else "bee"}
	data["released_bee_ids"] = _free_entity(e)
	_emit("entity_removed", data)
	return _ok(data)


func _cmd_clear_world(_args: Dictionary) -> Dictionary:
	var count := entities.size()
	for e in entities.values():
		_free_entity(e)
	_emit("world_cleared", {"removed": count})
	return _ok({"removed": count})


# --- clock & events -------------------------------------------------------------------

func _cmd_pause(_args: Dictionary) -> Dictionary:
	if not paused:
		paused = true
		_emit("paused")
	return _ok({"paused": paused, "tick": tick})


func _cmd_resume(_args: Dictionary) -> Dictionary:
	if paused:
		paused = false
		_emit("resumed")
	return _ok({"paused": paused, "tick": tick})


func _cmd_set_speed(args: Dictionary) -> Dictionary:
	var s = args.get("speed")
	if typeof(s) not in [TYPE_INT, TYPE_FLOAT] or s < SPEED_MIN or s > SPEED_MAX:
		return _err("speed must be a number between %s and %s (got %s)" % [SPEED_MIN, SPEED_MAX, s])
	speed = float(s)
	Engine.physics_ticks_per_second = roundi(BASE_TICKS_PER_SECOND * speed)
	_emit("speed_changed", {"speed": speed})
	return _ok({"speed": speed})


func _cmd_get_events(args: Dictionary) -> Dictionary:
	var since = args.get("since", 0)
	if typeof(since) not in [TYPE_INT, TYPE_FLOAT] or since < 0 or since != floorf(since):
		return _err("since must be a non-negative integer")
	var oldest: int = events[0].seq if events else next_seq
	return _ok({
		"events": events.filter(func(ev): return ev.seq > since),
		"last_seq": next_seq - 1,
		"lost": since + 1 < oldest,  # the caller missed events dropped from the log
	})
