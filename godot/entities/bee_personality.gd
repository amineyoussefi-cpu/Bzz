class_name BeePersonality
extends Resource
## Individual traits (0..1) that bend how a bee applies its species preferences.
## Game simplification: real bees have no documented "personality" in this sense.

@export_range(0, 1) var pickiness := 0.5    # higher -> needs a better score to accept a habitat
@export_range(0, 1) var boldness := 0.5     # higher -> cares less about predator risk
@export_range(0, 1) var sociability := 0.5  # >0.5 likes already busy sites, <0.5 avoids them
@export_range(0, 1) var curiosity := 0.5    # random spread in judgement, makes choices less predictable


static func random(rng: RandomNumberGenerator) -> BeePersonality:
	var p := BeePersonality.new()
	p.pickiness = rng.randf()
	p.boldness = rng.randf()
	p.sociability = rng.randf()
	p.curiosity = rng.randf()
	return p


func acceptance_threshold() -> float:
	return 0.3 + 0.5 * pickiness
