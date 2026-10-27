extends SceneTree
## Unit checks for the bee/habitat model. Run (after an import so class_name is registered):
##   godot --headless --path godot --import && godot --headless --path godot --script res://tests/test_entities.gd

var failures := 0


func check(cond: bool, what: String) -> void:
	if not cond:
		failures += 1
		printerr("FAIL: ", what)


func _init() -> void:
	test_roles()
	test_world_api()
	test_describe()
	test_swarm()
	print("entity tests: %s" % ("OK" if failures == 0 else "%d failure(s)" % failures))
	quit(1 if failures else 0)


func test_roles() -> void:
	check(BeeRole.Id.size() == 2, "exactly two roles")
	var bee := Bee.create()
	check(bee.role == BeeRole.Id.FOLLOWER and bee.behavior is FollowerBehavior, "default role is follower")
	for id in BeeRole.Id.values():
		bee.set_role(id)
		check(bee.role == id and bee.behavior.role() == id and bee.behavior.bee == bee,
			"set_role %s" % BeeRole.role_name(id))


func test_world_api() -> void:
	var world := Node2D.new()
	var api := WorldApi.new(world)
	var h = api.handle("add_habitat", {"type": "bare_soil", "x": 10, "y": 10}).result
	var b = api.handle("add_bee", {"x": 20, "y": 20}).result
	check(world.get_child_count() == 2 and h.id != b.id, "entities added as world children with unique ids")
	check(not api.handle("add_bee", {"x": 20, "y": 9999}).ok and world.get_child_count() == 2,
		"refused command creates nothing")

	var tick := api.tick
	api.step()
	check(api.tick == tick, "paused world does not advance")
	api.handle("resume", {})
	api.step()
	check(api.tick == tick + 1, "running world advances one tick per physics frame")
	check(api.handle("clear_world", {}).result.removed == 1 and world.get_child_count() == 0, "clear_world empties")
	var types: Array = api.handle("get_events", {}).result.events.map(func(e): return e.type)
	check(types == ["entity_added", "entity_added", "entity_removed", "resumed", "world_cleared"], "event log %s" % [types])
	world.free()


func test_describe() -> void:
	check(HabitatCatalog.level("sun_exposure", 0.0) == 0 and HabitatCatalog.level("sun_exposure", 0.2) == 1
		and HabitatCatalog.level("sun_exposure", 1.0) == 4, "levels: bound goes up, ends clamp to 0 and 4")
	var h := HabitatCatalog.create(Habitat.Type.TREE_CAVITY)
	var tree := HabitatCatalog.describe(h)
	check(tree.cavity_volume_l == "large cavity" and tree.entrance_height_m == "high"
		and tree.predator_risk == "safe" and tree.previously_occupied == "no old nest", "tree cavity wording %s" % [tree])
	h.free()
	h = HabitatCatalog.create(Habitat.Type.BARE_SOIL)
	var soil := HabitatCatalog.describe(h)
	check(soil.cavity_volume_l == "no cavity" and soil.entrance_diameter_mm == "no entrance"
		and soil.sun_exposure == "very sunny", "zero means not applicable %s" % [soil])
	h.free()
	h = HabitatCatalog.create(Habitat.Type.HIVE_BOX, {"sun_exposure": 0.05})
	check(h.sun_exposure == 0.05 and HabitatCatalog.describe(h).sun_exposure == "very shady", "numbers kept, words follow")
	h.free()


## A whole house hunt with a scripted brain: site A is good (5), B is poor (1). The swarm must pick A.
func test_swarm() -> void:
	var world := Node2D.new()
	var api := WorldApi.new(world)
	var a = api.handle("add_habitat", {"type": "tree_cavity", "x": 200, "y": 150}).result.id
	api.handle("add_habitat", {"type": "bare_soil", "x": 800, "y": 550})
	for i in 2:
		api.handle("add_bee", {"role": "scout"})
	for i in 3:
		api.handle("add_bee", {})
	var bee_id = api.handle("list_entities", {}).result[2].id
	check(not api.handle("answer_decision", {"bee_id": bee_id, "kind": "evaluate_site", "answer": {"score": 3}}).ok,
		"an answer nobody waits for is refused")
	api.handle("resume", {})
	var seen := 0
	var asked := {}
	for t in 20000:
		api.step()
		for ev in api.events:
			if ev.seq <= seen:
				continue
			seen = ev.seq
			if ev.type != "decision_needed":
				continue
			var d: Dictionary = ev.data
			asked[d.kind] = true
			var reply := {}
			match d.kind:
				"evaluate_site":
					reply = {"score": 5 if d.situation.habitat.id == a else 1}
					check(not api.handle("answer_decision", {"bee_id": d.bee_id, "kind": "evaluate_site", "answer": {"score": 9}}).ok,
						"out-of-range score refused")
				"stay_or_leave":
					reply = {"choice": "stay" if d.situation.habitat.id == a else "go_back"}
				"judge_dances":
					reply = {"follow": d.situation.dances[0].site_id}
			var r = api.handle("answer_decision", {"bee_id": d.bee_id, "kind": d.kind, "answer": reply})
			check(r.ok, "answer accepted: %s" % [r])
		if api.swarm.status().phase == "settled":
			break
	var st: Dictionary = api.swarm.status()
	check(st.phase == "settled" and st.chosen_id == a, "swarm settled at the good site: %s" % [st])
	check(asked.size() == 3, "all three decisions were asked: %s" % [asked.keys()])
	var bees: Array = api.handle("list_entities", {}).result.filter(func(e): return e.kind == "bee")
	check(bees.all(func(e): return e.home_id == a and e.state == "settled"), "every bee lives at the chosen site")
	check(api.events.any(func(e): return e.type == "bee_danced"), "bees danced")
	check(api.events.any(func(e): return e.type == "swarm_decided" and e.data.habitat_id == a), "swarm_decided event")
	world.free()
