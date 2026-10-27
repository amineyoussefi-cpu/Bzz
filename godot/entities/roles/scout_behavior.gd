class_name ScoutBehavior
extends BeeBehavior
## SCOUT: will search for habitats and report them. No logic yet — brainless.


func role() -> BeeRole.Id:
	return BeeRole.Id.SCOUT


func actions() -> PackedStringArray:
	return []
