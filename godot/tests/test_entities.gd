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

	print("entity tests: %s" % ("OK" if failures == 0 else "%d failure(s)" % failures))
	quit(1 if failures else 0)
