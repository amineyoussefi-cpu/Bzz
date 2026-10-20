# PROJECT_STATUS

_Dernière mise à jour : 2026-10-20 (prompt 4 : tableau de bord)_

Référence de reprise entre sessions. Ne décrit que ce qui existe réellement dans le dépôt.
Spécifications d'origine : [prompts/prompt1.txt](prompts/prompt1.txt),
[prompts/github_versioning.txt](prompts/github_versioning.txt), [prompts/portability.txt](prompts/portability.txt),
[prompts/prompt2.txt](prompts/prompt2.txt), [prompts/prompt3.txt](prompts/prompt3.txt),
[prompts/prompt4.txt](prompts/prompt4.txt).

## Architecture actuelle

```
Tableau de bord (navigateur) ──HTTP + WebSocket──► Backend Python ──TCP JSON──► Godot 4.7 headless
  backend/bzz/static/index.html                    bzz/server.py (FastAPI)       main.gd (TCP) → WorldApi
                                                   bzz/engine.py (verrou)        entités = enfants du nœud World
                     stdin JSON ─► bzz/__main__.py ┘ bzz/commands.py (validation)
```

**Évolution de décision (prompt 4).** Le prompt 1 excluait tout frontend. Un tableau de bord web est désormais
ajouté, **uniquement comme client du backend Python** :

- Godot reste le moteur et le propriétaire de l'état du monde, toujours sans fenêtre.
- Python reste l'unique point d'entrée vers Godot : il valide, transmet et calcule les KPI.
- Le navigateur n'affiche que ce que le backend lui fournit.
- Le point d'entrée stdin fonctionne toujours.

Deux modes, choisis par la variable `GODOT_HOST` :

- **local** (`GODOT_HOST` vide) : Python lance lui-même Godot en sous-processus sur un port libre. Si le cache
  `.godot/` manque (dépôt fraîchement cloné), il lance d'abord `godot --import`.
- **distant** (`GODOT_HOST=godot`) : Python se connecte à un Godot déjà lancé. C'est le mode de Docker Compose.

Fichiers :

- **godot/main.gd** — nœud World : serveur TCP (`--host`, `--port`, `--world-width`, `--world-height`), `ping`/`quit`,
  délègue tout le reste à `WorldApi`. `run/max_fps=60`.
- **godot/api/world_api.gd** — `WorldApi` : catalogue, ajout/consultation/retrait des entités (identifiants `hab-N` / `bee-N`
  jamais réutilisés), horloge (`tick`, pause, vitesse), journal d'événements (1000 derniers, curseur `seq`) et validation
  côté Godot. **N'appelle jamais** `evaluate_habitat`, `choose_habitat`, `settle` ni les composants de rôles.
- **godot/entities/** — modèle :
  - `Habitat` (Node2D, 6 types) et `HabitatCatalog` (caractéristiques par défaut par type, bornes, noms lisibles) ;
  - `Bee` (Node2D : évaluation, choix, installation — logique conservée telle quelle, non appelée) ;
  - `BeePersonality` (4 traits, `PRESETS`, `validate_traits`), `Preference`, `BeeSpecies` (5 espèces + noms lisibles) ;
  - `DecisionEvent` (format des futurs événements de décision, jamais émis).
  Référence : [docs/reference_abeilles.md](docs/reference_abeilles.md) (+ PDF).
- **godot/entities/roles/** — `BeeRole` (`scout`/`follower`/`queen`), `BeeBehavior` (abstraite), `ScoutBehavior`,
  `FollowerBehavior`, `QueenBehavior`, `DanceSignal`, `ColonyDecision` : interfaces définies, jamais exécutées.
  Voir [docs/roles_comportements.md](docs/roles_comportements.md) (+ PDF).
- **backend/bzz/engine.py** — `GodotEngine` : démarrage (local/distant), récupération du catalogue au démarrage,
  `send` protégé par un **verrou** (une connexion TCP partagée par tous les appelants), `stop`, `restart`.
  Erreurs : `ValueError` (refus Python), `CommandRejected` (refus Godot), `GodotError` (connexion).
- **backend/bzz/commands.py** — liste blanche (commandes, arguments, types) + validation des valeurs à partir du
  catalogue généré par Godot (aucune liste recopiée). À garder synchronisée avec `WorldApi.ARGS`.
- **backend/bzz/server.py** — API HTTP + WebSocket `/ws` (FastAPI), relevé des événements toutes les 250 ms,
  sert la page du tableau de bord. `python -m bzz.server`.
- **backend/bzz/kpi.py** — calcul des KPI à partir de l'état, des entités et des événements.
- **backend/bzz/static/index.html** — tableau de bord (HTML/JS sans framework, sans dépendance externe).
- **backend/bzz/__main__.py** — entrée stdin (une commande JSON par ligne), inchangée.
- **godot/tests/test_entities.gd** — tests GDScript (modèle, rôles, `WorldApi`), lancés par `backend/tests/test_entities.py`.
- **backend/tests/** — `test_engine` (cycle de vie), `test_protocol` (chaque commande), `test_server` (API HTTP + WebSocket + KPI).
- **docs/api.md** — **référence de toutes les commandes et routes**, avec exemples, format des événements et des
  décisions, choix du relevé périodique et du verrou, KPI.
- **docs/** — documents de référence (Markdown + PDF, SVG dans `docs/img/`) ; PDF régénérés par `python docs/build_pdf.py docs/*.md`.
- **Dockerfile** — cibles `godot` (serveur headless) et `backend` (Python 3.12 + dépendances + binaire Godot ; CMD = serveur web).
- **compose.yaml** — `godot` (port interne uniquement) + `backend` (tableau de bord publié sur `127.0.0.1:${DASHBOARD_PORT:-8000}`).
- **.env.example** — `GODOT_*`, `WORLD_WIDTH`/`WORLD_HEIGHT`, `DASHBOARD_PORT`, `BZZ_HTTP_HOST` ; sans secrets.
- **backend/requirements.txt** — `fastapi`, `uvicorn`, `websockets` (serveur), `httpx` (tests) ; le moteur et
  l'entrée stdin n'utilisent que la bibliothèque standard.

## Fonctionnalités implémentées

Commandes du protocole (détail et exemples : [docs/api.md](docs/api.md)) :

| Commande | Effet |
|---|---|
| `ping`, `quit` | test de vie, arrêt de Godot |
| `get_state` | tick, pause, vitesse, taille du monde, effectifs, dernier `seq`, `decision_mechanism: null` |
| `get_catalog` | types d'habitats et leurs valeurs par défaut, caractéristiques et bornes, espèces, rôles, traits, préréglages, monde, vitesses |
| `add_habitat` | type + position + surcharge facultative des caractéristiques |
| `add_bee` | espèce + position + personnalité (préréglage / traits / aléatoire avec graine) + nom + rôle |
| `list_entities`, `get_entity`, `remove_entity`, `clear_world` | consultation et retrait (un habitat retiré libère ses occupants) |
| `pause`, `resume`, `set_speed` | horloge de simulation (le monde démarre en pause ; vitesse de 0,25 à 8) |
| `get_events` | événements depuis un curseur (`entity_added`, `entity_removed`, `world_cleared`, `paused`, `resumed`, `speed_changed`) |
| `restart` | (stdin uniquement) relance Godot |

Tableau de bord (<http://localhost:8000>) :

- **Formulaires** : ajout d'habitat (type, position par clic dans la vue, surcharge des caractéristiques) et d'abeille
  (espèce, rôle, nom, position, personnalité par préréglage, curseurs ou aléatoire avec graine).
- **Vue du monde** : 2D, couleur par type d'habitat et par espèce.
- **Entités** : liste avec détail et retrait, plus les boutons pause/reprise, vitesse et vider le monde. Les erreurs du
  backend s'affichent dans une notification.
- **KPI temps réel** : effectifs par type et par espèce, répartition des traits, abeilles installées ou sans habitat,
  occupation des habitats, temps simulé, état de la simulation, fil des événements.
- **Espace décisions** : fil, nombre de choix et de refus, score moyen, répartition par espèce et par trait. Il est
  affiché vide, avec la mention qu'aucun mécanisme n'est actif.

**Aucune décision n'est prise** : les abeilles ajoutées restent sans habitat et à leur position, et aucun événement
`decision` n'est émis. Un test le vérifie après plus de 200 ticks de simulation à vitesse ×8.

Modèle (inchangé) :

- Évaluation et choix d'habitat dans `Bee` : `score_breakdown`, `evaluate_habitat`, `choose_habitat`, `settle`,
  `leave_home`. Cette logique est conservée comme référence pour le futur mécanisme, puis sera retirée.
- Rôles : opérations sur données uniquement. Les interfaces vides restent `explore_habitats`, `return_to_colony`,
  `evaluate_signal`, `decide_to_follow`, `visit_habitat`, `move_to_habitat`, `lay_eggs`, `manage_reproduction_cycle`.

## Utilisation

Avec Docker :

```sh
cp .env.example .env                       # optionnel
docker compose up -d                       # tableau de bord : http://localhost:8000
docker compose run --rm backend python -m bzz          # entrée stdin
docker compose run --rm -e GODOT_HOST= backend python -m unittest discover tests   # tests
docker compose down
```

Sans Docker (Godot ≥ 4.5 sur le PATH ou `GODOT_BIN`, Python ≥ 3.10) :

```sh
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/python -m bzz.server          # tableau de bord : http://localhost:8000
../.venv/bin/python -m bzz                 # entrée stdin (aucune dépendance requise)
../.venv/bin/python -m unittest discover tests     # 23 tests ; sans les dépendances web, 4 sont ignorés
```

## Décisions techniques

- **TCP + JSON lignes** entre Python et Godot, en requête/réponse uniquement.
- **Événements relevés par Python** (`get_events` avec curseur, toutes les 250 ms), plutôt qu'envoyés spontanément
  par Godot : le protocole reste simple, aucun message spontané ne se mêle aux réponses, et aucun événement n'est
  perdu (`lost` signale un débordement du journal de 1000 événements). Justification complète : docs/api.md §5.
- **Une connexion TCP + un verrou** dans `GodotEngine.send` : les requêtes HTTP concurrentes et le relevé passent
  l'un après l'autre sans mélanger leurs réponses.
- **Événements horodatés en ticks de simulation** (compteur propre à `WorldApi`, arrêté en pause). La vitesse change
  `Engine.physics_ticks_per_second` (60 × vitesse).
- **Noms lisibles générés depuis les énumérations** (`Habitat.Type`, `BeeSpecies.Id`, `BeeRole.Id`) ; le catalogue
  est produit par Godot et sert à Python pour valider, donc aucune liste n'est dupliquée à la main.
- **Validation double** (Python puis Godot), refus sans correction silencieuse, tout est vérifié avant la création.
- **Taille du monde** : une seule valeur par défaut (`WorldApi.DEFAULT_SIZE`, 1000 × 700), modifiable par
  `WORLD_WIDTH`/`WORLD_HEIGHT`, transmises à Godot en ligne de commande seulement si elles sont définies.
- **Graine** : toujours enregistrée (tirée au hasard si absente), donc toute abeille aléatoire est reproductible.
- **KPI calculés par Python** (`kpi.py`) ; le navigateur ne calcule rien. Les KPI de décision lisent déjà le format
  `DecisionEvent`, indépendant de la source de la décision.
- **Tableau de bord servi par le backend** (même origine, pas de service Compose séparé) : HTML/JS sans framework ni build.
- Hérité des étapes précédentes : configuration par variables d'environnement, Dockerfile multi-cible,
  entités en GDScript, rôles par composition, `@abstract` (Godot ≥ 4.5).

## Problèmes connus / limites

- **Pas d'authentification** : le tableau de bord est prévu pour un usage local. Compose le publie sur `127.0.0.1`
  seulement ; ne pas l'exposer sur un réseau sans ajouter une authentification.
- Pas de sauvegarde ni de chargement d'un monde (hors périmètre). Redémarrer Godot vide le monde.
- Une capture WebSocket peut montrer une entité un relevé (≤ 250 ms) avant l'événement correspondant :
  entités et événements viennent de requêtes distinctes.
- Une seule connexion TCP sérialise toutes les commandes : cela suffit pour un usage local, mais ce serait un goulot
  d'étranglement avec beaucoup de clients.
- Le journal d'événements de Godot est limité à 1000 événements, et le backend en garde 200 pour les nouveaux clients.
- Mode local : petite fenêtre de course entre le choix du port libre et l'écoute par Godot (rare).
- Si un script Godot a une erreur de parse, Godot ne quitte pas : `start()` échoue après le timeout (10 s).
- Les tests supposent le mode local (`GODOT_HOST=` vide).
- `floral_abundance` et `predator_risk` sont fixés à la main (valeurs par défaut ou surcharge) ; rien ne les calcule depuis le monde.
- `.godot/` (cache d'import) n'est pas versionné ; il est régénéré automatiquement (moteur en mode local, images Docker).

## Tâches en cours

- Aucune.

## Prochaines étapes possibles

- **Prompt 5** : mécanisme de décision des abeilles. Il émettra des événements `decision` (format `DecisionEvent`,
  docs/api.md §3), renseignera `decision_mechanism` dans `get_state`, puis remplacera la logique de choix de `Bee`.
- Décision collective des essaims d'abeilles mellifères (quorum) produisant une `ColonyDecision` ; implémentation
  des interfaces des rôles (déplacements, danse).
- Reproduction derrière `lay_eggs` / `manage_reproduction_cycle`.
- Sauvegarde et chargement d'un monde ; authentification si le tableau de bord doit être exposé.
