"""Turns a decision situation from Godot into an OpenJev request (POST /v1/systemone).

OpenJev is not retrained: it learns the project's choice logic (Bee.score_breakdown / choose_habitat,
docs/reference_abeilles.md §3-5) from how the situation and the question are written. The state states the
rules in English (the model's language) with the bee's preferences, personality and threshold, and describes
each candidate habitat. Reference scores are NEVER included: the model would just copy them.
"""

NONE_OPTION = "none"
DEFAULT_MAX_CANDIDATES = 12  # keeps the state far below OpenJev's 4096-token state limit (~60 tokens per habitat)

SPECIES = {
    "honey_bee": "honey bee (Apis mellifera), a social bee whose swarm needs a nest cavity",
    "bumblebee": "buff-tailed bumblebee (Bombus terrestris), a queen founding a colony, usually underground",
    "mason_bee": "red mason bee (Osmia bicornis), a solitary bee nesting in hollow stems or holes",
    "mining_bee": "mining bee (Andrena), a solitary bee digging its burrow in bare soil",
    "carpenter_bee": "violet carpenter bee (Xylocopa violacea), a solitary bee digging tunnels in dead wood",
}
HABITAT_TYPES = {
    "tree_cavity": "tree cavity", "hive_box": "hive box", "rodent_burrow": "old rodent burrow",
    "bare_soil": "bare soil", "hollow_stem": "hollow stems", "dead_wood": "dead wood",
}
FEATURES = {  # feature -> (label, unit)
    "cavity_volume_l": ("cavity volume", "L"),
    "entrance_diameter_mm": ("entrance diameter", "mm"),
    "entrance_height_m": ("entrance height above ground", "m"),
    "sun_exposure": ("sun exposure", "from 0 to 1"),
    "humidity": ("humidity", "from 0 to 1"),
    "floral_abundance": ("flowers nearby", "from 0 to 1"),
    "previously_occupied": ("old nest present", "1 = yes, 0 = no"),
}
TRAITS = {  # trait -> (meaning, effect when high, medium, low)
    "pickiness": ("how demanding the bee is", "needs a very good overall fit", "needs a fair overall fit",
                  "accepts a modest fit"),
    "boldness": ("tolerance to predator risk", "barely cares about predator risk", "is moderately wary of predators",
                 "strongly avoids predator risk"),
    "sociability": ("attitude to busy shared sites", "prefers sites where other bees already nest",
                    "is indifferent to other nests", "avoids sites where other bees already nest"),
    "curiosity": ("how unpredictable its judgement is", "sometimes picks a slightly worse site",
                  "is mostly consistent", "judges consistently"),
}
RULES = [
    "Each preference gives a fit between 0 and 1: 1 at the ideal value, falling linearly to 0 at ideal plus or minus "
    "the tolerance.",
    "The overall fit is the weighted average of the preference fits (a weight of 2 counts twice).",
    "Predator risk lowers the overall fit by risk x (1 - boldness).",
    "On a site that hosts several nests, a sociability above 0.5 adds up to 0.2 in proportion to how busy the site is; "
    "below 0.5 it removes up to 0.2.",
    "Only habitat types the species accepts, with free space, are listed as candidates.",
    "Choose the candidate with the best overall fit if that fit reaches the acceptance threshold; otherwise choose none.",
]


def _num(v: float) -> str:
    return f"{v:g}"


def _level(v: float) -> str:
    return "high" if v >= 0.67 else "low" if v <= 0.33 else "medium"


def eligible_candidates(situation: dict, max_candidates: int = DEFAULT_MAX_CANDIDATES) -> list[dict]:
    """Eligible habitats (type accepted, free space), nearest first, cut to max_candidates (documented preselection)."""
    eligible = [h for h in situation["habitats"] if h["eligible"]]
    return sorted(eligible, key=lambda h: (h["distance"], h["id"]))[:max_candidates]


def describe_habitat(h: dict, preferences: list[dict]) -> str:
    """Type, each preferred feature with its distance to the ideal (plain arithmetic, no fit score), risk, occupancy."""
    f = h["features"]
    parts = [HABITAT_TYPES.get(h["type"], h["type"])]
    for p in preferences:
        label, unit = FEATURES[p["criterion"]]
        v = float(f[p["criterion"]])
        dev = abs(v - p["ideal"])
        where = ("at the ideal" if dev == 0 else "outside the tolerance" if dev >= p["tolerance"]
                 else f"{_num(round(dev, 3))} from the ideal, tolerance {_num(p['tolerance'])}")
        parts.append(f"{label} {_num(v)}{' ' + unit if unit in ('L', 'mm', 'm') else ''} ({where})")
    parts.append(f"predator risk {_num(f['predator_risk'])}")
    if h["capacity"] > 1:
        parts.append(f"{h['occupants']} of {h['capacity']} nest places taken")
    return ", ".join(parts)


def build_request(situation: dict, candidates: list[dict]) -> dict:
    """OpenJev request: the state (bee, rules, candidates) and two questions answered in the same pass:
    "best" (which candidate fits best) and "accept" (does that best fit reach the acceptance threshold).
    Splitting "which" from "good enough" agreed best with the reference logic (docs/rapport_comparaison.md)."""
    bee = situation["bee"]
    prefs = bee["preferences"]
    preferences = []
    for p in prefs:
        label, unit = FEATURES[p["criterion"]]
        preferences.append(f"{label} ({unit}): ideal {_num(p['ideal'])}, tolerance {_num(p['tolerance'])}, "
                           f"weight {_num(p['weight'])}")
    personality = {}
    for trait, (meaning, *effects) in TRAITS.items():
        v = bee["personality"][trait]
        level = _level(v)
        effect = effects[["high", "medium", "low"].index(level)]
        personality[f"{trait} {v:.2f} ({level})"] = f"{meaning}: {effect}"
    threshold = bee["acceptance_threshold"]
    candidates_text = {h["id"]: describe_habitat(h, prefs) for h in candidates}
    state = {
        "task": "A bee is choosing a habitat to nest in. Judge every candidate with this bee's preferences and "
                "personality, following the rules.",
        "bee": SPECIES.get(bee["species"], bee["species"]),
        "accepted habitat types": ", ".join(HABITAT_TYPES.get(t, t) for t in bee["accepted_habitat_types"]),
        "preferences": preferences,
        "personality": personality,
        "acceptance threshold": f"{threshold:.2f} (minimum overall fit to accept a habitat)",
        "rules": RULES,
        "candidates": candidates_text,
    }
    return {"state": state, "questions": {
        "best": {"type": "choice", "instructions": "Which candidate has the best overall fit for this bee?",
                 "criteria": candidates_text},
        "accept": {"type": "noul",
                   "instructions": f"The best candidate's overall fit reaches this bee's acceptance threshold "
                                   f"({threshold:.2f}).",
                   "criteria": {"true": "Good enough: the bee settles there.",
                                "false": "Not good enough: the bee keeps looking."}},
    }}


def read_answer(answers: dict) -> tuple[str | None, dict, str]:
    """(choice or None, probability of every option including "none", best candidate) from OpenJev's answers.
    P(habitat) = P(best = habitat) x P(accept); P(none) = 1 - P(accept)."""
    best = answers["best"]
    p_accept = answers["accept"]["noul"]
    probabilities = {k: round(v * p_accept, 4) for k, v in best["probabilities"].items()}
    probabilities[NONE_OPTION] = round(1 - p_accept, 4)
    return (best["choice"] if p_accept >= 0.5 else None), probabilities, best["choice"]
