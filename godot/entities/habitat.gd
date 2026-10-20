class_name Habitat
extends Node2D
## A place where a bee may settle. Designed for many independent instances;
## none is placed in the world yet (see docs/reference_abeilles.md).

enum Type { TREE_CAVITY, HIVE_BOX, RODENT_BURROW, BARE_SOIL, HOLLOW_STEM, DEAD_WOOD }

@export var habitat_type: Type = Type.TREE_CAVITY
@export var cavity_volume_l := 0.0        # inner volume; ~0 for stems and soil
@export var entrance_diameter_mm := 0.0   # 0 = no entrance to judge (soil, wood the bee digs itself)
@export var entrance_height_m := 0.0      # height of the entrance above ground
@export_range(0, 1) var sun_exposure := 0.5
@export_range(0, 1) var humidity := 0.5
@export_range(0, 1) var floral_abundance := 0.5  # flowers nearby; may be computed from the world later
@export_range(0, 1) var predator_risk := 0.0
@export var previously_occupied := false  # old comb / old nest present
@export var capacity := 1                 # bees or colonies it can host at once

var occupants: Array = []  # Bee nodes living here


func is_full() -> bool:
	return occupants.size() >= capacity


func occupancy() -> float:
	return occupants.size() / float(capacity)


## Numeric features a bee can judge, keyed by the criterion names used in Preference.
func features() -> Dictionary:
	return {
		"cavity_volume_l": cavity_volume_l,
		"entrance_diameter_mm": entrance_diameter_mm,
		"entrance_height_m": entrance_height_m,
		"sun_exposure": sun_exposure,
		"humidity": humidity,
		"floral_abundance": floral_abundance,
		"previously_occupied": 1.0 if previously_occupied else 0.0,
	}
