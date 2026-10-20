class_name DecisionEvent
extends RefCounted
## Format of a bee decision as published in the event log (type "decision").
## Defined now so the dashboard can display decisions; NOTHING emits it yet — the decision
## mechanism comes in the next step and only has to fill this object (format: docs/api.md).

var bee_id := ""
var evaluated: Array[Dictionary] = []  # [{"habitat_id", "score", "breakdown": {criterion: score}}]
var chosen_habitat_id = null           # String, or null when the bee refused every candidate
var reason := ""                       # optional free-text justification
var source := ""                       # who decided, e.g. "individual", "collective"
var result := ""                       # what followed, e.g. "settled", "pending", "none"


func outcome() -> String:
	return "refused" if chosen_habitat_id == null else "chosen"


## Payload stored as the event "data".
func to_dict() -> Dictionary:
	return {"bee_id": bee_id, "evaluated": evaluated, "chosen_habitat_id": chosen_habitat_id,
		"outcome": outcome(), "reason": reason, "source": source, "result": result}
