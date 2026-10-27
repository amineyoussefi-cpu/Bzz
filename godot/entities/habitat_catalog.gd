class_name HabitatCatalog
extends RefCounted
## Default features per habitat type (the BeeSpecies counterpart for habitats), feature bounds,
## and readable names. Values follow docs/reference_abeilles.md where the sources give one;
## sun/humidity/flowers/predator defaults are game tuning.

## Every overridable feature with its type and bounds.
const FEATURES := {
	"cavity_volume_l": {"type": "float", "min": 0.0, "max": 1000.0},
	"entrance_diameter_mm": {"type": "float", "min": 0.0, "max": 1000.0},
	"entrance_height_m": {"type": "float", "min": 0.0, "max": 50.0},
	"sun_exposure": {"type": "float", "min": 0.0, "max": 1.0},
	"humidity": {"type": "float", "min": 0.0, "max": 1.0},
	"floral_abundance": {"type": "float", "min": 0.0, "max": 1.0},
	"predator_risk": {"type": "float", "min": 0.0, "max": 1.0},
	"previously_occupied": {"type": "bool"},
	"capacity": {"type": "int", "min": 1, "max": 1000},
}


## 5-level wording of the features a bee perceives (for LLM bees). `bounds` are the upper limits of
## levels 1-4; a value on a bound goes to the higher level. Numbers stay the source of truth.
const LEVELS := {
	"cavity_volume_l": {"bounds": [5.0, 20.0, 35.0, 60.0],
		"words": ["very small cavity", "small cavity", "medium cavity", "large cavity", "very large cavity"]},
	"entrance_diameter_mm": {"bounds": [5.0, 15.0, 30.0, 60.0],
		"words": ["very narrow entrance", "narrow entrance", "medium entrance", "wide entrance", "very wide entrance"]},
	"entrance_height_m": {"bounds": [0.5, 2.0, 4.0, 8.0],
		"words": ["at ground level", "low", "mid-height", "high", "very high"]},
	"sun_exposure": {"bounds": [0.2, 0.4, 0.6, 0.8],
		"words": ["very shady", "shady", "partly sunny", "sunny", "very sunny"]},
	"humidity": {"bounds": [0.2, 0.4, 0.6, 0.8],
		"words": ["very dry", "dry", "moderately humid", "humid", "very humid"]},
	"floral_abundance": {"bounds": [0.2, 0.4, 0.6, 0.8],
		"words": ["almost no flowers", "few flowers", "some flowers", "many flowers", "abundant flowers"]},
	"predator_risk": {"bounds": [0.2, 0.4, 0.6, 0.8],
		"words": ["very safe", "safe", "some danger", "dangerous", "very dangerous"]},
}
## 0 means "not applicable" for these (soil, stems, wood the bee digs itself), not "the smallest".
const NONE_IF_ZERO := {"cavity_volume_l": "no cavity", "entrance_diameter_mm": "no entrance"}


static func defaults(t: Habitat.Type) -> Dictionary:
	var d := {"floral_abundance": 0.6, "previously_occupied": false}
	match t:
		Habitat.Type.TREE_CAVITY:  # Seeley & Morse 1978: ~40 L, ~12.5 cm² entrance, ~5 m high
			d.merge({"cavity_volume_l": 40.0, "entrance_diameter_mm": 40.0, "entrance_height_m": 5.0,
				"sun_exposure": 0.4, "humidity": 0.4, "predator_risk": 0.2, "capacity": 1})
		Habitat.Type.HIVE_BOX:
			d.merge({"cavity_volume_l": 40.0, "entrance_diameter_mm": 40.0, "entrance_height_m": 1.0,
				"sun_exposure": 0.5, "humidity": 0.3, "predator_risk": 0.1, "capacity": 1})
		Habitat.Type.RODENT_BURROW:  # small underground cavity, old nest material
			d.merge({"cavity_volume_l": 2.0, "entrance_diameter_mm": 30.0, "entrance_height_m": 0.0,
				"sun_exposure": 0.1, "humidity": 0.5, "predator_risk": 0.3, "capacity": 1, "previously_occupied": true})
		Habitat.Type.BARE_SOIL:  # sunny, well-drained, hosts nest aggregations
			d.merge({"cavity_volume_l": 0.0, "entrance_diameter_mm": 0.0, "entrance_height_m": 0.0,
				"sun_exposure": 0.9, "humidity": 0.2, "predator_risk": 0.3, "capacity": 50})
		Habitat.Type.HOLLOW_STEM:  # bundle of ~7 mm tubes, one nest per tube
			d.merge({"cavity_volume_l": 0.0, "entrance_diameter_mm": 7.0, "entrance_height_m": 1.0,
				"sun_exposure": 0.8, "humidity": 0.3, "predator_risk": 0.2, "capacity": 20})
		Habitat.Type.DEAD_WOOD:  # dry sunny wood the bee digs into
			d.merge({"cavity_volume_l": 0.0, "entrance_diameter_mm": 0.0, "entrance_height_m": 1.5,
				"sun_exposure": 0.7, "humidity": 0.2, "predator_risk": 0.2, "capacity": 5})
	return d


static func type_name(t: Habitat.Type) -> String:
	return Habitat.Type.keys()[t].to_lower()


## Enum value for a readable name, or -1.
static func type_from_name(n: String) -> int:
	return Habitat.Type.keys().find(n.to_upper()) if n == n.to_lower() else -1


static func type_names() -> Array:
	return Habitat.Type.keys().map(func(k): return k.to_lower())


## "" if every override is a known feature within bounds, else the error message.
static func validate_features(features: Dictionary) -> String:
	for key in features:
		if key not in FEATURES:
			return "unknown feature %s; accepted: %s" % [key, ", ".join(FEATURES.keys())]
		var spec: Dictionary = FEATURES[key]
		var v = features[key]
		if spec.type == "bool":
			if typeof(v) != TYPE_BOOL:
				return "%s must be true or false" % key
			continue
		if typeof(v) not in [TYPE_INT, TYPE_FLOAT] or (spec.type == "int" and v != floorf(v)):
			return "%s must be %s" % [key, "an integer" if spec.type == "int" else "a number"]
		if v < spec.min or v > spec.max:
			return "%s must be between %s and %s (got %s)" % [key, spec.min, spec.max, v]
	return ""


## New habitat with the type's defaults, then `overrides` (validate them first).
static func create(t: Habitat.Type, overrides := {}) -> Habitat:
	var h := Habitat.new()
	h.habitat_type = t
	var values := defaults(t)
	values.merge(overrides, true)
	for key in values:
		h.set(key, int(values[key]) if FEATURES[key].type == "int" else values[key])
	return h


static func features_of(h: Habitat) -> Dictionary:
	var out := {}
	for key in FEATURES:
		out[key] = h.get(key)
	return out


## Level 0..4 of `value` on the LEVELS scale of `key`.
static func level(key: String, value: float) -> int:
	return LEVELS[key].bounds.bsearch(value, false)


## What a bee perceives of `h`: {feature: words}. Capacity is left out (not something a bee judges).
static func describe(h: Habitat) -> Dictionary:
	var out := {}
	for key in LEVELS:
		var v: float = h.get(key)
		out[key] = NONE_IF_ZERO[key] if v == 0.0 and key in NONE_IF_ZERO else LEVELS[key].words[level(key, v)]
	out["previously_occupied"] = "old nest present" if h.previously_occupied else "no old nest"
	return out
