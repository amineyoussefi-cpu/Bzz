@abstract
class_name BeeBehavior
extends RefCounted
## Base of the role behavior components. A component declares what a role can do;
## the mechanisms that run these actions in the world (movement, collective decision,
## reproduction) are not implemented yet. Methods marked "Interface only" do nothing.

var bee: Bee  # the bee holding this role; habitat judgement stays in Bee (not duplicated here)


func _init(p_bee: Bee) -> void:
	bee = p_bee


@abstract func role() -> BeeRole.Id


## Names of the actions this role exposes.
@abstract func actions() -> PackedStringArray
