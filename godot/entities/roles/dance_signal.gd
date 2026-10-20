class_name DanceSignal
extends RefCounted
## What a scout communicates about a habitat: where it is and how good she judged it.
## Pure data: building one does not broadcast anything.

var scout: Bee
var habitat: Habitat
var location: Vector2      # habitat position in the world
var quality := 0.0         # scout's evaluation, 0..1
var created_at_ms := 0


static func make(p_scout: Bee, p_habitat: Habitat, p_quality: float) -> DanceSignal:
	var s := DanceSignal.new()
	s.scout = p_scout
	s.habitat = p_habitat
	s.location = p_habitat.position
	s.quality = p_quality
	s.created_at_ms = Time.get_ticks_msec()
	return s
