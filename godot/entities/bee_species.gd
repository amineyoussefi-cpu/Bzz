class_name BeeSpecies
extends RefCounted
## Species catalogue: which habitat types each species accepts and its default preferences.
## Values come from docs/reference_abeilles.md (sources there); tolerances and weights are game tuning.

enum Id { HONEY_BEE, BUMBLEBEE, MASON_BEE, MINING_BEE, CARPENTER_BEE }


static func species_name(id: Id) -> String:
	return Id.keys()[id].to_lower()


## Enum value for a readable name, or -1.
static func from_name(n: String) -> int:
	return Id.keys().find(n.to_upper()) if n == n.to_lower() else -1


static func names() -> Array:
	return Id.keys().map(func(k): return k.to_lower())


static func accepted_types(id: Id) -> Array:
	match id:
		Id.HONEY_BEE: return [Habitat.Type.TREE_CAVITY, Habitat.Type.HIVE_BOX]
		Id.BUMBLEBEE: return [Habitat.Type.RODENT_BURROW, Habitat.Type.HIVE_BOX, Habitat.Type.TREE_CAVITY]
		Id.MASON_BEE: return [Habitat.Type.HOLLOW_STEM, Habitat.Type.DEAD_WOOD]
		Id.MINING_BEE: return [Habitat.Type.BARE_SOIL]
		Id.CARPENTER_BEE: return [Habitat.Type.DEAD_WOOD]
	return []


## Fresh Preference objects each call, so every bee can tune its own copy.
static func default_preferences(id: Id) -> Array[Preference]:
	match id:
		Id.HONEY_BEE:  # Seeley & Morse 1978: 40 L, 12.5 cm² entrance (~40 mm), 5 m high, old comb
			return [Preference.make("cavity_volume_l", 40, 35, 2), Preference.make("entrance_diameter_mm", 40, 40),
				Preference.make("entrance_height_m", 5, 5), Preference.make("previously_occupied", 1, 1, 0.5),
				Preference.make("floral_abundance", 1, 1)]
		Id.BUMBLEBEE:  # small sheltered cavity, usually underground
			return [Preference.make("cavity_volume_l", 2, 4), Preference.make("entrance_height_m", 0, 1, 1.5),
				Preference.make("humidity", 0.4, 0.5), Preference.make("floral_abundance", 1, 1)]
		Id.MASON_BEE:  # tubes ~6-8 mm (usable 4-12), sunny, off the ground
			return [Preference.make("entrance_diameter_mm", 7, 5, 2), Preference.make("sun_exposure", 1, 0.8),
				Preference.make("entrance_height_m", 1, 1.5, 0.5), Preference.make("floral_abundance", 1, 1)]
		Id.MINING_BEE:  # bare, well-drained, sunny soil
			return [Preference.make("sun_exposure", 1, 0.8, 1.5), Preference.make("humidity", 0.2, 0.6, 1.5),
				Preference.make("floral_abundance", 1, 1)]
		Id.CARPENTER_BEE:  # dry dead wood in the sun
			return [Preference.make("sun_exposure", 0.8, 0.8), Preference.make("humidity", 0.2, 0.6),
				Preference.make("floral_abundance", 1, 1)]
	return []
