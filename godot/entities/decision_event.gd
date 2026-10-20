class_name DecisionEvent
extends RefCounted
## Format of a bee decision as published in the event log (type "decision"), whatever its source.
## The backend fills it (source "openjev") and Godot emits it from apply_decision (format: docs/api.md).
## result: "flying" (took off; settling happens on arrival), "none" (no habitat chosen) or "rejected".

var bee_id := ""
var evaluated: Array = []          # [{"habitat_id", "score", "breakdown": {criterion: score}, ...}]
var chosen_habitat_id = null       # String, or null when the bee refused every candidate
var reason := ""                   # optional free-text justification
var source := ""                   # who decided, e.g. "openjev", "reference"
var result := ""                   # what followed: "flying", "none", "rejected"
var probabilities := {}            # option -> probability given by the source ("none" included)
var reference := {}                # the reference logic's choice for comparison: {"choice", "scores"}
var agreement = null               # true/false when a reference choice exists
var model := {}                    # model id/revision/device/latency when the source is a model
var context := {}                  # extra facts given to the decider, e.g. a swarm's population and days left


## Fills the known keys from a dictionary sent by the backend; unknown keys are ignored.
static func from_dict(d: Dictionary) -> DecisionEvent:
	var e := DecisionEvent.new()
	for key in ["bee_id", "evaluated", "chosen_habitat_id", "reason", "source", "result", "probabilities",
			"reference", "agreement", "model", "context"]:
		if key in d and d[key] != null:
			e.set(key, d[key])
	return e


func outcome() -> String:
	return "refused" if chosen_habitat_id == null else "chosen"


## Payload stored as the event "data".
func to_dict() -> Dictionary:
	return {"bee_id": bee_id, "evaluated": evaluated, "chosen_habitat_id": chosen_habitat_id,
		"outcome": outcome(), "reason": reason, "source": source, "result": result,
		"probabilities": probabilities, "reference": reference, "agreement": agreement, "model": model,
		"context": context}
