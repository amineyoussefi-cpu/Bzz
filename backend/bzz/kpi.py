"""Dashboard indicators, computed from the state, entities and events Godot provides (never simulated here)."""

TRAIT_BINS = 5  # 0-0.2, 0.2-0.4, ... 0.8-1


def _bin(value: float) -> int:
    return min(int(value * TRAIT_BINS), TRAIT_BINS - 1)


BEE_STATES = ("searching", "waiting", "flying", "settled")
SWARM_STATES = ("cluster", "flying", "settled", "exposed")


def _avg(xs) -> float | None:
    xs = list(xs)
    return round(sum(xs) / len(xs), 3) if xs else None


def compute(state: dict, entities: list[dict], events: list[dict], catalog: dict,
            decision_service: dict | None = None) -> dict:
    """`events`: the decision and movement events kept by the backend (decision, arrived, arrival_failed,
    swarm_exposed)."""
    habitats = [e for e in entities if e["kind"] == "habitat"]
    bees = [e for e in entities if e["kind"] == "bee"]
    swarms = [e for e in entities if e["kind"] == "swarm"]
    traits = [t["name"] for t in catalog["traits"]]
    species = [s["name"] for s in catalog["species"]]
    day_ticks = state["day_ticks"]
    by_type = lambda t: [ev for ev in events if ev["type"] == t]  # noqa: E731
    arrived, failed = by_type("arrived"), by_type("arrival_failed")
    return {
        "sim": {
            "tick": state["tick"],
            "seconds": round(state["tick"] / state["ticks_per_second"], 2),
            "day": state["tick"] // day_ticks + 1,
            "hour": round(state["tick"] % day_ticks / day_ticks * 24, 2),
            "paused": state["paused"],
            "speed": state["speed"],
        },
        "habitats_by_type": {t["name"]: sum(h["type"] == t["name"] for h in habitats) for t in catalog["habitat_types"]},
        "bees_by_species": {s: sum(b["species"] == s for b in bees) for s in species},
        "trait_distribution": {t: [sum(_bin(b["personality"][t]) == i for b in bees + swarms) for i in range(TRAIT_BINS)]
                               for t in traits},
        "bees_by_state": {st: sum(b["state"] == st for b in bees) for st in BEE_STATES},
        "swarms_by_state": {st: sum(w["state"] == st for w in swarms) for st in SWARM_STATES},
        "swarms": [{"id": w["id"], "name": w["name"], "state": w["state"], "population": w["population"],
                    "days_left": round(w["days_left"], 2), "waiting": w["waiting"]} for w in swarms],
        "bees_settled": sum(b["state"] == "settled" for b in bees),
        "bees_homeless": sum(b["state"] != "settled" for b in bees),
        "occupancy": [{"id": h["id"], "type": h["type"], "occupants": h["occupants"], "capacity": h["capacity"],
                       "rate": h["occupants"] / h["capacity"]} for h in habitats],
        "movement": {
            "arrivals": len(arrived),
            "arrival_failures": len(failed),
            "failures_by_reason": {r: sum(ev["data"]["reason"] == r for ev in failed) for r in ("full", "removed")},
            "avg_days_to_habitat": _avg(ev["data"]["found_after_days"] for ev in arrived),
            "avg_flight_hours": _avg(ev["data"]["flight_ticks"] / day_ticks * 24 for ev in arrived),
            "swarms_exposed": len(by_type("swarm_exposed")),
        },
        "decisions": _decision_kpi(by_type("decision"), bees + swarms, species, traits, decision_service),
    }


def _decision_kpi(decisions: list[dict], bees: list[dict], species: list[str], traits: list[str],
                  service: dict | None) -> dict:
    """Aggregates "decision" events (format in docs/api.md): choices, refusals, scores, agreement with the reference."""
    by_id = {b["id"]: b for b in bees}
    chosen_scores, chosen_ref_scores = [], []
    by_species = {s: {"chosen": 0, "refused": 0} for s in species}
    agreement = {s: {"agree": 0, "total": 0} for s in species}
    by_trait = {t: [{"chosen": 0, "refused": 0} for _ in range(TRAIT_BINS)] for t in traits}
    for ev in decisions:
        d = ev["data"]
        outcome = d["outcome"]
        if outcome == "chosen":
            chosen = [c for c in d["evaluated"] if c["habitat_id"] == d["chosen_habitat_id"]]
            chosen_scores += [c["score"] for c in chosen]
            chosen_ref_scores += [c["reference_score"] for c in chosen if c.get("reference_score") is not None]
        bee = by_id.get(d["bee_id"])  # a removed bee no longer counts in the per-species/trait split
        if bee:
            by_species[bee["species"]][outcome] += 1
            if d.get("agreement") is not None:
                agreement[bee["species"]]["total"] += 1
                agreement[bee["species"]]["agree"] += bool(d["agreement"])
            for t in traits:
                by_trait[t][_bin(bee["personality"][t])][outcome] += 1
    compared = [ev["data"]["agreement"] for ev in decisions if ev["data"].get("agreement") is not None]
    avg = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    return {
        "service": service,  # decision service status (provider, model, revision, device, latency, availability)
        "count": len(decisions),
        "chosen": sum(ev["data"]["outcome"] == "chosen" for ev in decisions),
        "refused": sum(ev["data"]["outcome"] == "refused" for ev in decisions),
        "rejected": sum(ev["data"].get("result") == "rejected" for ev in decisions),
        "avg_chosen_score": avg(chosen_scores),  # probability the source gave to the habitat it chose
        "avg_chosen_reference_score": avg(chosen_ref_scores),  # reference fit of the chosen habitats
        "agreement_rate": avg([float(a) for a in compared]),
        "agreement_by_species": {s: {**a, "rate": round(a["agree"] / a["total"], 3) if a["total"] else None}
                                 for s, a in agreement.items()},
        "by_species": by_species,
        "by_trait": by_trait,
    }
