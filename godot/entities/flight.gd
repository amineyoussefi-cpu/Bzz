class_name Flight
extends RefCounted
## A straight-line flight toward a habitat, advanced one simulation tick at a time by WorldApi.step().
## No obstacles and no path finding. The habitat is not reserved: it may be full or gone on arrival.

var target: Habitat
var origin: Vector2
var speed := 1.0  # world units per tick
var ticks := 0    # ticks spent flying so far


func _init(p_origin: Vector2, p_target: Habitat, p_speed: float) -> void:
	origin = p_origin
	target = p_target
	speed = p_speed


## Moves `node` one tick toward the target; true once it has reached it.
func advance(node: Node2D) -> bool:
	ticks += 1
	var to := target.position
	var d := node.position.distance_to(to)
	if d <= speed:
		node.position = to
		return true
	node.position += (to - node.position) / d * speed
	return false
