extends SceneTree
## Unit checks for the bee/habitat model. Run (after an import so class_name is registered):
##   godot --headless --path godot --import && godot --headless --path godot --script res://tests/test_entities.gd

var failures := 0


func check(cond: bool, what: String) -> void:
	if not cond:
		failures += 1
		printerr("FAIL: ", what)


func calm() -> BeePersonality:
	var p := BeePersonality.new()
	p.curiosity = 0.0  # deterministic scores
	return p


func cavity(volume: float, entrance: float, height: float) -> Habitat:
	var h := Habitat.new()
	h.habitat_type = Habitat.Type.TREE_CAVITY
	h.cavity_volume_l = volume
	h.entrance_diameter_mm = entrance
	h.entrance_height_m = height
	h.floral_abundance = 1.0
	return h


func _init() -> void:
	var p := Preference.make("x", 10, 5)
	check(p.score(10) == 1.0 and p.score(12.5) == 0.5 and p.score(20) == 0.0, "triangular preference score")

	var bee := Bee.create(BeeSpecies.Id.HONEY_BEE, calm())
	var ideal := cavity(40, 40, 5)
	var small := cavity(10, 40, 5)
	var huge := cavity(100, 40, 5)
	check(bee.evaluate_habitat(ideal) > bee.evaluate_habitat(small), "honey bee: 40 L beats 10 L")
	check(bee.evaluate_habitat(ideal) > bee.evaluate_habitat(huge), "honey bee: 40 L beats 100 L")
	check(bee.choose_habitat([small, huge, ideal]) == ideal, "honey bee picks the ideal cavity")

	var soil := Habitat.new()
	soil.habitat_type = Habitat.Type.BARE_SOIL
	check(bee.evaluate_habitat(soil) == 0.0, "honey bee rejects bare soil")

	check(bee.settle(ideal) and bee.home == ideal and ideal.is_full(), "settle fills a single-capacity cavity")
	var other := Bee.create(BeeSpecies.Id.HONEY_BEE, calm())
	check(other.evaluate_habitat(ideal) == 0.0 and not other.settle(ideal), "full habitat is unusable for others")
	bee.leave_home()
	check(not ideal.is_full() and bee.home == null, "leave_home frees the habitat")

	var picky := calm()
	picky.pickiness = 1.0
	check(Bee.create(BeeSpecies.Id.HONEY_BEE, picky).choose_habitat([small]) == null, "picky bee refuses a poor site")

	var risky := cavity(40, 40, 5)
	risky.predator_risk = 1.0
	var bold := calm()
	bold.boldness = 1.0
	var shy := calm()
	shy.boldness = 0.0
	check(Bee.create(BeeSpecies.Id.HONEY_BEE, bold).evaluate_habitat(risky)
		> Bee.create(BeeSpecies.Id.HONEY_BEE, shy).evaluate_habitat(risky), "boldness reduces predator penalty")

	var bank := Habitat.new()
	bank.habitat_type = Habitat.Type.BARE_SOIL
	bank.capacity = 50
	bank.sun_exposure = 1.0
	bank.humidity = 0.2
	var empty_score := Bee.create(BeeSpecies.Id.MINING_BEE, calm()).evaluate_habitat(bank)
	for i in 25:
		bank.occupants.append(Bee.create(BeeSpecies.Id.MINING_BEE, calm()))
	var social := calm()
	social.sociability = 1.0
	check(Bee.create(BeeSpecies.Id.MINING_BEE, social).evaluate_habitat(bank) > empty_score, "sociable bee likes aggregations")

	for id in BeeSpecies.Id.values():
		var b := Bee.create(id, null, 42)
		check(not b.accepted_types.is_empty() and not b.preferences.is_empty(), "species %d has defaults" % id)
		for pref in b.preferences:
			check(pref.criterion in Habitat.new().features(), "criterion %s exists" % pref.criterion)

	test_roles()
	test_world_api()
	test_flights_and_swarms()
	test_window_view()
	print("entity tests: %s" % ("OK" if failures == 0 else "%d failure(s)" % failures))
	quit(1 if failures else 0)


func test_roles() -> void:
	var expected := {
		BeeRole.Id.SCOUT: ["explore_habitats", "evaluate_habitat", "remember_habitat", "return_to_colony", "perform_dance"],
		BeeRole.Id.FOLLOWER: ["receive_dance", "evaluate_signal", "decide_to_follow", "visit_habitat", "evaluate_habitat"],
		BeeRole.Id.QUEEN: ["receive_colony_decision", "follow_colony_decision", "move_to_habitat", "lay_eggs",
			"manage_reproduction_cycle"],
	}
	check(BeeRole.Id.size() == 3, "exactly three roles")
	# roles are species-independent: every species gets every role with the same interface
	for species in BeeSpecies.Id.values():
		var bee := Bee.create(species, calm())
		check(bee.role == BeeRole.Id.FOLLOWER and bee.behavior is FollowerBehavior, "default role is follower")
		for id in expected:
			bee.set_role(id)
			check(bee.role == id and bee.behavior.role() == id and bee.behavior.bee == bee, "set_role %s" % BeeRole.role_name(id))
			check(Array(bee.behavior.actions()) == expected[id], "%s action list" % BeeRole.role_name(id))
			for action in expected[id]:
				check(bee.behavior.has_method(action), "%s has %s()" % [BeeRole.role_name(id), action])

	# the queen never selects a habitat on her own
	var queen := Bee.create(BeeSpecies.Id.HONEY_BEE, calm())
	queen.set_role(BeeRole.Id.QUEEN)
	for forbidden in ["evaluate_habitat", "explore_habitats", "choose_habitat"]:
		check(not queen.behavior.has_method(forbidden), "queen behavior has no %s()" % forbidden)

	# evaluation is delegated to Bee, not duplicated
	var site := cavity(40, 40, 5)
	site.position = Vector2(30, 40)
	var scout := Bee.create(BeeSpecies.Id.HONEY_BEE, calm())
	scout.set_role(BeeRole.Id.SCOUT)
	check(scout.behavior.evaluate_habitat(site) == scout.evaluate_habitat(site), "scout evaluation reuses Bee")
	scout.behavior.remember_habitat(site)
	check(site in scout.behavior.known_habitats, "scout remembers habitat")
	var dance: DanceSignal = scout.behavior.perform_dance(site)
	check(dance.scout == scout and dance.habitat == site and dance.location == site.position
		and dance.quality == scout.evaluate_habitat(site), "dance signal carries habitat and quality")

	# interface-only actions change nothing in the world
	check(scout.behavior.explore_habitats().is_empty(), "explore_habitats finds nothing yet")
	var follower := Bee.create(BeeSpecies.Id.HONEY_BEE, calm())
	follower.behavior.receive_dance(dance)
	check(follower.behavior.received_signals == [dance], "follower stores received dance")
	check(not follower.behavior.decide_to_follow(dance), "decide_to_follow not implemented yet")
	follower.behavior.visit_habitat(site)
	check(follower.position == Vector2.ZERO and follower.home == null, "visit_habitat does not move")

	var decision := ColonyDecision.make(site, 20)
	queen.behavior.follow_colony_decision(decision)
	check(queen.behavior.decision == decision and queen.behavior.target_habitat == site, "queen adopts colony decision")
	queen.behavior.move_to_habitat(site)
	queen.behavior.lay_eggs()
	queen.behavior.manage_reproduction_cycle()
	check(queen.flight != null and queen.flight.target == site and queen.home == null and site.occupants.is_empty(),
		"move_to_habitat starts a flight (settling waits for the arrival); laying creates no bee")


func test_world_api() -> void:
	var world := Node2D.new()
	var api := WorldApi.new(world)
	var h = api.handle("add_habitat", {"type": "bare_soil", "x": 10, "y": 10}).result
	var b = api.handle("add_bee", {"species": "mining_bee", "x": 20, "y": 20}).result
	check(world.get_child_count() == 2 and h.id != b.id, "entities added as world children with unique ids")
	check(not api.handle("add_bee", {"species": "mining_bee", "x": 20, "y": 9999}).ok and world.get_child_count() == 2,
		"refused command creates nothing")

	# removing a habitat releases its occupants (settled by hand here: no command or loop ever settles a bee)
	var bee: Bee = api.entities[b.id]
	var habitat: Habitat = api.entities[h.id]
	bee.settle(habitat)
	var removed = api.handle("remove_entity", {"id": h.id}).result
	check(removed.released_bee_ids == [b.id] and bee.home == null and world.get_child_count() == 1,
		"removing a habitat frees its occupants")

	var tick := api.tick
	api.step()
	check(api.tick == tick, "paused world does not advance")
	api.handle("resume", {})
	api.step()
	check(api.tick == tick + 1, "running world advances one tick per physics frame")
	check(api.handle("clear_world", {}).result.removed == 1 and world.get_child_count() == 0, "clear_world empties")
	var types: Array = api.handle("get_events", {}).result.events.map(func(e): return e.type)
	check(types == ["entity_added", "entity_added", "entity_removed", "resumed", "world_cleared"], "event log %s" % [types])
	check("decision" not in types, "no decision event")
	world.free()


func test_flights_and_swarms() -> void:
	var world := Node2D.new()
	# 1 m/s = 1 unit/tick; a day lasts 100 ticks; swarms wait half a day (50 ticks) and fly at 5 units/tick
	var api := WorldApi.new(world, WorldApi.DEFAULT_SIZE,
		{"flight_speed_factor": 1.0, "day_ticks": 100.0, "swarm_cluster_days": 0.5, "swarm_speed_mps": 5.0})
	var add := func(cmd: String, args: Dictionary): return api.handle(cmd, args)
	var decide := func(id: String, hab): return api.handle("apply_decision", {"bee_id": id, "habitat_id": hab})

	check(not add.call("add_bee", {"species": "honey_bee", "x": 1, "y": 1}).ok
		and "add_swarm" in add.call("add_bee", {"species": "honey_bee", "x": 1, "y": 1}).error, "honey bees only as swarms")

	# --- a bee flies in a straight line and settles only on arrival (mining bee: 3 m/s -> 3 units/tick)
	var soil = add.call("add_habitat", {"type": "bare_soil", "x": 40, "y": 10}).result
	var b = add.call("add_bee", {"species": "mining_bee", "x": 10, "y": 10}).result
	var bee: Bee = api.entities[b.id]
	check(api._summary(bee).state == "searching", "new bee is searching")
	api.handle("resume", {})
	check(decide.call(b.id, soil.id).result.result == "flying" and api._summary(bee).state == "flying", "decision starts a flight")
	for i in 9:
		api.step()
	check(bee.home == null and is_equal_approx(bee.position.x, 37.0), "not settled during the flight (30 units = 10 ticks)")
	api.step()
	check(bee.home == api.entities[soil.id] and bee.position == Vector2(40, 10) and api._summary(bee).state == "settled",
		"settles on arrival, after exactly 10 ticks")
	var arrived: Array = api.events.filter(func(e): return e.type == "arrived")
	check(arrived.size() == 1 and arrived[0].data.flight_ticks == 10, "arrived event with flight duration")

	# --- pause stops the flight
	var b2 = add.call("add_bee", {"species": "mining_bee", "x": 40, "y": 70}).result
	decide.call(b2.id, soil.id)
	api.step()
	api.handle("pause", {})
	var bee2: Bee = api.entities[b2.id]
	var frozen := bee2.position
	for i in 5:
		api.step()
	check(bee2.position == frozen and bee2.flight.ticks == 1, "paused: no movement")
	api.handle("resume", {})

	# --- habitat full on arrival: no reservation, the late bee searches again
	var wood = add.call("add_habitat", {"type": "dead_wood", "x": 300, "y": 300, "features": {"capacity": 1}}).result
	var c1 = add.call("add_bee", {"species": "carpenter_bee", "x": 296, "y": 300}).result
	var c2 = add.call("add_bee", {"species": "carpenter_bee", "x": 200, "y": 300}).result
	decide.call(c1.id, wood.id)
	decide.call(c2.id, wood.id)  # still free when c2 decides
	for i in 30:
		api.step()
	var late: Bee = api.entities[c2.id]
	var failed: Array = api.events.filter(func(e): return e.type == "arrival_failed")
	check(late.home == null and late.flight == null and late.position == Vector2(300, 300)
		and failed.size() == 1 and failed[0].data.reason == "full", "full on arrival -> arrival_failed")
	check(api._summary(late).state == "waiting", "no compatible habitat left -> waiting")

	# --- habitat removed during the flight: the bee stops on the spot and searches again
	var wood2 = add.call("add_habitat", {"type": "dead_wood", "x": 500, "y": 300}).result
	decide.call(c2.id, wood2.id)
	for i in 5:
		api.step()
	var stop := late.position
	api.handle("remove_entity", {"id": wood2.id})
	api.step()
	check(late.flight == null and late.position == stop and api.events.back().type == "entity_removed"
		and api.events.filter(func(e): return e.type == "arrival_failed").back().data.reason == "removed",
		"habitat removed mid-flight -> stops where it is")

	# --- a swarm: queen follows the colony decision, the whole swarm flies, takes ONE place
	var tree = add.call("add_habitat", {"type": "tree_cavity", "x": 100, "y": 100}).result
	var s = add.call("add_swarm", {"x": 100, "y": 50, "population": 12000, "personality": {"preset": "prudente"}}).result
	var swarm: Swarm = api.entities[s.id]
	check(s.kind == "swarm" and s.state == "cluster" and s.population == 12000 and is_equal_approx(s.days_left, 0.5),
		"swarm added as a cluster with its delay")
	check(swarm.queen.role == BeeRole.Id.QUEEN and swarm.queen.behavior is QueenBehavior, "the swarm has a queen")
	check(decide.call(s.id, tree.id).result.result == "flying", "swarm decision")
	var queen: QueenBehavior = swarm.queen.behavior
	check(queen.decision is ColonyDecision and queen.decision.support == 12000 and queen.target_habitat == api.entities[tree.id],
		"queen follows the ColonyDecision")
	var ticks_left := swarm.cluster_ticks_left
	for i in 10:  # 50 units at 5 units/tick
		api.step()
	var cavity: Habitat = api.entities[tree.id]
	check(swarm.home == cavity and cavity.occupants == [swarm] and cavity.is_full() and swarm.queen.home == cavity
		and swarm.queen.global_position == cavity.position, "swarm settles on arrival, one place, queen attached")
	check(swarm.cluster_ticks_left == ticks_left, "the delay does not run during the flight")

	# --- delay runs out while clustered: nest in the open
	var s2 = add.call("add_swarm", {"x": 800, "y": 600, "population": 5000}).result
	var swarm2: Swarm = api.entities[s2.id]
	for i in 50:
		api.step()
	check(swarm2.exposed and api._summary(swarm2).state == "exposed"
		and api.events.filter(func(e): return e.type == "swarm_exposed").size() == 1, "delay over -> exposed")
	check(not decide.call(s2.id, tree.id).ok, "an exposed swarm takes no decision")

	# --- swarm full on arrival: clusters again where it is, keeping its remaining delay
	var box = add.call("add_habitat", {"type": "hive_box", "x": 700, "y": 100}).result
	var near = add.call("add_swarm", {"x": 700, "y": 90, "population": 8000}).result
	var far = add.call("add_swarm", {"x": 600, "y": 100, "population": 8000}).result
	decide.call(near.id, box.id)
	decide.call(far.id, box.id)
	var far_swarm: Swarm = api.entities[far.id]
	var far_left := far_swarm.cluster_ticks_left
	for i in 20:
		api.step()
	check(far_swarm.state() == Swarm.State.CLUSTER and far_swarm.cluster_position == far_swarm.position
		and far_swarm.position == Vector2(700, 100) and far_swarm.cluster_ticks_left <= far_left,
		"swarm clusters again after a failed arrival")
	check(api.entities[box.id].occupants.size() == 1, "one colony per cavity")

	# --- removing a settled swarm frees its place; removing its cavity makes it cluster again
	api.handle("remove_entity", {"id": tree.id})
	check(swarm.home == null and swarm.state() == Swarm.State.CLUSTER and swarm.cluster_position == swarm.position,
		"cavity removed -> swarm clusters again")
	check(api.handle("clear_world", {}).ok and world.get_child_count() == 0, "clear_world removes swarms too")
	world.free()


func test_window_view() -> void:
	# the view is only a reader of WorldApi: one drawn item per entity, positions follow the simulation
	var world := Node2D.new()
	var api := WorldApi.new(world, WorldApi.DEFAULT_SIZE, {"flight_speed_factor": 1.0})
	var view: Node2D = load("res://view/world_view.gd").new()
	view.setup(api)
	var soil = api.handle("add_habitat", {"type": "bare_soil", "x": 500, "y": 100}).result
	var b = api.handle("add_bee", {"species": "mining_bee", "x": 100, "y": 100}).result
	api.handle("add_swarm", {"x": 300, "y": 300, "population": 9000})
	api.handle("add_habitat", {"type": "tree_cavity", "x": 50, "y": 600})
	var items: Array = view.build_items()
	check(items.size() == api.entities.size(), "one drawn item per entity")
	api.handle("resume", {})
	api.handle("apply_decision", {"bee_id": b.id, "habitat_id": soil.id})
	var before: Vector2 = view.build_items().filter(func(i): return i.id == b.id)[0].pos
	for i in 10:
		api.step()
	var it: Dictionary = view.build_items().filter(func(i): return i.id == b.id)[0]
	check(it.state == "flying" and it.pos.x > before.x and it.pos == api.entities[b.id].position
		and it.target_id == soil.id, "a flying bee is drawn where the simulation puts it, with its target")
	check(view.build_items().filter(func(i): return i.kind == "swarm")[0].state == "cluster", "swarm drawn as a cluster")
	view.free()
	world.free()
