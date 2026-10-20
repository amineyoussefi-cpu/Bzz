class_name Bee
extends Node2D
## An autonomous bee that judges habitats through its species preferences and its personality.
## Designed for many independent instances. Honey bees enter the world as swarm queens (Swarm), not alone.

@export var species: BeeSpecies.Id = BeeSpecies.Id.HONEY_BEE
@export var bee_name := ""
@export var accepted_types: Array = []
@export var preferences: Array[Preference] = []
@export var personality: BeePersonality

var home: Habitat = null
var rng := RandomNumberGenerator.new()
var role: BeeRole.Id = BeeRole.Id.FOLLOWER
var behavior: BeeBehavior  # actions of the current role; set by set_role()
var flight: Flight = null  # set while flying to a chosen habitat
var flight_speed := 1.0    # world units per tick (species speed x flight speed factor, set by WorldApi)


## Builds a bee with its species defaults; pass a personality to override the random one.
static func create(p_species: BeeSpecies.Id, p_personality: BeePersonality = null, rng_seed := 0) -> Bee:
	var bee := Bee.new()
	bee.species = p_species
	bee.accepted_types = BeeSpecies.accepted_types(p_species)
	bee.preferences = BeeSpecies.default_preferences(p_species)
	if rng_seed != 0:
		bee.rng.seed = rng_seed
	bee.personality = p_personality if p_personality else BeePersonality.random(bee.rng)
	bee.set_role(BeeRole.Id.FOLLOWER)
	return bee


## Gives the bee a role and the matching behavior component. Runs no action.
func set_role(p_role: BeeRole.Id) -> void:
	role = p_role
	behavior = BeeRole.create_behavior(p_role, self)


## Per-criterion scores plus the final score in "total" (0..1). 0 if the habitat is unusable.
func score_breakdown(h: Habitat) -> Dictionary:
	if h.habitat_type not in accepted_types or (h.is_full() and h != home):
		return {"total": 0.0}
	var out := {}
	var features := h.features()
	var sum := 0.0
	var weights := 0.0
	for p in preferences:
		out[p.criterion] = p.score(features[p.criterion])
		sum += out[p.criterion] * p.weight
		weights += p.weight
	var total := sum / weights if weights > 0 else 1.0
	total *= 1.0 - h.predator_risk * (1.0 - personality.boldness)
	if h.capacity > 1:
		total += 0.2 * (personality.sociability - 0.5) * 2.0 * h.occupancy()
	total += rng.randf_range(-0.1, 0.1) * personality.curiosity
	out["total"] = clampf(total, 0.0, 1.0)
	return out


func evaluate_habitat(h: Habitat) -> float:
	return score_breakdown(h)["total"]


## Best candidate that clears this bee's acceptance threshold, or null.
func choose_habitat(candidates: Array) -> Habitat:
	var best: Habitat = null
	var best_score := personality.acceptance_threshold()
	for h: Habitat in candidates:
		var s := evaluate_habitat(h)
		if s >= best_score:
			best = h
			best_score = s
	return best


func settle(h: Habitat) -> bool:
	if h.is_full() or h.habitat_type not in accepted_types:
		return false
	leave_home()
	h.occupants.append(self)
	home = h
	return true


## Starts a straight flight toward `h`; settling happens on arrival (WorldApi).
func fly_to(h: Habitat) -> void:
	flight = Flight.new(position, h, flight_speed)


func leave_home() -> void:
	if home:
		home.occupants.erase(self)
		home = null
