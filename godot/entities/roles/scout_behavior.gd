class_name ScoutBehavior
extends BeeBehavior
## SCOUT: searches for habitats, judges them, remembers them and reports them by dancing.

var known_habitats := {}  # Habitat -> last quality the scout gave it


func role() -> BeeRole.Id:
	return BeeRole.Id.SCOUT


func actions() -> PackedStringArray:
	return ["explore_habitats", "evaluate_habitat", "remember_habitat", "return_to_colony", "perform_dance"]


## Interface only: will search the world for candidate habitats. Returns none for now.
func explore_habitats() -> Array[Habitat]:
	return []


## Judgement from the bee's species preferences and personality (delegates to Bee).
func evaluate_habitat(habitat: Habitat) -> float:
	return bee.evaluate_habitat(habitat)


## Stores the habitat with its current evaluation in the scout's memory.
func remember_habitat(habitat: Habitat) -> void:
	known_habitats[habitat] = evaluate_habitat(habitat)


## Interface only: will fly the scout back to its colony. No movement yet.
func return_to_colony() -> void:
	pass


## Prepares the dance signal for a habitat (data only, nothing is broadcast).
func perform_dance(habitat: Habitat) -> DanceSignal:
	var quality: float = known_habitats.get(habitat, evaluate_habitat(habitat))
	return DanceSignal.make(bee, habitat, quality)
