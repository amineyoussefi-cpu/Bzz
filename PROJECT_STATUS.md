# PROJECT_STATUS

_Dernière mise à jour : 2026-10-20_

Référence de reprise entre sessions. Ne décrit que ce qui existe réellement dans le dépôt.
Spécifications d'origine : [prompts/prompt1.txt](prompts/prompt1.txt),
[prompts/github_versioning.txt](prompts/github_versioning.txt), [prompts/portability.txt](prompts/portability.txt).

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

## Problèmes connus / limites

- Mode local : petite fenêtre de course entre le choix du port libre et l'écoute par Godot (rare).
- Si `main.gd` a une erreur de parse, Godot ne quitte pas : `start()` échoue après le timeout (10 s).
- `send()` est synchrone et un seul client à la fois côté Python (Godot accepte plusieurs connexions).
- Le port Godot n'est pas publié sur l'hôte dans `compose.yaml` (accès réservé au réseau Compose).
- Les tests supposent le mode local (ils vérifient le PID du sous-processus) : lancer avec `GODOT_HOST=` vide.
- `.godot/` (cache d'import) n'est pas versionné ; il est régénéré au premier lancement (pré-généré dans l'image).

## Tâches en cours

- Aucune.

## Prochaines étapes possibles

- Commandes de création/suppression d'objets dans le monde (`spawn`, `remove`) et `get_state` détaillé.
- Pas-à-pas de la simulation piloté par Python (pause / `step N`) si un déterminisme est requis.
- Source de données entrantes réelle (HTTP, file de messages, fichier) à la place de stdin, en nouveau service Compose.
