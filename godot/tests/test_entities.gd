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
	check(queen.home == null and queen.position == Vector2.ZERO and site.occupants.is_empty(),
		"queen actions do not move her or create bees")


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
