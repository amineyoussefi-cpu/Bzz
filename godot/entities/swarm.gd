class_name Swarm
extends RefCounted
## Swarm house-hunting, run tick by tick (docs/decision_agents_llm.md). Godot moves the bees, keeps the dances
## and counts the quorum. The three judgements (evaluate a site, judge the dances, stay or leave) are not made
## here: a bee asks them with a "decision_needed" event and waits; answer() brings the reply back
## (the backend asks the LLM brain, one call per decision: docs/methode_jeton.md).
##
## Flow: scouts fly to sites they have not seen -> evaluate -> stay or go back. A bee that stays is committed:
## it dances on the branch for its site, flies back to check it, dances again with less vigour (attrition) until
## it stops. Bees on the branch with nothing to explore judge the dances and may go and inspect a site
## themselves; a recruit that approves a site becomes a scout and dances too. When QUORUM bees are committed to
## one site, the whole swarm flies there and settles.

const SPEED := 1.6         # world units per tick (96 per second at speed x1)
const QUORUM := 3          # bees committed to one site -> the swarm moves there
const DANCE_TICKS := 180   # one dance on the branch
const WATCH_TICKS := 120   # a bee idle on the branch looks at the dances this often
const START_SPREAD := 120  # scouts leave the branch at random moments within this many ticks
const MIN_DANCE := 3       # a bee dances for its site while its vigour stays at least this (score 1-5)
const STRENGTH := {5: "very strongly", 4: "strongly", 3: "moderately"}
const KINDS := ["evaluate_site", "judge_dances", "stay_or_leave"]

enum State { RESTING, FLYING, WAITING, DANCING, AT_SITE, SETTLED }

var api  # WorldApi: entities, branch, tick, _emit (untyped to avoid a cyclic class reference)
var rng := RandomNumberGenerator.new()
var minds := {}  # bee id -> {state, perch, wake, purpose, target, goal, kind, situation, visited, site, score, level, until}
var chosen_id = null  # habitat the swarm decided on


func _init(p_api) -> void:
	api = p_api


func reset() -> void:
	minds.clear()
	chosen_id = null


func forget(id: String) -> void:
	minds.erase(id)


# --- reading ---------------------------------------------------------------------------

func mind(bee: Bee) -> Dictionary:
	var id: String = bee.get_meta("id")
	if id not in minds:
		minds[id] = {"state": State.RESTING, "perch": bee.position, "visited": {}, "site": null, "score": 0,
			"level": 0, "wake": api.tick + (rng.randi_range(0, START_SPREAD) if bee.role == BeeRole.Id.SCOUT else WATCH_TICKS),
			"purpose": "", "target": bee.position, "goal": null, "kind": "", "situation": {}, "until": 0}
	return minds[id]


## Extra fields for a bee's summary (list_entities, get_entity).
func bee_summary(bee: Bee) -> Dictionary:
	var m := mind(bee)
	return {"state": State.keys()[m.state].to_lower(), "site_id": m.site,
		"dance_level": m.level if m.state == State.DANCING else null,
		"waiting_for": m.kind if m.state == State.WAITING else null}


func committed(habitat_id: String) -> int:
	return minds.values().filter(func(m): return m.site == habitat_id).size()


func status() -> Dictionary:
	var waiting := minds.values().filter(func(m): return m.state == State.WAITING).size()
	var settled := minds.values().filter(func(m): return m.state == State.SETTLED).size()
	var phase := "searching"
	if chosen_id != null:
		phase = "settled" if settled > 0 and settled == minds.size() else "moving"
	return {"phase": phase, "chosen_id": chosen_id, "quorum": QUORUM, "dances": _dances().size(), "waiting": waiting}


# --- the clock -------------------------------------------------------------------------

func step() -> void:
	for bee in _bees():
		var m := mind(bee)
		match m.state:
			State.RESTING:
				_rest(bee, m)
			State.FLYING:
				_fly(bee, m)
			State.DANCING:
				if api.tick >= m.until:
					_fly_to(m, _site_spot(m.site), "revisit", m.site)


func _rest(bee: Bee, m: Dictionary) -> void:
	if chosen_id != null or api.tick < m.wake:
		return
	m.wake = api.tick + WATCH_TICKS
	if bee.role == BeeRole.Id.SCOUT and m.site == null:
		var unseen := _habitats().filter(func(h): return h.get_meta("id") not in m.visited)
		if not unseen.is_empty():  # explore: fly to a site this bee has not seen yet
			var h: Habitat = unseen[rng.randi_range(0, unseen.size() - 1)]
			_fly_to(m, _site_spot(h.get_meta("id")), "inspect", h.get_meta("id"))
			return
	var seen := _dance_situation(bee)
	if m.site == null and not seen.is_empty():
		_ask(bee, m, "judge_dances", {"dances": seen})


func _fly(bee: Bee, m: Dictionary) -> void:
	var to: Vector2 = m.target - bee.position
	if to.length() > SPEED:
		bee.position += to.normalized() * SPEED
		return
	bee.position = m.target
	var site = _habitat(m.goal)
	match m.purpose:
		"inspect":
			if site == null:
				_go_home(m)
			else:
				_ask(bee, m, "evaluate_site", {"habitat": _site_words(site)})
		"dance":
			m.state = State.DANCING
			m.until = api.tick + DANCE_TICKS
			api._emit("bee_danced", {"bee_id": bee.get_meta("id"), "habitat_id": m.site, "level": m.level})
		"revisit":  # back at its site after a dance: a bit less enthusiastic each time
			m.level -= 1
			if site != null and m.level >= MIN_DANCE and chosen_id == null:
				_fly_to(m, m.perch, "dance", m.site)
			else:
				m.state = State.AT_SITE
		"move_in":
			if site == null:  # the chosen site was removed on the way: search again
				chosen_id = null
				_go_home(m)
			else:
				m.state = State.SETTLED
				bee.home = site
				site.occupants.append(bee)
		_:
			m.state = State.RESTING


# --- decisions (asked to the brain) --------------------------------------------------------

func _ask(bee: Bee, m: Dictionary, kind: String, situation: Dictionary) -> void:
	m.state = State.WAITING
	m.kind = kind
	m.situation = situation
	api._emit("decision_needed", {"bee_id": bee.get_meta("id"), "kind": kind,
		"personality": bee.personality.to_dict(), "situation": situation})


## Applies the brain's answer to a waiting bee. "" if applied, else the reason it was refused.
func answer(bee: Bee, kind: String, a: Dictionary) -> String:
	var m := mind(bee)
	if m.state != State.WAITING or m.kind != kind:
		return "bee %s is not waiting for %s" % [bee.get_meta("id"), kind]
	match kind:
		"evaluate_site":
			var score = a.get("score")
			if typeof(score) not in [TYPE_INT, TYPE_FLOAT] or score != floorf(score) or score < 1 or score > 5:
				return "score must be an integer from 1 to 5"
			m.score = int(score)
			m.visited[m.goal] = m.score
			api._emit("bee_decided", {"bee_id": bee.get_meta("id"), "kind": kind, "habitat_id": m.goal, "answer": a})
			_ask(bee, m, "stay_or_leave", m.situation)  # second token: the bee decides what to do with its judgement
			return ""
		"stay_or_leave":
			var choice = a.get("choice")
			if choice not in ["stay", "go_back"]:
				return "choice must be stay or go_back"
			api._emit("bee_decided", {"bee_id": bee.get_meta("id"), "kind": kind, "habitat_id": m.goal, "answer": a})
			if choice == "stay" and _habitat(m.goal) != null:
				_commit(bee, m)
			else:
				_go_home(m)
		"judge_dances":
			var follow = a.get("follow")
			var offered: Array = m.situation.dances.map(func(d): return d.site_id)
			if follow != "none" and follow not in offered:
				return "follow must be none or one of %s" % [offered]
			api._emit("bee_decided", {"bee_id": bee.get_meta("id"), "kind": kind, "answer": a})
			if follow == "none" or _habitat(follow) == null:
				m.state = State.RESTING
			else:
				_fly_to(m, _site_spot(follow), "inspect", follow)
	return ""


func _commit(bee: Bee, m: Dictionary) -> void:
	m.site = m.goal
	m.level = m.score
	if bee.role == BeeRole.Id.FOLLOWER:
		bee.set_role(BeeRole.Id.SCOUT)  # a recruit that approves a site dances for it too
	api._emit("bee_committed", {"bee_id": bee.get_meta("id"), "habitat_id": m.site, "score": m.score})
	if committed(m.site) >= QUORUM:
		_choose(m.site)
	elif m.level >= MIN_DANCE:
		_fly_to(m, m.perch, "dance", m.site)
	else:
		m.state = State.AT_SITE


func _choose(habitat_id: String) -> void:
	chosen_id = habitat_id
	api._emit("swarm_decided", {"habitat_id": habitat_id, "committed": committed(habitat_id)})
	for bee in _bees():  # every bee leaves what it was doing, pending decisions included
		var m := mind(bee)
		if m.state != State.SETTLED:
			_fly_to(m, _site_spot(habitat_id), "move_in", habitat_id)


# --- helpers ---------------------------------------------------------------------------------

func _fly_to(m: Dictionary, target: Vector2, purpose: String, goal) -> void:
	m.state = State.FLYING
	m.target = target
	m.purpose = purpose
	m.goal = goal


func _go_home(m: Dictionary) -> void:
	_fly_to(m, m.perch, "rest", null)


func _site_spot(habitat_id: String) -> Vector2:  # around the site, so bees there do not stack on one point
	var h = _habitat(habitat_id)
	var center: Vector2 = h.position if h else api.branch
	return (center + Vector2.from_angle(rng.randf() * TAU) * rng.randf_range(4, 14)).clamp(Vector2.ZERO, api.size)


func _site_words(h: Habitat) -> Dictionary:
	return {"id": h.get_meta("id"), "description": HabitatCatalog.describe(h)}


func _dances() -> Array:
	return _bees().filter(func(b): return mind(b).state == State.DANCING)


## What a bee on the branch sees: each dance with its vigour and the direction of the site.
func _dance_situation(watcher: Bee) -> Array:
	var out := []
	for b in _dances():
		var m := mind(b)
		var h = _habitat(m.site)
		if b != watcher and h != null:
			out.append({"site_id": m.site, "strength": STRENGTH[clampi(m.level, MIN_DANCE, 5)],
				"direction": _direction(h.position - api.branch)})
	return out


func _direction(v: Vector2) -> String:
	if absf(v.x) > absf(v.y):
		return "to the east" if v.x > 0 else "to the west"
	return "to the south" if v.y > 0 else "to the north"


func _bees() -> Array:
	return api.entities.values().filter(func(e): return e is Bee)


func _habitats() -> Array:
	return api.entities.values().filter(func(e): return e is Habitat)


func _habitat(id):
	var h = api.entities.get(id) if id != null else null
	return h if h is Habitat else null
