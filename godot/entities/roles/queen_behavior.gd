class_name QueenBehavior
extends BeeBehavior
## QUEEN: will follow the colony's decision and reproduce. No logic yet — brainless.


func role() -> BeeRole.Id:
	return BeeRole.Id.QUEEN


func actions() -> PackedStringArray:
	return []
