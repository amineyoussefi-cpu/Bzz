"""Dashboard indicators, computed from the state, entities and events Godot provides (never simulated here)."""

TRAIT_BINS = 5  # 0-0.2, 0.2-0.4, ... 0.8-1


def _bin(value: float) -> int:
    return min(int(value * TRAIT_BINS), TRAIT_BINS - 1)


def compute(state: dict, entities: list[dict], decisions: list[dict], catalog: dict) -> dict:
    habitats = [e for e in entities if e["kind"] == "habitat"]
    bees = [e for e in entities if e["kind"] == "bee"]
    traits = [t["name"] for t in catalog["traits"]]
    species = [s["name"] for s in catalog["species"]]
    return {
        "sim": {
            "tick": state["tick"],
            "seconds": round(state["tick"] / state["ticks_per_second"], 2),
            "paused": state["paused"],
            "speed": state["speed"],
        },
        "habitats_by_type": {t["name"]: sum(h["type"] == t["name"] for h in habitats) for t in catalog["habitat_types"]},
        "bees_by_species": {s: sum(b["species"] == s for b in bees) for s in species},
        "trait_distribution": {t: [sum(_bin(b["personality"][t]) == i for b in bees) for i in range(TRAIT_BINS)]
                               for t in traits},
        "bees_settled": sum(b["home_id"] is not None for b in bees),
        "bees_homeless": sum(b["home_id"] is None for b in bees),
        "occupancy": [{"id": h["id"], "type": h["type"], "occupants": h["occupants"], "capacity": h["capacity"],
                       "rate": h["occupants"] / h["capacity"]} for h in habitats],
        "decisions": _decision_kpi(decisions, bees, species, traits, state.get("decision_mechanism")),
    }


def _decision_kpi(decisions: list[dict], bees: list[dict], species: list[str], traits: list[str], mechanism) -> dict:
    """Aggregates "decision" events (format in docs/api.md). Empty until a decision mechanism exists."""
    by_id = {b["id"]: b for b in bees}
    chosen_scores = []
    by_species = {s: {"chosen": 0, "refused": 0} for s in species}
    by_trait = {t: [{"chosen": 0, "refused": 0} for _ in range(TRAIT_BINS)] for t in traits}
    for ev in decisions:
        d = ev["data"]
        outcome = d["outcome"]
        if outcome == "chosen":
            chosen_scores += [c["score"] for c in d["evaluated"] if c["habitat_id"] == d["chosen_habitat_id"]]
        bee = by_id.get(d["bee_id"])  # a removed bee no longer counts in the per-species/trait split
        if bee:
            by_species[bee["species"]][outcome] += 1
            for t in traits:
                by_trait[t][_bin(bee["personality"][t])][outcome] += 1
    return {
        "mechanism": mechanism,  # None until the next step plugs a decision mechanism in
        "count": len(decisions),
        "chosen": sum(ev["data"]["outcome"] == "chosen" for ev in decisions),
        "refused": sum(ev["data"]["outcome"] == "refused" for ev in decisions),
        "avg_chosen_score": round(sum(chosen_scores) / len(chosen_scores), 3) if chosen_scores else None,
        "by_species": by_species,
        "by_trait": by_trait,
    }
