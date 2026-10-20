"""Fixed, reproducible scenarios comparing OpenJev with the reference logic (nothing is applied).

    python -m bzz.decision.compare            # needs the OpenJev service (DECISION_SERVICE_URL)

5 species x 5 personality presets x 3 habitat sets = 75 decisions. Every bee has a fixed seed, so the reference
logic (curiosity noise included) gives the same answers on every run. Writes docs/comparison/results.json and
docs/rapport_comparaison.md.
"""

import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from ..engine import GodotEngine
from .prompting import DEFAULT_MAX_CANDIDATES, eligible_candidates
from .providers import OpenJevProvider, ReferenceProvider

DOCS = Path(__file__).resolve().parents[3] / "docs"
SPECIES = ["honey_bee", "bumblebee", "mason_bee", "mining_bee", "carpenter_bee"]
PROFILES = ["prudente", "audacieuse", "sociable", "curieuse", "équilibrée"]
BEE_POSITION = (500, 350)
SWARM_POPULATION = 10000

# (type, x, y, feature overrides); every set offers at least one habitat type to every species
HABITAT_SETS = {
    "variés": [
        ("tree_cavity", 300, 200, {}),
        ("tree_cavity", 700, 200, {"cavity_volume_l": 100, "entrance_height_m": 1}),
        ("hive_box", 400, 500, {}),
        ("hive_box", 600, 500, {"cavity_volume_l": 10}),
        ("rodent_burrow", 200, 400, {}),
        ("bare_soil", 800, 400, {}),
        ("hollow_stem", 500, 150, {}),
        ("dead_wood", 500, 600, {}),
    ],
    "contrastés": [
        ("bare_soil", 300, 300, {"sun_exposure": 0.95, "humidity": 0.15}),
        ("bare_soil", 700, 300, {"sun_exposure": 0.3, "humidity": 0.8}),
        ("hollow_stem", 400, 200, {"entrance_diameter_mm": 7, "sun_exposure": 0.9}),
        ("hollow_stem", 600, 200, {"entrance_diameter_mm": 12, "sun_exposure": 0.3}),
        ("dead_wood", 400, 500, {"sun_exposure": 0.85, "humidity": 0.15}),
        ("dead_wood", 600, 500, {"sun_exposure": 0.3, "humidity": 0.7}),
        ("tree_cavity", 250, 450, {"predator_risk": 0.8}),
        ("hive_box", 750, 450, {"previously_occupied": True, "predator_risk": 0.1}),
        ("rodent_burrow", 500, 650, {"humidity": 0.9}),
        ("rodent_burrow", 500, 80, {}),
    ],
    "médiocres": [
        ("tree_cavity", 300, 250, {"cavity_volume_l": 15, "entrance_height_m": 1.5}),
        ("hive_box", 700, 250, {"cavity_volume_l": 90, "entrance_height_m": 0.5}),
        ("rodent_burrow", 300, 450, {"cavity_volume_l": 12, "humidity": 0.9}),
        ("bare_soil", 700, 450, {"sun_exposure": 0.4, "humidity": 0.6}),
        ("hollow_stem", 500, 200, {"entrance_diameter_mm": 11.5, "sun_exposure": 0.4, "entrance_height_m": 3}),
        ("dead_wood", 500, 550, {"sun_exposure": 0.3, "humidity": 0.65}),
    ],
}


def run_scenarios(provider) -> list[dict]:
    rows = []
    for set_index, (set_name, habitats) in enumerate(HABITAT_SETS.items()):
        with GodotEngine() as engine:
            for t, x, y, f in habitats:
                engine.send("add_habitat", type=t, x=x, y=y, features=f)
            reference = ReferenceProvider(engine)
            for i, species in enumerate(SPECIES):
                for j, profile in enumerate(PROFILES):
                    seed = 1000 + 100 * set_index + 10 * i + j
                    where = {"x": BEE_POSITION[0], "y": BEE_POSITION[1], "personality": {"preset": profile, "seed": seed}}
                    if species == engine.catalog["swarm"]["species"]:  # honey bees exist only as swarms
                        bee = engine.send("add_swarm", population=SWARM_POPULATION, **where)
                    else:
                        bee = engine.send("add_bee", species=species, **where)
                    situation = engine.send("get_decision_situation", bee_id=bee["id"])
                    candidates = eligible_candidates(situation, DEFAULT_MAX_CANDIDATES)
                    decision = provider.decide(situation, candidates)
                    ref = reference.decide(situation, candidates)
                    ids = {h["id"]: h["type"] for h in candidates}
                    rows.append({
                        "set": set_name, "species": species, "profile": profile, "seed": seed,
                        "swarm": bee["kind"] == "swarm",
                        "candidates": ids,
                        "openjev": decision["choice"], "openjev_best": decision.get("best"),
                        "probabilities": decision["probabilities"],
                        "latency_ms": decision["latency_ms"],
                        "reference": ref["choice"], "threshold": ref["threshold"],
                        "reference_scores": {s["habitat_id"]: round(s["score"], 3) for s in ref["scores"]},
                        "agreement": decision["choice"] == ref["choice"],
                    })
    return rows


def _rate(rows) -> str:
    n = len(rows)
    agree = sum(r["agreement"] for r in rows)
    return f"{100 * agree / n:.0f} % ({agree}/{n})" if n else "—"


def summarize(rows: list[dict]) -> dict:
    kinds = Counter()
    for r in rows:
        if r["agreement"]:
            kinds["accord : même habitat" if r["openjev"] else "accord : refus des deux côtés"] += 1
        elif r["openjev"] is None:
            kinds["OpenJev refuse, la référence choisit"] += 1
        elif r["reference"] is None:
            kinds["OpenJev choisit, la référence refuse"] += 1
        else:
            kinds["habitats différents"] += 1
    same_best = sum(r["openjev_best"] == max(r["reference_scores"], key=r["reference_scores"].get) for r in rows)
    return {"total": len(rows), "agreement": sum(r["agreement"] for r in rows), "kinds": dict(kinds),
            "same_best": same_best,
            "latency_ms_median": statistics.median(r["latency_ms"] for r in rows)}


def write_report(rows: list[dict], info: dict, path: Path) -> None:
    s = summarize(rows)
    groups = {k: defaultdict(list) for k in ("species", "profile", "set")}
    for r in rows:
        for k in groups:
            groups[k][r[k]].append(r)
    lines = [
        "# Rapport de comparaison : OpenJev et logique de référence",
        "",
        f"_Généré le {date.today().isoformat()} par `python -m bzz.decision.compare` "
        "(scénarios fixes : [`backend/bzz/decision/compare.py`](../backend/bzz/decision/compare.py))._",
        "",
        f"- Modèle : `{info.get('model')}`, révision `{(info.get('revision') or '')[:12]}`, appareil `{info.get('device')}` "
        f"({info.get('dtype')}).",
        f"- {s['total']} décisions : 5 espèces × 5 profils de personnalité × 3 jeux d'habitats ; graines fixes.",
        f"- Temps de réponse médian du modèle : {s['latency_ms_median']:.0f} ms.",
        "- Rien n'est appliqué : chaque abeille est seulement évaluée par les deux logiques.",
        "- **Abeilles mellifères = essaims** (10 000 ouvrières, délai de grappe complet). OpenJev reçoit aussi la "
        "population, le délai restant et la distance depuis la grappe ; **la logique de référence ignore le délai et "
        "la distance**, donc un désaccord sur un essaim peut venir de ces informations supplémentaires.",
        "",
        f"## Taux d'accord global : {_rate(rows)}",
        "",
        f"Meilleur habitat identique (en ignorant le seuil d'acceptation) : "
        f"{100 * s['same_best'] / s['total']:.0f} % ({s['same_best']}/{s['total']}).",
        "",
        "| Type de résultat | Décisions |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(s["kinds"].items(), key=lambda kv: -kv[1])],
    ]
    titles = {"species": "Par espèce", "profile": "Par profil de personnalité", "set": "Par jeu d'habitats"}
    for k, title in titles.items():
        lines += ["", f"## {title}", "", "| | Accord |", "|---|---|"]
        lines += [f"| {name} | {_rate(rs)} |" for name, rs in groups[k].items()]
    lines += ["", "## Formulations essayées", "",
              "Mesurées sur ces 75 scénarios le 2026-10-20, avant l'introduction des essaims (abeilles mellifères alors individuelles) ; seule la dernière est dans le code "
              "([`prompting.py`](../backend/bzz/decision/prompting.py)).", "",
              "| Formulation | Accord | Comportement |", "|---|---|---|",
              "| A — une question « quel habitat ? » avec l'option « aucun » | 41 % | ne refuse presque jamais "
              "(32 choix là où la référence refuse) |",
              "| B — deux questions : meilleur habitat + « atteint le seuil ? » | 51 % | refuse souvent, "
              "excellent sur les habitats médiocres (92 %) |",
              "| C — B + écart à l'idéal de chaque critère dans la description | 53 % | retenue |"]
    lines += ["", "## Désaccords", "",
              "| Jeu | Espèce | Profil | OpenJev (p) | Référence (score) | Seuil |", "|---|---|---|---|---|---|"]
    for r in rows:
        if not r["agreement"]:
            oj = r["openjev"] or "aucun"
            p = r["probabilities"].get(r["openjev"] or "none", 0)
            ref = r["reference"] or "aucun"
            rs = r["reference_scores"].get(r["reference"], max(r["reference_scores"].values(), default=0))
            lines.append(f"| {r['set']} | {r['species']} | {r['profile']} | {oj} ({p:.2f}) | {ref} ({rs:.2f}) "
                         f"| {r['threshold']:.2f} |")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    provider = OpenJevProvider(os.environ.get("DECISION_SERVICE_URL") or "http://127.0.0.1:8009", timeout=120)
    info = provider.status()
    if not info["available"]:
        sys.exit(f"OpenJev service unavailable: {info['error']}")
    rows = run_scenarios(provider)
    out = DOCS / "comparison"
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps({"model": info, "summary": summarize(rows), "rows": rows},
                                                 indent=1, ensure_ascii=False) + "\n")
    write_report(rows, info, DOCS / "rapport_comparaison.md")
    print(f"agreement {_rate(rows)} -> docs/rapport_comparaison.md")


if __name__ == "__main__":
    main()
