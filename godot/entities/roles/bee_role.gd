class_name BeeRole
extends RefCounted
## Roles a bee can hold, independent of species and personality: every species uses the same roles.
## A role maps to a behavior component that declares the role's actions (see docs/roles_comportements.md).

enum Id { SCOUT, FOLLOWER, QUEEN }


## New behavior component for `id`, attached to `bee`. Creating it executes nothing.
static func create_behavior(id: Id, bee: Bee) -> BeeBehavior:
	match id:
		Id.SCOUT: return ScoutBehavior.new(bee)
		Id.FOLLOWER: return FollowerBehavior.new(bee)
		Id.QUEEN: return QueenBehavior.new(bee)
	return null


static func role_name(id: Id) -> String:
	return Id.keys()[id]


## Readable lowercase names ("scout", ...) used by the protocol.
static func from_name(n: String) -> int:
	return Id.keys().find(n.to_upper()) if n == n.to_lower() else -1


static func names() -> Array:
	return Id.keys().map(func(k): return k.to_lower())
