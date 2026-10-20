# PROJECT_STATUS

_Dernière mise à jour : 2026-10-20_

Référence de reprise entre sessions. Ne décrit que ce qui existe réellement dans le dépôt.
Spécifications d'origine : [prompts/prompt1.txt](prompts/prompt1.txt),
[prompts/github_versioning.txt](prompts/github_versioning.txt), [prompts/portability.txt](prompts/portability.txt),
[prompts/prompt2.txt](prompts/prompt2.txt).

## Architecture actuelle

```
Python (backend/bzz)                         Godot 4.7 headless (godot/)
 stdin JSON ─► __main__.py                     main.tscn : Node2D "World" vide
              └► engine.GodotEngine ──TCP──►   main.gd   : serveur TCP <host>:<port>
                   commands.validate()          ◄── réponses JSON
```

Deux modes, choisis par la variable `GODOT_HOST` :

- **local** (`GODOT_HOST` vide) : Python lance lui-même Godot en sous-processus sur un port libre.
- **distant** (`GODOT_HOST=godot`) : Python se connecte à un Godot déjà lancé (autre conteneur / serveur).
  C'est le mode utilisé par Docker Compose.

Fichiers :

- **godot/** — projet Godot 4.7. Scène unique `main.tscn` (Node2D vide) avec `main.gd`, qui ouvre un
  `TCPServer` (`-- --host=H --port=N`, défaut `127.0.0.1:9876`) et traite les commandes dans `_process`.
  `run/max_fps=60` pour ne pas saturer un CPU en headless.
- **godot/entities/** — modèle abeilles/habitats, **conçu mais non instancié dans le monde** (le monde reste vide,
  `node_count` = 0) : `Habitat` (Node2D, 6 types, caractéristiques, occupants), `Bee` (Node2D : évaluation,
  choix, installation), `BeePersonality` (Resource, 4 traits), `Preference` (Resource, un critère pondéré),
  `BeeSpecies` (catalogue de 5 espèces : types acceptés et préférences par défaut).
  Référence illustrée et sourcée : [docs/reference_abeilles.md](docs/reference_abeilles.md)
  (version PDF : [docs/reference_abeilles.pdf](docs/reference_abeilles.pdf), générée depuis le Markdown, à régénérer s'il change).
- **godot/entities/roles/** — rôles et interfaces de comportement, **définis mais jamais exécutés** :
  `BeeRole` (enum `SCOUT`/`FOLLOWER`/`QUEEN`, indépendant des espèces, `create_behavior`),
  `BeeBehavior` (classe abstraite : `role()`, `actions()`), `ScoutBehavior`, `FollowerBehavior`, `QueenBehavior`,
  `DanceSignal` (données d'une danse), `ColonyDecision` (contrat avec la future décision collective).
  `Bee` porte `role` + `behavior` (`set_role`, `FOLLOWER` par défaut). Détail des méthodes et de ce qui reste à faire :
  [docs/roles_comportements.md](docs/roles_comportements.md) (+ PDF).
- **godot/tests/test_entities.gd** — tests unitaires du modèle et des rôles (lancés par `backend/tests/test_entities.py`).
- **docs/** — documents de référence (Markdown + PDF, illustrations SVG dans `docs/img/`).
  PDF régénérés par `python docs/build_pdf.py docs/*.md` (dépendances : `docs/requirements.txt` + Chrome).
- **backend/bzz/engine.py** — `GodotEngine` : démarrage/connexion, `send`, `stop`, `restart`, utilisable en `with`.
  Toute la configuration vient des variables d'environnement (liste en tête du fichier et dans `.env.example`).
- **backend/bzz/commands.py** — liste blanche des commandes et de leurs arguments, validée avant envoi.
- **backend/bzz/__main__.py** — point d'entrée des données : lit une commande JSON par ligne sur stdin,
  la transmet, imprime le résultat. `restart` est géré côté Python.
- **Dockerfile** — multi-cible : `godot` (serveur Godot headless, binaire Linux officiel téléchargé, amd64/arm64)
  et `backend` (Python 3.12 + binaire Godot, pour le mode local et les tests).
- **compose.yaml** — services `godot` et `backend` ; `restart: unless-stopped` sur `godot`.
- **.env.example** — variables configurables, sans secrets. **backend/requirements.txt** — vide (stdlib seulement).

### Protocole (JSON, une ligne par message)

- Requête : `{"id": 1, "cmd": "ping", "args": {}}`
- Réponse : `{"id": 1, "ok": true, "result": ...}` ou `{"id": 1, "ok": false, "error": "..."}`

## Fonctionnalités implémentées

- Modèle d'entités (non relié au protocole ni au monde) : une abeille évalue un habitat
  (`Bee.evaluate_habitat` / `score_breakdown`), choisit le meilleur au-dessus de son seuil (`choose_habitat`),
  s'y installe ou le quitte (`settle`, `leave_home`). Formules dans docs/reference_abeilles.md §3–5.
- Rôles : seules les opérations sur des données sont écrites — éclaireuse : `evaluate_habitat` (délégué à `Bee`),
  `remember_habitat`, `perform_dance` (construit un `DanceSignal`) ; suiveuse : `receive_dance`, `evaluate_habitat` ;
  reine : `receive_colony_decision`, `follow_colony_decision` (fixe `target_habitat`, sans bouger).
  **Interfaces vides** (aucun effet) : `explore_habitats`, `return_to_colony`, `evaluate_signal`, `decide_to_follow`,
  `visit_habitat`, `move_to_habitat`, `lay_eggs`, `manage_reproduction_cycle`.

Commandes du protocole :

| Commande    | Effet                                                           |
|-------------|-----------------------------------------------------------------|
| `ping`      | renvoie `"pong"`                                                |
| `get_state` | `physics_frames`, `process_frames`, `node_count` (0 : monde vide) |
| `quit`      | Godot répond `"bye"` puis s'arrête                              |
| `restart`   | (CLI Python) local : relance le sous-processus ; distant : `quit` puis reconnexion (Compose relance Godot) |

## Utilisation

Avec Docker (aucune installation à part Docker) :

```sh
cp .env.example .env                       # optionnel
docker compose up -d godot
docker compose run --rm backend            # puis taper : {"cmd": "get_state"}
docker compose run --rm -e GODOT_HOST= backend python -m unittest discover tests   # tests
docker compose down
```

Sans Docker (Godot 4.7 sur le PATH ou `GODOT_BIN`, Python ≥ 3.10) :

```sh
cd backend
python3 -m bzz
python3 -m unittest discover tests -v
```

## Décisions techniques

- **TCP + JSON lignes** : standard des deux côtés (`TCPServer` Godot, `socket` Python), pas de dépendance ;
  fonctionne aussi bien en local qu'entre conteneurs.
- **Mode local : port libre choisi par Python** et passé en argument : plusieurs instances possibles.
- **Validation double** : liste blanche Python avant envoi, Godot rejette aussi les commandes inconnues.
- **Configuration uniquement par variables d'environnement**, aucun chemin absolu dans le code
  (chemin du projet Godot résolu relativement au dépôt).
- **Une seule image Dockerfile multi-cible** plutôt que deux Dockerfiles : le binaire Godot n'est téléchargé qu'une fois.
- En mode distant, la fin du backend ne fait que se déconnecter (Godot reste vivant) ; seul `restart`/`quit` l'arrête.
- La simulation tourne en continu (pas de pas-à-pas piloté) : Godot garde son cycle natif.
- **Entités en GDScript dans Godot**, pas en Python : le moteur reste propriétaire de l'état du monde ;
  Python les pilotera plus tard via de nouvelles commandes.
- `Bee`/`Habitat` héritent de `Node2D` (position dans le monde dès qu'ils y seront ajoutés) ;
  personnalité et préférences sont des `Resource` (sauvegardables, éditables, copiées par individu).
- Évaluation = moyenne pondérée de critères « triangulaires » (idéal ± tolérance), puis modulée par la personnalité.
  Valeurs idéales issues des sources quand elles existent ; tolérances et poids = réglages de jeu.
- Choix d'habitat **individuel** ; la décision collective des essaims d'abeilles mellifères n'est pas modélisée.
- **Rôles par composition** : `bee.behavior` est un composant remplaçable (`set_role`), pas une sous-classe de `Bee` ;
  les comportements délèguent l'évaluation à `Bee` (aucune duplication). La reine n'a pas de méthode de choix d'habitat.
- `BeeBehavior` utilise `@abstract` (GDScript ≥ 4.5) : le projet requiert Godot 4.5+ (4.7 utilisé).

## Problèmes connus / limites

- Mode local : petite fenêtre de course entre le choix du port libre et l'écoute par Godot (rare).
- Si `main.gd` a une erreur de parse, Godot ne quitte pas : `start()` échoue après le timeout (10 s).
- `send()` est synchrone et un seul client à la fois côté Python (Godot accepte plusieurs connexions).
- Le port Godot n'est pas publié sur l'hôte dans `compose.yaml` (accès réservé au réseau Compose).
- Les tests supposent le mode local (ils vérifient le PID du sous-processus) : lancer avec `GODOT_HOST=` vide.
- Les tests GDScript nécessitent un `godot --import` préalable (fait automatiquement par le test Python),
  sinon les `class_name` ne sont pas reconnus en mode `--script`.
- `floral_abundance` et `predator_risk` sont des valeurs fixées à la main ; rien ne les calcule encore depuis le monde.
- `.godot/` (cache d'import) n'est pas versionné ; il est régénéré au premier lancement (pré-généré dans l'image).

## Tâches en cours

- Aucune.

## Prochaines étapes possibles

- Instancier abeilles et habitats dans le monde : commandes `spawn_habitat`, `spawn_bee`, `remove`
  et `get_state` détaillé (liste des entités), puis comportements (recherche, déplacement, installation).
- Décision collective pour les essaims d'abeilles mellifères (force de danse, attrition, signal stop, quorum)
  produisant une `ColonyDecision` ; puis implémenter les interfaces vides des rôles (voir docs/roles_comportements.md §7).
- Mécanisme de reproduction (ponte, développement, naissance) derrière `lay_eggs` / `manage_reproduction_cycle`.
- Pas-à-pas de la simulation piloté par Python (pause / `step N`) si un déterminisme est requis.
- Source de données entrantes réelle (HTTP, file de messages, fichier) à la place de stdin, en nouveau service Compose.
