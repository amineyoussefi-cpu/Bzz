class_name ColonyDecision
extends RefCounted
## Result handed over by the future collective decision mechanism: the habitat the colony
## settled on. Pure data contract; the mechanism that produces it does not exist yet.

var habitat: Habitat
var support := 0      # e.g. number of scouts backing it when the quorum was reached


static func make(p_habitat: Habitat, p_support := 0) -> ColonyDecision:
	var d := ColonyDecision.new()
	d.habitat = p_habitat
	d.support = p_support
	return d
