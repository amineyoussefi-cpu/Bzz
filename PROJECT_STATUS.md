# PROJECT_STATUS

_Dernière mise à jour : 2026-10-20 (prompt 5 : décisions des abeilles avec OpenJev)_

Référence de reprise entre sessions. Ne décrit que ce qui existe réellement dans le dépôt.
Spécifications d'origine : [prompts/](prompts/) (`prompt1.txt` à `prompt5.txt`, `github_versioning.txt`, `portability.txt`).

## Architecture actuelle

```
Tableau de bord ◄─HTTP+WebSocket─► Backend Python (Docker ou local) ◄─TCP JSON─► Godot 4.7 headless
  bzz/static/index.html              bzz/server.py (API, KPI, relevé d'événements)  main.gd → WorldApi
                                     bzz/decision/ (boucle de décision)             (état du monde, validation)
                                          │
                                          └─HTTP local─► Service OpenJev (HORS Docker : decision/service.py)
                                                          modèle alanhuangya/OpenJev-1.7B, CUDA / MPS / CPU
```

- **Godot** possède l'état du monde. Il décrit la situation d'une abeille, **valide et applique** les décisions, et
  publie les événements.
- **Le backend** orchestre : situation → requête → OpenJev → comparaison avec la référence → application par Godot.
  Il expose l'API et calcule les KPI.
- **Le service OpenJev** tourne sur la machine de l'utilisateur, sans Docker (Docker sur Mac n'a pas accès au GPU).
  Il n'a besoin ni de clé API ni de réseau, hormis le téléchargement initial des poids.
- **Le tableau de bord** est un client du backend (décision du prompt 4) ; l'entrée stdin fonctionne toujours.
- **Modes Godot** (`GODOT_HOST`) : local (Python lance Godot ; import automatique si le cache `.godot/` manque) ou
  distant (Compose).

Fichiers :

- **godot/main.gd** — serveur TCP (`--host`, `--port`, `--world-width`, `--world-height`), délègue à `WorldApi`.
- **godot/api/world_api.gd** — catalogue, entités (`hab-N`/`bee-N`), horloge (tick, pause, vitesse), journal
  d'événements, validation. Décisions :
  - `get_decision_situation` : profil de l'abeille et tous les habitats, avec leur éligibilité ;
  - `apply_decision` : validation, puis `Bee.settle` ou rejet, et événement `decision` ;
  - `reference_decision` : `Bee.score_breakdown` + `choose_habitat`, pour comparaison uniquement, jamais appliqué.
- **godot/entities/** — `Habitat`, `HabitatCatalog`, `Bee` (logique de choix d'origine **inchangée**, utilisée
  uniquement comme référence), `BeePersonality`, `Preference`, `BeeSpecies`, `DecisionEvent` (format des décisions,
  avec probabilités, référence, accord, modèle). Rôles dans `roles/` : jamais exécutés.
- **backend/bzz/decision/** :
  - `prompting.py` : construit la situation et les questions envoyées à OpenJev, présélectionne les candidats et lit
    la réponse ;
  - `providers.py` : interface `DecisionProvider`, avec `OpenJevProvider` (HTTP vers le service) et
    `ReferenceProvider` (Godot `reference_decision`) ;
  - `loop.py` : `DecisionLoop`, cadence, concurrence, pause, service indisponible ;
  - `compare.py` : scénarios fixes et rapport de comparaison.
- **backend/bzz/** — `engine.py` (connexion + verrou), `commands.py` (liste blanche + validation à partir du
  catalogue), `server.py` (API + WebSocket + boucle de décision), `kpi.py`, `static/index.html`, `__main__.py` (stdin).
- **decision/** (service hors Docker) — `service.py` (`POST /v1/systemone`, `GET /health`), `requirements.txt`
  (versions figées), `start.sh` (macOS), `start.ps1` (Windows + NVIDIA). `.venv/` et `.cache/` (poids) sont ignorés
  par git.
- **Tests** — `godot/tests/test_entities.gd` ; `backend/tests/` : `test_engine`, `test_protocol`, `test_server`,
  `test_decisions` (avec `fakes.FakeProvider`), `test_entities`.
- **Docs** :
  - [docs/api.md](docs/api.md) : commandes, routes, événements, KPI ;
  - [docs/decision_service.md](docs/decision_service.md) : installation macOS et Windows, paramètres, mesures,
    format des requêtes, conditions d'utilisation ;
  - [docs/rapport_comparaison.md](docs/rapport_comparaison.md) (+ `docs/comparison/results.json`) ;
  - références abeilles et rôles (Markdown + PDF).
- **Docker** — `Dockerfile` (cibles `godot` et `backend`) et `compose.yaml`. Le backend joint le service OpenJev de
  l'hôte via `DECISION_SERVICE_URL_FROM_DOCKER` (`host.docker.internal`, `extra_hosts` pour Linux) ; le port de Godot
  reste interne.

## Fonctionnalités implémentées

- **Construction du monde** depuis le tableau de bord ou l'API : habitats, abeilles (personnalité par préréglage,
  traits ou aléatoire, avec **graine facultative pour toutes les formes**), consultation, retrait, remise à zéro,
  pause, reprise et vitesse.
- **Décisions par OpenJev**, uniquement quand la simulation tourne :
  - tous les `DECISION_INTERVAL_TICKS` ticks, chaque abeille sans habitat demande une décision, avec au plus
    `DECISION_CONCURRENCY` décisions à la fois, exécutées dans des threads, sans bloquer l'API ni Godot ;
  - OpenJev reçoit les habitats éligibles les plus proches (12 au maximum) et répond à deux questions en une passe :
    « meilleur habitat ? » et « atteint le seuil ? » ;
  - Godot valide la décision : une décision invalide est rejetée et produit un événement de refus. L'abeille
    s'installe sans se déplacer.
- **Comparaison** : à chaque décision, la logique de référence calcule son choix sans l'appliquer. L'événement
  contient les deux choix, les probabilités et l'accord.
- **Service indisponible** : aucune décision n'est prise, l'état est affiché, et il n'y a **pas de bascule** vers la
  référence.
- **Tableau de bord** :
  - fil des décisions (choix ou refus, probabilités, source, choix de référence, accord) ;
  - choix, refus et rejets ; probabilité moyenne et score de référence moyen des habitats choisis ;
  - accord global et par espèce ; répartition par espèce et par trait ;
  - état du service : modèle, révision, appareil, temps de réponse, disponibilité ;
  - KPI du monde (prompt 4).

Commandes du protocole : voir [docs/api.md](docs/api.md) §2 (ajoutées à cette étape : `get_decision_situation`,
`apply_decision`, `reference_decision` ; `get_state` ne contient plus `decision_mechanism`).

## Résultats

**Test préalable sur Mac (M4 Pro, 24 Go)** : le modèle se charge et répond.

| Appareil | Chargement depuis le cache | Requête courte | Requête du projet | Mémoire |
|---|---|---|---|---|
| MPS | 2,5 s | ~97 ms | ~550 ms | 7,7 Go GPU (float32) |
| Processeur | 1,2 s | ~295 ms | non mesuré | ~10,6 Go RAM |

Le premier téléchargement (3,2 Go) a pris environ 6 minutes. La configuration Windows + NVIDIA **n'a pas été testée**.

**Comparaison avec la logique de référence** (75 scénarios fixes : 5 espèces × 5 profils × 3 jeux d'habitats ;
[rapport](docs/rapport_comparaison.md)) :

- **53 % d'accord** sur la décision finale ;
- **75 %** sur le meilleur habitat, en ignorant le seuil d'acceptation.

Le désaccord porte surtout sur « assez bon pour s'installer » autour du seuil. Trois formulations ont été essayées
(41 %, 51 %, puis 53 % pour celle retenue). **Conclusion : la logique de référence ne peut pas encore être supprimée.**

## Utilisation

```sh
./decision/start.sh                     # macOS ; Windows : .\decision\start.ps1 (1er lancement : installe + télécharge)
docker compose up -d                    # puis http://localhost:8000 : ajouter habitats et abeilles, « Lancer »
# sans Docker : cd backend && ../.venv/bin/python -m bzz.server
cd backend && ../.venv/bin/python -m bzz.decision.compare      # régénère le rapport de comparaison (service requis)
../.venv/bin/python -m unittest discover tests                 # 36 tests ; le test du vrai modèle n'est lancé que si le service répond
docker compose run --rm -e GODOT_HOST= backend python -m unittest discover tests   # tests dans Docker (sans modèle)
```

## Décisions techniques

- **OpenJev hors Docker** : un service HTTP local (`decision/service.py`) reprend les formats `POST /v1/systemone`
  d'OpenJev et ajoute `GET /health`. `wev serve` n'a pas été utilisé car il ne permet ni de figer la révision ni de
  choisir le cache.
- **Révision figée** (`7418ae8b…`) ; modèle, révision, appareil et cache sont des paramètres. Les poids sont
  téléchargés une fois, puis chargés hors ligne (`HF_HUB_OFFLINE`).
- **Une seule passe par décision**, avec deux questions (choix + oui/non). P(habitat) = P(meilleur) × P(accepter) ;
  l'abeille s'installe si P(accepter) ≥ 0,5. **Aucun score de référence n'est transmis** au modèle (un test le
  vérifie). Chaque critère est décrit par son écart à l'idéal rapporté à la tolérance.
- **Présélection** : seuls les habitats éligibles, les 12 plus proches. Sans candidat, ni appel au modèle ni événement.
- **Godot valide tout** avant d'appliquer. Un rejet produit un événement `decision` avec `result: "rejected"`.
- **Cadence en ticks de simulation** : elle respecte la pause et la vitesse. Une décision reçue alors que la
  simulation est en pause est abandonnée.
- **Pas de bascule silencieuse** vers la référence : `ReferenceProvider` ne sert qu'à comparer.
- **Graine possible avec un préréglage ou des traits** : elle rend reproductible le bruit de curiosité de la référence,
  ce qui est nécessaire aux scénarios fixes.
- Hérité : TCP JSON en requête/réponse, relevé des événements avec curseur, verrou sur la connexion, validation
  double, noms lisibles générés, configuration par variables d'environnement, entités en GDScript.

## Problèmes connus / limites

- **Accord avec la référence de 53 %** seulement : le modèle juge mal le seuil d'acceptation.
- **Windows + NVIDIA non testé** : le script installe torch CUDA 12.6, ou 13.0 pour les RTX 50xx. Le modèle 4B n'a
  pas été testé non plus.
- **Temps de réponse** : ~0,5 à 1,4 s par décision sur MPS. Le service traite une requête à la fois, donc beaucoup
  d'abeilles allongent le délai entre deux décisions d'une même abeille.
- **Refus répétés** : une abeille qui refuse redemande une décision à chaque intervalle, ce qui ajoute un événement
  de refus à chaque fois.
- **Bruit de curiosité** : la référence le tire à chaque évaluation, donc son choix peut rarement différer du meilleur
  score affiché.
- **Conditions d'utilisation** : certaines données d'entraînement du modèle sont réservées à la recherche ou soumises
  aux conditions de qwen3-max. **Vérifier avant tout usage commercial** (docs/decision_service.md §7).
- **Service de décision** : il écoute sur `127.0.0.1` par défaut. Sous Linux avec Docker, il faut
  `OPENJEV_HOST=0.0.0.0`.
- **Pas d'authentification** : le tableau de bord n'est publié que sur `127.0.0.1`.
- **Pas de sauvegarde du monde.** Les KPI de décision repartent de zéro quand le backend redémarre.
- **Capture WebSocket** : les entités peuvent précéder leurs événements d'un relevé (≤ 250 ms).
- **Erreur de syntaxe GDScript** : Godot ne quitte pas, et `start()` échoue seulement après le délai (10 s).
- **Tests** : ils supposent le mode local (`GODOT_HOST=` vide).

## Tâches en cours

- Aucune.

## Prochaines étapes possibles

- Améliorer l'accord sur le seuil d'acceptation : formulation, ou seuil réglable sur P(accepter) mesuré sur un jeu
  de scénarios distinct pour éviter le surapprentissage. Valider sur Windows + NVIDIA et avec le modèle 4B. Supprimer
  ensuite la logique de référence si les résultats le permettent.
- Déplacements et exploration (interfaces des rôles), puis décision collective des essaims (quorum → `ColonyDecision`).
- Reproduction (`lay_eggs`, `manage_reproduction_cycle`).
- Sauvegarde et chargement d'un monde ; authentification si le tableau de bord doit être exposé.
