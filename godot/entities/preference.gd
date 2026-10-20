class_name Preference
extends Resource
## One criterion a bee cares about: the score is 1 at `ideal` and falls linearly
## to 0 at `ideal ± tolerance`.

@export var criterion := ""   # a key of Habitat.features()
@export var ideal := 0.0
@export var tolerance := 1.0
@export var weight := 1.0


static func make(p_criterion: String, p_ideal: float, p_tolerance: float, p_weight := 1.0) -> Preference:
	var p := Preference.new()
	p.criterion = p_criterion
	p.ideal = p_ideal
	p.tolerance = p_tolerance
	p.weight = p_weight
	return p


func score(value: float) -> float:
	return clampf(1.0 - absf(value - ideal) / tolerance, 0.0, 1.0)
