class_name Swarm
extends Node2D
## A honey bee swarm: a queen plus a population of workers (a number, not thousands of nodes), clustered on a
## branch while it looks for a cavity. It has a few simulated days before it must nest in the open.
## Its collective personality is a BeePersonality shared with the queen (game simplification).
## The queen is a child node, so she moves with the swarm.

enum State { CLUSTER, FLYING, SETTLED, EXPOSED }

var queen: Bee
var population := 10000
var swarm_name := ""
var cluster_position := Vector2.ZERO   # the branch the swarm hangs on
var cluster_ticks_left := 0            # runs down only while clustered
var exposed := false                   # the delay ran out: nest in the open
var home: Habitat = null
var flight: Flight = null
var flight_speed := 1.0                # world units per tick


## A swarm whose queen has the honey bee preferences and `personality` (random from `rng_seed` if null).
static func create(p_population: int, p_personality: BeePersonality, p_cluster_ticks: int, rng_seed := 0) -> Swarm:
	var s := Swarm.new()
	s.population = p_population
	s.cluster_ticks_left = p_cluster_ticks
	s.queen = Bee.create(BeeSpecies.Id.HONEY_BEE, p_personality, rng_seed)
	s.queen.set_role(BeeRole.Id.QUEEN)
	s.add_child(s.queen)
	return s


func personality() -> BeePersonality:
	return queen.personality


func state() -> State:
	if home:
		return State.SETTLED
	if flight:
		return State.FLYING
	return State.EXPOSED if exposed else State.CLUSTER


## Starts the whole swarm's flight toward `h` (called through QueenBehavior.move_to_habitat).
func fly_to(h: Habitat) -> void:
	flight = Flight.new(position, h, flight_speed)


## Takes one place in `h` (a colony, whatever its population); false if full or not a cavity it accepts.
func settle(h: Habitat) -> bool:
	if h.is_full() or h.habitat_type not in queen.accepted_types:
		return false
	h.occupants.append(self)
	home = h
	queen.home = h
	return true


func leave_home() -> void:
	if home:
		home.occupants.erase(self)
		home = null
		queen.home = null


## Hangs again where it is (after a failed arrival or when its habitat is removed), keeping its remaining delay.
func cluster_here() -> void:
	flight = null
	cluster_position = position
