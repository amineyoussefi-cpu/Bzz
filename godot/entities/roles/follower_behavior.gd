class_name FollowerBehavior
extends BeeBehavior
## FOLLOWER: watches dances, visits habitats, decides to stay or return to the branch.


func role() -> BeeRole.Id:
	return BeeRole.Id.FOLLOWER


func actions() -> PackedStringArray:
	return ["evaluation_signal_danse", "visit_habitat", "stay", "go_back_to_branch"]


## Judge a dance signal (returns 0..1). Logic to be added.
func evaluation_signal_danse() -> float:
	return 0.0


## Travel to the advertised habitat.
func visit_habitat(_habitat: Habitat) -> void:
	pass


## Settle at the visited habitat.
func stay() -> void:
	pass


## Return to the swarm branch.
func go_back_to_branch() -> void:
	pass
