class_name FollowerBehavior
extends BeeBehavior
## FOLLOWER: watches dances, decides whether one is worth following, then checks the habitat herself.

var received_signals: Array[DanceSignal] = []


func role() -> BeeRole.Id:
	return BeeRole.Id.FOLLOWER


func actions() -> PackedStringArray:
	return ["receive_dance", "evaluate_signal", "decide_to_follow", "visit_habitat", "evaluate_habitat"]


## Records a dance the follower has watched.
func receive_dance(dance: DanceSignal) -> void:
	received_signals.append(dance)


## Interface only: will weigh what a dance says (quality, distance, scout). Returns 0 for now.
func evaluate_signal(_dance: DanceSignal) -> float:
	return 0.0


## Interface only: will decide whether the dance justifies a trip. Always false for now.
func decide_to_follow(_dance: DanceSignal) -> bool:
	return false


## Interface only: will fly to the advertised habitat. No movement yet.
func visit_habitat(_habitat: Habitat) -> void:
	pass


## Independent judgement of the visited habitat (delegates to Bee, same rules as scouts).
func evaluate_habitat(habitat: Habitat) -> float:
	return bee.evaluate_habitat(habitat)
