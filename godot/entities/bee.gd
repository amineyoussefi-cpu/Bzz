class_name Bee
extends Node2D
## A bee with a personality and role. No species, no evaluation logic — brainless by design.

@export var bee_name := ""
@export var personality: BeePersonality

var home: Habitat = null
var role: BeeRole.Id = BeeRole.Id.FOLLOWER
var behavior: BeeBehavior  # the component for the current role; set by set_role()


## Builds a bee with a random personality unless one is provided.
static func create(p_personality: BeePersonality = null, rng_seed := 0) -> Bee:
	var bee := Bee.new()
	var rng := RandomNumberGenerator.new()
	if rng_seed != 0:
		rng.seed = rng_seed
	bee.personality = p_personality if p_personality else BeePersonality.random(rng)
	bee.set_role(BeeRole.Id.FOLLOWER)
	return bee


## Gives the bee a role and its matching behavior component. Runs no action.
func set_role(p_role: BeeRole.Id) -> void:
	role = p_role
	behavior = BeeRole.create_behavior(p_role, self)
