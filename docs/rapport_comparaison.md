# Rapport de comparaison : OpenJev et logique de référence

_Généré le 2026-10-20 par `python -m bzz.decision.compare` (scénarios fixes : [`backend/bzz/decision/compare.py`](../backend/bzz/decision/compare.py))._

- Modèle : `alanhuangya/OpenJev-1.7B`, révision `7418ae8b6e3b`, appareil `mps` (float32).
- 75 décisions : 5 espèces × 5 profils de personnalité × 3 jeux d'habitats ; graines fixes.
- Temps de réponse médian du modèle : 570 ms.
- Rien n'est appliqué : chaque abeille est seulement évaluée par les deux logiques.
- **Abeilles mellifères = essaims** (10 000 ouvrières, délai de grappe complet). OpenJev reçoit aussi la population, le délai restant et la distance depuis la grappe ; **la logique de référence ignore le délai et la distance**, donc un désaccord sur un essaim peut venir de ces informations supplémentaires.

## Taux d'accord global : 56 % (42/75)

Meilleur habitat identique (en ignorant le seuil d'acceptation) : 77 % (58/75).

| Type de résultat | Décisions |
|---|---|
| accord : refus des deux côtés | 27 |
| OpenJev refuse, la référence choisit | 26 |
| accord : même habitat | 15 |
| OpenJev choisit, la référence refuse | 5 |
| habitats différents | 2 |

## Par espèce

| | Accord |
|---|---|
| honey_bee | 60 % (9/15) |
| bumblebee | 40 % (6/15) |
| mason_bee | 53 % (8/15) |
| mining_bee | 67 % (10/15) |
| carpenter_bee | 60 % (9/15) |

## Par profil de personnalité

| | Accord |
|---|---|
| prudente | 67 % (10/15) |
| audacieuse | 60 % (9/15) |
| sociable | 60 % (9/15) |
| curieuse | 47 % (7/15) |
| équilibrée | 47 % (7/15) |

## Par jeu d'habitats

| | Accord |
|---|---|
| variés | 44 % (11/25) |
| contrastés | 36 % (9/25) |
| médiocres | 88 % (22/25) |

## Formulations essayées

Mesurées sur ces 75 scénarios le 2026-10-20, avant l'introduction des essaims (abeilles mellifères alors individuelles) ; seule la dernière est dans le code ([`prompting.py`](../backend/bzz/decision/prompting.py)).

| Formulation | Accord | Comportement |
|---|---|---|
| A — une question « quel habitat ? » avec l'option « aucun » | 41 % | ne refuse presque jamais (32 choix là où la référence refuse) |
| B — deux questions : meilleur habitat + « atteint le seuil ? » | 51 % | refuse souvent, excellent sur les habitats médiocres (92 %) |
| C — B + écart à l'idéal de chaque critère dans la description | 53 % | retenue |

## Désaccords

| Jeu | Espèce | Profil | OpenJev (p) | Référence (score) | Seuil |
|---|---|---|---|---|---|
| variés | honey_bee | audacieuse | aucun (0.52) | hab-1 (0.78) | 0.45 |
| variés | honey_bee | sociable | aucun (0.57) | hab-1 (0.75) | 0.55 |
| variés | honey_bee | curieuse | aucun (0.57) | hab-1 (0.78) | 0.50 |
| variés | honey_bee | équilibrée | aucun (0.61) | hab-1 (0.72) | 0.55 |
| variés | bumblebee | audacieuse | hab-4 (0.15) | hab-5 (0.78) | 0.45 |
| variés | bumblebee | sociable | aucun (0.55) | hab-5 (0.74) | 0.55 |
| variés | bumblebee | curieuse | aucun (0.57) | hab-5 (0.75) | 0.50 |
| variés | bumblebee | équilibrée | aucun (0.56) | hab-5 (0.69) | 0.55 |
| variés | mason_bee | curieuse | aucun (0.55) | hab-7 (0.84) | 0.50 |
| variés | mason_bee | équilibrée | aucun (0.52) | hab-7 (0.79) | 0.55 |
| variés | mining_bee | prudente | hab-6 (0.64) | aucun (0.62) | 0.70 |
| variés | carpenter_bee | prudente | hab-8 (0.55) | aucun (0.66) | 0.70 |
| variés | carpenter_bee | sociable | aucun (0.52) | hab-8 (0.71) | 0.55 |
| variés | carpenter_bee | curieuse | aucun (0.56) | hab-8 (0.79) | 0.50 |
| contrastés | honey_bee | prudente | aucun (0.50) | hab-8 (0.69) | 0.70 |
| contrastés | honey_bee | équilibrée | aucun (0.56) | hab-8 (0.70) | 0.55 |
| contrastés | bumblebee | audacieuse | hab-7 (0.20) | hab-10 (0.83) | 0.45 |
| contrastés | bumblebee | sociable | aucun (0.56) | hab-10 (0.71) | 0.55 |
| contrastés | bumblebee | curieuse | aucun (0.58) | hab-10 (0.74) | 0.50 |
| contrastés | bumblebee | équilibrée | aucun (0.58) | hab-10 (0.73) | 0.55 |
| contrastés | mason_bee | prudente | aucun (0.54) | hab-3 (0.72) | 0.70 |
| contrastés | mason_bee | audacieuse | aucun (0.51) | hab-3 (0.88) | 0.45 |
| contrastés | mason_bee | sociable | aucun (0.54) | hab-3 (0.83) | 0.55 |
| contrastés | mason_bee | curieuse | aucun (0.56) | hab-3 (0.86) | 0.50 |
| contrastés | mason_bee | équilibrée | aucun (0.53) | hab-3 (0.81) | 0.55 |
| contrastés | mining_bee | prudente | hab-1 (0.38) | aucun (0.62) | 0.70 |
| contrastés | mining_bee | curieuse | aucun (0.50) | hab-1 (0.66) | 0.50 |
| contrastés | carpenter_bee | sociable | aucun (0.54) | hab-5 (0.70) | 0.55 |
| contrastés | carpenter_bee | curieuse | aucun (0.57) | hab-5 (0.82) | 0.50 |
| contrastés | carpenter_bee | équilibrée | aucun (0.55) | hab-5 (0.74) | 0.55 |
| médiocres | bumblebee | audacieuse | aucun (0.59) | hab-2 (0.49) | 0.45 |
| médiocres | mining_bee | audacieuse | hab-4 (0.56) | aucun (0.34) | 0.45 |
| médiocres | mining_bee | équilibrée | hab-4 (0.52) | aucun (0.27) | 0.55 |
