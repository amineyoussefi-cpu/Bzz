class_name BeeSpecies
extends RefCounted
## Species catalogue: names and accepted habitat types per species.

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
