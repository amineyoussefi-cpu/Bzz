class_name BeePersonality
extends Resource
## Individual traits (0..1) that make each bee distinct. No evaluation logic — brainless bees.

const TRAITS := ["pickiness", "boldness", "sociability", "curiosity"]

## Named presets offered by the dashboard (documented in docs/api.md).
const PRESETS := {
	"prudente": {"pickiness": 0.8, "boldness": 0.1, "sociability": 0.4, "curiosity": 0.2},
	"audacieuse": {"pickiness": 0.3, "boldness": 0.9, "sociability": 0.5, "curiosity": 0.6},
	"sociable": {"pickiness": 0.5, "boldness": 0.5, "sociability": 0.9, "curiosity": 0.4},
	"curieuse": {"pickiness": 0.4, "boldness": 0.6, "sociability": 0.5, "curiosity": 0.9},
	"équilibrée": {"pickiness": 0.5, "boldness": 0.5, "sociability": 0.5, "curiosity": 0.5},
}

@export_range(0, 1) var pickiness := 0.5    # higher -> needs a better score to accept a habitat
@export_range(0, 1) var boldness := 0.5     # higher -> cares less about predator risk
@export_range(0, 1) var sociability := 0.5  # >0.5 likes already busy sites, <0.5 avoids them
@export_range(0, 1) var curiosity := 0.5    # random spread in judgement, makes choices less predictable


static func random(rng: RandomNumberGenerator) -> BeePersonality:
	var p := BeePersonality.new()
	p.pickiness = rng.randf()
	p.boldness = rng.randf()
	p.sociability = rng.randf()
	p.curiosity = rng.randf()
	return p


## Personality from a {trait: value} dictionary holding every trait (validate it first).
static func from_traits(traits: Dictionary) -> BeePersonality:
	var p := BeePersonality.new()
	for t in TRAITS:
		p.set(t, float(traits[t]))
	return p


## "" if `traits` holds exactly the four traits, each a number in 0..1, else the error message.
static func validate_traits(traits: Dictionary) -> String:
	for t in traits:
		if t not in TRAITS:
			return "unknown trait %s; accepted: %s" % [t, ", ".join(TRAITS)]
	for t in TRAITS:
		if t not in traits:
			return "missing trait %s" % t
		var v = traits[t]
		if typeof(v) not in [TYPE_INT, TYPE_FLOAT] or v < 0.0 or v > 1.0:
			return "%s must be a number between 0 and 1 (got %s)" % [t, v]
	return ""


func to_dict() -> Dictionary:
	var d := {}
	for t in TRAITS:
		d[t] = get(t)
	return d


