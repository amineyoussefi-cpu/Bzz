class_name FollowerBehavior
extends BeeBehavior
## FOLLOWER: will watch dances and visit habitats. No logic yet — brainless.


func role() -> BeeRole.Id:
	return BeeRole.Id.FOLLOWER


func actions() -> PackedStringArray:
	return []
