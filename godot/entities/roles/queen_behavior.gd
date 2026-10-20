class_name QueenBehavior
extends BeeBehavior
## QUEEN: never picks a habitat herself; she follows the colony's collective decision and reproduces.

var decision: ColonyDecision = null
var target_habitat: Habitat = null


func role() -> BeeRole.Id:
	return BeeRole.Id.QUEEN


func actions() -> PackedStringArray:
	return ["receive_colony_decision", "follow_colony_decision", "move_to_habitat", "lay_eggs",
		"manage_reproduction_cycle"]


## Records the destination validated by the collective decision mechanism.
func receive_colony_decision(p_decision: ColonyDecision) -> void:
	decision = p_decision


## Adopts the decision's habitat as the queen's destination. Does not move her.
func follow_colony_decision(p_decision: ColonyDecision) -> void:
	receive_colony_decision(p_decision)
	target_habitat = p_decision.habitat


## Flies to the chosen habitat; a queen inside a swarm takes the whole swarm with her.
func move_to_habitat(habitat: Habitat) -> void:
	target_habitat = habitat
	var swarm := bee.get_parent() as Swarm
	if swarm:
		swarm.fly_to(habitat)
	else:
		bee.fly_to(habitat)


## Interface only: will lay eggs in the current home. Creates nothing yet.
func lay_eggs() -> void:
	pass


## Interface only: will run the reproduction cycle (laying, brood development, new bees).
func manage_reproduction_cycle() -> void:
	pass
