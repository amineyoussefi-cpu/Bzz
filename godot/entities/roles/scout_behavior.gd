class_name ScoutBehavior
extends BeeBehavior
## SCOUT: explores habitats, evaluates them, returns to colony, and dances to report.


func role() -> BeeRole.Id:
	return BeeRole.Id.SCOUT


func actions() -> PackedStringArray:
	return ["explore", "evaluate", "go_back", "dance"]


## Search the world for candidate habitats.
func explore() -> Array[Habitat]:
	return []


## Judge a habitat (returns 0..1). Logic to be added.
func evaluate(_habitat: Habitat) -> float:
	return 0.0


## Return to the colony.
func go_back() -> void:
	pass


## Signal a habitat discovery to the colony.
func dance() -> void:
	pass
