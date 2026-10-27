"""Paper scenario (docs/decision_agents_llm.md §6) played with real LLM decisions.

Godot holds the world (sites, bees, habitat words from describe()); every bee decision is one Brain call
(one intelligence token, see docs/methode_jeton.md).
shortcut: exploration, dances, recruitment and quorum are orchestrated here, not in Godot; move them to Godot when built.

Run (Ollama running, model installed): python backend/scenarios/scenario_papier.py --model qwen2.5:0.5b --seed 1
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bzz import GodotEngine
from bzz.brain import Brain, OllamaLLM

BRANCH = (500, 350)  # the swarm, at the centre of the 1000 x 700 world
# letter: (type, x, y, feature overrides). A is the best site by the numbers.
SITES = {"A": ("tree_cavity", 500, 100, {}), "B": ("hive_box", 850, 350, {"predator_risk": 0.7}),
         "C": ("rodent_burrow", 500, 620, {})}
BEES = [("S1", "scout", "audacieuse"), ("S2", "scout", "prudente"),
        ("F1", "follower", "prudente"), ("F2", "follower", "audacieuse"), ("F3", "follower", "sociable")]
DISCOVERIES = {"S1": ["B"], "S2": ["C", "A"]}  # what each scout finds while exploring, as on paper
QUORUM = 3
MAX_ROUNDS = 8
STRENGTH = {5: "very strongly", 4: "strongly", 3: "moderately"}


def direction(x, y) -> str:
    dx, dy = x - BRANCH[0], y - BRANCH[1]
    if abs(dx) > abs(dy):
        return "to the east" if dx > 0 else "to the west"
    return "to the south" if dy > 0 else "to the north"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="Ollama model (default: BZZ_MODEL or qwen2.5:0.5b)")
    ap.add_argument("--seed", type=int, default=1, help="run seed")
    args = ap.parse_args()

    llm = OllamaLLM(model=args.model)
    calls = []
    brain = Brain(lambda m, s, seed: calls.append(1) or llm(m, s, seed), run_seed=args.seed)

    engine = GodotEngine()
    engine.start()
    try:
        habitats = {}
        for letter, (kind, x, y, features) in SITES.items():
            h = engine.send("add_habitat", type=kind, x=x, y=y, features=features)
            habitats[letter] = {"id": letter, "description": engine.send("get_entity", id=h["id"])["description"]}
        bees = {}
        for name, role, preset in BEES:
            b = engine.send("add_bee", role=role, name=name, x=BRANCH[0], y=BRANCH[1], personality={"preset": preset})
            bees[name] = {"id": name, "personality": engine.send("get_entity", id=b["id"])["personality"], "preset": preset}
    finally:
        engine.stop()

    print(f"Modèle : {llm.model} · seed du run : {args.seed} · quorum : {QUORUM}\n")
    for letter, h in habitats.items():
        print(f"  Site {letter} ({SITES[letter][0]}, {direction(*SITES[letter][1:3]).removeprefix('to the ')}) : "
              f"{', '.join(h['description'].values())}")
    print()

    committed = {}  # bee -> (site, score, round committed): approved bees count for the quorum and dance
    to_explore = {k: list(v) for k, v in DISCOVERIES.items()}
    say = lambda bee, text: print(f"  {bee} ({bees[bee]['preset']}) {text}")

    def inspect(bee, site, rnd):
        score = brain.decide(bees[bee], "evaluate_site", {"habitat": habitats[site]})["score"]
        choice = brain.decide(bees[bee], "stay_or_leave", {"habitat": habitats[site]})["choice"]
        say(bee, f"inspecte {site} → note {score}/5, {'reste' if choice == 'stay' else 'repart'}")
        if choice == "stay":
            committed[bee] = (site, score, rnd)

    winner = None
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"── Tour {rnd} ──")
        for scout, sites in to_explore.items():
            if scout not in committed and sites:
                inspect(scout, sites.pop(0), rnd)

        # attrition: a bee dances at (score - rounds since approval) while that stays >= 3
        dances = []
        for bee, (site, score, since) in committed.items():
            level = score - (rnd - since)
            if level >= 3:
                dances.append({"site_id": site, "strength": STRENGTH[min(level, 5)], "direction": direction(*SITES[site][1:3])})
                say(bee, f"danse {STRENGTH[min(level, 5)]} pour {site}")

        watchers = [b for b in bees if b not in committed and not to_explore.get(b)]
        for bee in watchers if dances else []:
            follow = brain.decide(bees[bee], "judge_dances", {"dances": dances})["follow"]
            if follow == "none":
                say(bee, "ignore les danses")
            else:
                say(bee, f"suit une danse vers {follow}")
                inspect(bee, follow, rnd)

        counts = {s: sum(c[0] == s for c in committed.values()) for s in SITES}
        print(f"  Abeilles engagées par site : {counts}\n")
        winner = next((s for s, n in counts.items() if n >= QUORUM), None)
        exploring = any(sites for b, sites in to_explore.items() if b not in committed)
        if winner or (not dances and not exploring):  # nothing can change any more
            break

    if winner:
        print(f"Quorum atteint à {winner} : l'essaim s'envole vers {winner}. "
              f"{'Bon choix (A est le meilleur site).' if winner == 'A' else 'Mauvais choix : le meilleur site était A.'}")
    else:
        print("Pas de quorum : l'essaim n'a pas décidé.")
    print(f"Jetons utilisés : {len(calls)} appels LLM · réponses invalides remplacées par défaut : {brain.failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
