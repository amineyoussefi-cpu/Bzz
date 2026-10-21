class_name WorldApi
extends RefCounted
## World toolbox behind the TCP protocol: catalogue, adding/removing habitats, bees and swarms,
## simulation clock (pause/resume/speed, simulated days), flights, and the event log polled by the backend.
## Decisions are taken outside Godot (backend + OpenJev): Godot describes the situation, validates and applies them.
## The original choice logic (Bee.score_breakdown / choose_habitat) only runs in reference_decision, for comparison.
## Role behaviors are not executed, except QueenBehavior.move_to_habitat (the swarm's flight).
## Commands are documented in docs/api.md.

const DEFAULT_SIZE := Vector2(1000, 700)  # world size unless --world-width/--world-height are given
const EVENT_LOG_SIZE := 1000
const BASE_TICKS_PER_SECOND := 60
const SPEED_MIN := 0.25
const SPEED_MAX := 8.0
const MAX_NAME_LENGTH := 40
const SWARM_POPULATION := {"min": 1000, "max": 50000, "default": 10000}  # workers; ~10,000 typical (Seeley)

## Tunable parameters: the single source of their defaults. Override with --day-ticks=... etc.
## (main.gd), fed from the environment (.env.example: DAY_TICKS, FLIGHT_SPEED_FACTOR, ...).
const DEFAULT_CONFIG := {
	"day_ticks": 3600.0,          # ticks in one simulated day (1 real minute at speed x1)
	"flight_speed_factor": 0.05,  # world units per tick for 1 m/s: game scale that keeps flights visible
	"swarm_speed_mps": 2.7,       # swarm cruising speed, ~9.7 km/h
	"swarm_cluster_days": 3.0,    # days a swarm can hang on its branch before nesting in the open
}

## Allowed arguments per command (the Python whitelist in backend/bzz/commands.py mirrors it).
const ARGS := {
	"get_state": [], "get_catalog": [], "list_entities": [], "clear_world": [], "pause": [], "resume": [],
	"add_habitat": ["type", "x", "y", "features"],
	"add_bee": ["species", "x", "y", "personality", "name", "role"],
	"add_swarm": ["x", "y", "population", "personality", "name"],
	"get_entity": ["id"], "remove_entity": ["id"],
	"set_speed": ["speed"], "get_events": ["since"],
	"get_decision_situation": ["bee_id"], "apply_decision": ["bee_id", "habitat_id", "decision"],
	"reference_decision": ["bee_id", "habitat_ids"],
}

var world: Node2D
var size := DEFAULT_SIZE
var entities := {}  # id -> Habitat | Bee | Swarm, in creation order
var next_id := 1    # never reset, so ids stay unique for the whole run
var tick := 0       # simulation time: advances only while running
var paused := true  # the world is built paused, then resumed
var speed := 1.0
var events: Array[Dictionary] = []
var next_seq := 1
var config := DEFAULT_CONFIG.duplicate()
var display := "headless"  # "window" when main.gd opened the read-only WorldView


## "" if every key is a known parameter with a positive number, else the error message.
static func config_error(overrides: Dictionary) -> String:
	for key in overrides:
		if key not in DEFAULT_CONFIG:
			return "unknown parameter %s; accepted: %s" % [key, ", ".join(DEFAULT_CONFIG.keys())]
		if not str(overrides[key]).is_valid_float() or float(overrides[key]) <= 0:
			return "%s must be a positive number (got %s)" % [key, overrides[key]]
	return ""


func _init(p_world: Node2D, p_size := DEFAULT_SIZE, overrides := {}) -> void:
	world = p_world
	size = p_size
	for key in overrides:
		config[key] = float(overrides[key])


## World units per tick for a flight speed in m/s.
func _units_per_tick(mps: float) -> float:
	return mps * config.flight_speed_factor


## Called every physics frame: advances time, flights and swarm delays (nothing moves while paused).
func step() -> void:
	if paused:
		return
	tick += 1
	for e in entities.values():
		if e is Habitat:
			continue
		if e.flight:
			if e.flight.advance(e):
				_arrive(e)
		elif e is Swarm and e.state() == Swarm.State.CLUSTER:
			e.cluster_ticks_left -= 1
			if e.cluster_ticks_left <= 0:
				e.exposed = true
				_emit("swarm_exposed", {"id": e.get_meta("id"), "x": e.position.x, "y": e.position.y,
					"population": e.population})


## Settles on arrival; a full habitat makes the arrival fail (bee searches again, swarm clusters again).
func _arrive(e: Node2D) -> void:
	var h: Habitat = e.flight.target
	var data := {"id": e.get_meta("id"), "kind": _kind(e), "habitat_id": h.get_meta("id"),
		"flight_ticks": e.flight.ticks}
	e.flight = null
	if e.settle(h):
		data["found_after_days"] = (tick - e.get_meta("added_tick")) / config.day_ticks
		_emit("arrived", data)
	else:
		data["reason"] = "full" if h.is_full() else "not accepted"
		if e is Swarm:
			e.cluster_here()
		_emit("arrival_failed", data)


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
	var swarms := entities.values().filter(func(e): return e is Swarm).size()
	return _ok({
		"physics_frames": Engine.get_physics_frames(),
		"process_frames": Engine.get_process_frames(),
		"node_count": world.get_child_count(),
		"tick": tick, "paused": paused, "speed": speed,
		"ticks_per_second": BASE_TICKS_PER_SECOND,
		"world": {"width": size.x, "height": size.y},
		"habitats": habitats, "bees": entities.size() - habitats - swarms, "swarms": swarms,
		"day_ticks": config.day_ticks,
		"display": display,
		"view_loaded": ResourceLoader.has_cached("res://view/world_view.gd"),
		"last_event_seq": next_seq - 1,
	})


func _cmd_get_catalog(_args: Dictionary) -> Dictionary:
	var habitat_types := []
	for t in Habitat.Type.values():
		habitat_types.append({"name": HabitatCatalog.type_name(t), "defaults": HabitatCatalog.defaults(t)})
	var species := []
	for id in BeeSpecies.Id.values():
		species.append({
			"name": BeeSpecies.species_name(id),
			"accepted_habitat_types": BeeSpecies.accepted_types(id).map(func(t): return HabitatCatalog.type_name(t)),
			"preferences": BeeSpecies.default_preferences(id).map(_pref_dict),
			"flight_speed_mps": BeeSpecies.flight_speed_mps(id),
			"flight_speed_sourced": BeeSpecies.flight_speed_sourced(id),
			"lives_in_swarms": BeeSpecies.lives_in_swarms(id),
		})
	return _ok({
		"habitat_types": habitat_types,
		"features": HabitatCatalog.FEATURES,
		"species": species,
		"roles": BeeRole.names(),
		"default_role": BeeRole.names()[BeeRole.Id.FOLLOWER],
		"traits": BeePersonality.TRAITS.map(func(t): return {"name": t, "min": 0.0, "max": 1.0}),
		"presets": BeePersonality.PRESETS,
		"world": {"width": size.x, "height": size.y},
		"speed": {"min": SPEED_MIN, "max": SPEED_MAX, "default": 1.0},
		"ticks_per_second": BASE_TICKS_PER_SECOND,
		"max_name_length": MAX_NAME_LENGTH,
		"time": {"day_ticks": config.day_ticks, "flight_speed_factor": config.flight_speed_factor},
		"swarm": {"species": BeeSpecies.species_name(BeeSpecies.Id.HONEY_BEE), "population": SWARM_POPULATION,
			"speed_mps": config.swarm_speed_mps, "cluster_days": config.swarm_cluster_days},
	})


func _pref_dict(p: Preference) -> Dictionary:
	return {"criterion": p.criterion, "ideal": p.ideal, "tolerance": p.tolerance, "weight": p.weight}


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
	var species_name = args.get("species")
	var species := BeeSpecies.from_name(species_name) if typeof(species_name) == TYPE_STRING else -1
	if species == -1:
		return _err("unknown species %s; accepted: %s" % [species_name, ", ".join(BeeSpecies.names())])
	if BeeSpecies.lives_in_swarms(species):
		return _err("%s lives in swarms: use add_swarm instead of add_bee" % species_name)
	var pos_err := _position_error(args)
	if pos_err:
		return _err(pos_err)
	var name_err := _name_error(args)
	if name_err:
		return _err(name_err)
	var role := BeeRole.Id.FOLLOWER
	if "role" in args:
		role = BeeRole.from_name(args.role) if typeof(args.role) == TYPE_STRING else -1
		if role == -1:
			return _err("unknown role %s; accepted: %s" % [args.role, ", ".join(BeeRole.names())])
	var parsed := _parse_personality(args.get("personality", {"random": true}))
	if "error" in parsed:
		return _err(parsed.error)

	var bee := Bee.create(species, parsed.personality, parsed.seed)
	bee.bee_name = args.get("name", "")
	if role != bee.role:
		bee.set_role(role)
	bee.flight_speed = _units_per_tick(BeeSpecies.flight_speed_mps(species))
	bee.set_meta("seed", parsed.seed)
	bee.set_meta("personality_source", parsed.source)
	_register(bee, "bee", Vector2(args.x, args.y))
	var summary := _summary(bee)
	_emit("entity_added", summary)
	return _ok(summary)


func _name_error(args: Dictionary) -> String:
	var n = args.get("name", "")
	if typeof(n) != TYPE_STRING or n.length() > MAX_NAME_LENGTH:
		return "name must be a string of at most %d characters" % MAX_NAME_LENGTH
	return ""


## A honey bee swarm clustered on a branch at (x, y), with its queen and a collective personality.
func _cmd_add_swarm(args: Dictionary) -> Dictionary:
	var pos_err := _position_error(args)
	if pos_err:
		return _err(pos_err)
	var pop = args.get("population")
	if typeof(pop) not in [TYPE_INT, TYPE_FLOAT] or pop != floorf(pop) \
			or pop < SWARM_POPULATION.min or pop > SWARM_POPULATION.max:
		return _err("population must be an integer between %d and %d (got %s)" % [SWARM_POPULATION.min, SWARM_POPULATION.max, pop])
	var name_err := _name_error(args)
	if name_err:
		return _err(name_err)
	var parsed := _parse_personality(args.get("personality", {"random": true}))
	if "error" in parsed:
		return _err(parsed.error)

	var s := Swarm.create(int(pop), parsed.personality, roundi(config.swarm_cluster_days * config.day_ticks), parsed.seed)
	s.swarm_name = args.get("name", "")
	s.flight_speed = _units_per_tick(config.swarm_speed_mps)
	s.set_meta("seed", parsed.seed)
	s.set_meta("personality_source", parsed.source)
	_register(s, "swarm", Vector2(args.x, args.y))
	s.cluster_position = s.position
	var summary := _summary(s)
	_emit("entity_added", summary)
	return _ok(summary)


## {"personality": BeePersonality|null, "seed": int, "source": String} or {"error": String}.
## Forms: {"preset": name} | {"traits": {...}} | {"random": true}, each with an optional "seed" (int >= 1)
## that seeds the bee's random generator (random traits, curiosity noise), so the same bee can be recreated.
func _parse_personality(p) -> Dictionary:
	const FORMS := "personality must be {\"preset\": name}, {\"traits\": {...}} or {\"random\": true}, plus an optional \"seed\""
	if typeof(p) != TYPE_DICTIONARY or p.size() == 0:
		return {"error": FORMS}
	var seed_value := randi_range(1, 2147483647)  # a fresh seed is always recorded, so any bee can be reproduced
	if "seed" in p:
		if typeof(p.seed) not in [TYPE_INT, TYPE_FLOAT] or p.seed != floorf(p.seed) or p.seed < 1 or p.seed > 2147483647:
			return {"error": "seed must be an integer between 1 and 2147483647"}
		seed_value = int(p.seed)
	var forms := ["preset", "traits", "random"].filter(func(k): return k in p)
	if forms.size() != 1:
		return {"error": FORMS}
	for key in p:
		if key not in [forms[0], "seed"]:
			return {"error": "unexpected personality key %s" % key}
	match forms[0]:
		"preset":
			if typeof(p.preset) != TYPE_STRING or p.preset not in BeePersonality.PRESETS:
				return {"error": "unknown personality preset %s; accepted: %s" % [p.preset, ", ".join(BeePersonality.PRESETS.keys())]}
			return {"personality": BeePersonality.from_traits(BeePersonality.PRESETS[p.preset]), "seed": seed_value, "source": "preset:" + p.preset}
		"traits":
			if typeof(p.traits) != TYPE_DICTIONARY:
				return {"error": "traits must be an object"}
			var err := BeePersonality.validate_traits(p.traits)
			if err:
				return {"error": err}
			return {"personality": BeePersonality.from_traits(p.traits), "seed": seed_value, "source": "traits"}
	if p.random != true:
		return {"error": FORMS}
	return {"personality": null, "seed": seed_value, "source": "random"}


func _register(node: Node2D, prefix: String, pos: Vector2) -> void:
	var id := "%s-%d" % [prefix, next_id]
	next_id += 1
	node.set_meta("id", id)
	node.name = id
	node.position = pos
	node.set_meta("added_tick", tick)
	world.add_child(node)
	entities[id] = node


# --- reading -----------------------------------------------------------------------

func _kind(e: Node2D) -> String:
	return "habitat" if e is Habitat else "swarm" if e is Swarm else "bee"


## The Bee whose preferences and personality judge habitats: the bee itself, or a swarm's queen.
func _judge(e: Node2D) -> Bee:
	return e.queen if e is Swarm else e


## True if some habitat in the world has a type `e` accepts and a free place.
func _has_compatible_habitat(e: Node2D) -> bool:
	var types: Array = _judge(e).accepted_types
	return entities.values().any(func(h): return h is Habitat and h.habitat_type in types and not h.is_full())


## searching | waiting (no compatible habitat) | flying | settled, and for swarms cluster | flying | settled | exposed.
func _state(e: Node2D) -> String:
	if e is Swarm:
		return Swarm.State.keys()[e.state()].to_lower()
	if e.home:
		return "settled"
	if e.flight:
		return "flying"
	return "searching" if _has_compatible_habitat(e) else "waiting"


func _summary(e: Node2D) -> Dictionary:
	var d := {"id": e.get_meta("id"), "kind": _kind(e), "x": e.position.x, "y": e.position.y}
	if e is Habitat:
		d.merge({"type": HabitatCatalog.type_name(e.habitat_type), "capacity": e.capacity, "occupants": e.occupants.size()})
		return d
	d.merge({"state": _state(e), "personality": _judge(e).personality.to_dict(),
		"home_id": e.home.get_meta("id") if e.home else null})
	if e is Swarm:
		d.merge({"species": BeeSpecies.species_name(BeeSpecies.Id.HONEY_BEE), "name": e.swarm_name,
			"population": e.population, "days_left": e.cluster_ticks_left / config.day_ticks,
			"cluster_x": e.cluster_position.x, "cluster_y": e.cluster_position.y,
			"waiting": e.state() == Swarm.State.CLUSTER and not _has_compatible_habitat(e)})
	else:
		d.merge({"species": BeeSpecies.species_name(e.species), "name": e.bee_name, "role": BeeRole.names()[e.role]})
	if e.flight:
		d.merge({"target_id": e.flight.target.get_meta("id"), "target_x": e.flight.target.position.x,
			"target_y": e.flight.target.position.y, "speed": e.flight.speed, "flight_ticks": e.flight.ticks})
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
		d["occupant_ids"] = e.occupants.map(func(b): return b.get_meta("id"))
	else:
		var judge := _judge(e)
		d["accepted_habitat_types"] = judge.accepted_types.map(func(t): return HabitatCatalog.type_name(t))
		d["preferences"] = judge.preferences.map(_pref_dict)
		d["seed"] = e.get_meta("seed")
		d["personality_source"] = e.get_meta("personality_source")
		if e is Swarm:
			var q: QueenBehavior = e.queen.behavior
			d["queen"] = {"role": "queen", "target_habitat_id": q.target_habitat.get_meta("id") if q.target_habitat else null,
				"decision_support": q.decision.support if q.decision else null}
	return _ok(d)


# --- removing -------------------------------------------------------------------------

func _free_entity(e: Node2D) -> Array:
	var released := []
	if e is Habitat:
		for o in e.occupants.duplicate():  # bees search again, swarms hang again where they are
			o.leave_home()
			if o is Swarm:
				o.cluster_here()
			released.append(o.get_meta("id"))
		for f in entities.values():  # flights toward it stop on the spot
			if not f is Habitat and f.flight and f.flight.target == e:
				var data := {"id": f.get_meta("id"), "kind": _kind(f), "habitat_id": e.get_meta("id"),
					"flight_ticks": f.flight.ticks, "reason": "removed"}
				f.flight = null
				if f is Swarm:
					f.cluster_here()
				_emit("arrival_failed", data)
	else:
		e.leave_home()
	entities.erase(e.get_meta("id"))
	world.remove_child(e)
	e.free()
	return released


func _cmd_remove_entity(args: Dictionary) -> Dictionary:
	var e = entities.get(args.get("id"))
	if e == null:
		return _err("unknown entity %s" % args.get("id"))
	var data := {"id": e.get_meta("id"), "kind": _kind(e)}
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


# --- decisions ------------------------------------------------------------------------
# A "decider" is an individual Bee or a Swarm (whose queen carries the preferences and personality).

func _decider(id) -> Node2D:
	var e = entities.get(id)
	return e if e is Bee or e is Swarm else null


## Everything a decision maker needs about one bee or swarm and every habitat
## (eligible = type accepted and not full; distance from the bee, or from the swarm's cluster).
func _cmd_get_decision_situation(args: Dictionary) -> Dictionary:
	var e := _decider(args.get("bee_id"))
	if e == null:
		return _err("unknown bee or swarm %s" % args.get("bee_id"))
	var judge := _judge(e)
	var b := _summary(e)
	b.merge({"accepted_habitat_types": judge.accepted_types.map(func(t): return HabitatCatalog.type_name(t)),
		"preferences": judge.preferences.map(_pref_dict),
		"acceptance_threshold": judge.personality.acceptance_threshold()})
	var habitats := []
	for h in entities.values():
		if h is Habitat:
			var d := _summary(h)
			var accepted: bool = h.habitat_type in judge.accepted_types
			d.merge({"features": HabitatCatalog.features_of(h), "distance": e.position.distance_to(h.position),
				"type_accepted": accepted, "full": h.is_full(), "eligible": accepted and not h.is_full()})
			habitats.append(d)
	return _ok({"tick": tick, "paused": paused, "day_ticks": config.day_ticks, "bee": b, "habitats": habitats})


## Validates then applies a decision: the bee (or the whole swarm, led by its queen through a ColonyDecision)
## takes off toward the habitat and settles only on arrival. The habitat is not reserved during the flight.
## Every decision (applied, refused or rejected) becomes a "decision" event; `habitat_id` null = no habitat chosen.
## Nothing is applied while the simulation is paused.
func _cmd_apply_decision(args: Dictionary) -> Dictionary:
	if paused:
		return _err("simulation is paused: decision not applied")
	for key in ["bee_id", "habitat_id"]:
		if key not in args:
			return _err("missing %s" % key)
	var info = args.get("decision", {})
	if typeof(info) != TYPE_DICTIONARY:
		return _err("decision must be an object")
	var event := DecisionEvent.from_dict(info)
	event.bee_id = str(args.bee_id)
	var habitat_id = args.habitat_id
	var e := _decider(args.bee_id)
	var error := ""
	var h = entities.get(habitat_id) if typeof(habitat_id) == TYPE_STRING else null
	if e == null:
		error = "unknown bee or swarm %s" % args.bee_id
	elif e.home != null:
		error = "%s already lives in %s" % [args.bee_id, e.home.get_meta("id")]
	elif e.flight != null:
		error = "%s is already flying to %s" % [args.bee_id, e.flight.target.get_meta("id")]
	elif e is Swarm and e.exposed:
		error = "swarm %s has nested in the open" % args.bee_id
	elif habitat_id != null and typeof(habitat_id) != TYPE_STRING:
		error = "habitat_id must be a string or null"
	elif habitat_id != null and not h is Habitat:
		error = "unknown habitat %s" % habitat_id
	elif habitat_id != null and h.habitat_type not in _judge(e).accepted_types:
		error = "%s does not accept habitat type %s" % [BeeSpecies.species_name(_judge(e).species), HabitatCatalog.type_name(h.habitat_type)]
	elif habitat_id != null and h.is_full():
		error = "habitat %s is full" % habitat_id
	if error:
		event.chosen_habitat_id = null
		event.result = "rejected"
		event.reason = "rejected by Godot: %s (proposed %s)" % [error, habitat_id]
		_emit("decision", event.to_dict())
		return _err(error)
	event.chosen_habitat_id = habitat_id
	event.result = "none" if habitat_id == null else "flying"
	_emit("decision", event.to_dict())
	if habitat_id != null:
		var origin: Vector2 = e.position
		if e is Swarm:
			var queen: QueenBehavior = e.queen.behavior
			queen.follow_colony_decision(ColonyDecision.make(h, e.population))
			queen.move_to_habitat(h)
		else:
			e.fly_to(h)
		_emit("flight_started", {"id": e.get_meta("id"), "kind": _kind(e), "habitat_id": habitat_id,
			"from_x": origin.x, "from_y": origin.y, "to_x": h.position.x, "to_y": h.position.y,
			"distance": origin.distance_to(h.position), "speed": e.flight.speed})
	return _ok({"bee_id": event.bee_id, "habitat_id": habitat_id, "result": event.result})


## The original choice logic, for comparison only: scores and choice, never applied.
## For a swarm it judges with the queen's preferences and personality, ignoring the delay and the distance.
## Curiosity noise is drawn per evaluation, so the choice may occasionally differ from the best listed score.
func _cmd_reference_decision(args: Dictionary) -> Dictionary:
	var e := _decider(args.get("bee_id"))
	if e == null:
		return _err("unknown bee or swarm %s" % args.get("bee_id"))
	var bee := _judge(e)
	var ids = args.get("habitat_ids")
	if typeof(ids) != TYPE_ARRAY:
		return _err("habitat_ids must be a list")
	var habitats := []
	for id in ids:
		if not entities.get(id) is Habitat:
			return _err("unknown habitat %s" % id)
		habitats.append(entities[id])
	var scores := []
	for h in habitats:
		var bd: Dictionary = bee.score_breakdown(h)
		var total: float = bd.total
		bd.erase("total")
		scores.append({"habitat_id": h.get_meta("id"), "score": total, "breakdown": bd})
	var choice: Habitat = bee.choose_habitat(habitats)
	return _ok({"choice": choice.get_meta("id") if choice else null, "scores": scores,
		"threshold": bee.personality.acceptance_threshold()})
