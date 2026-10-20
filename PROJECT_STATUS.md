# PROJECT_STATUS

_Dernière mise à jour : 2026-10-20_

Référence de reprise entre sessions. Ne décrit que ce qui existe réellement dans le dépôt.
Spécifications d'origine : [prompt1.txt](prompt1.txt), [github_versioning.txt](github_versioning.txt).

## Architecture actuelle

```
Python (backend/bzz)                         Godot 4.7 headless (godot/)
 stdin JSON ─► __main__.py                     main.tscn : Node2D "World" vide
              └► engine.GodotEngine ──TCP──►   main.gd   : serveur TCP 127.0.0.1
                   commands.validate()          ◄── réponses JSON
```

- **godot/** — projet Godot 4.7. Scène unique `main.tscn` (Node2D vide) avec `main.gd`, qui ouvre un
  `TCPServer` sur `127.0.0.1:<port>` (`-- --port=N`, défaut 9876) et traite les commandes dans `_process`.
  `run/max_fps=60` pour ne pas saturer un CPU en headless.
- **backend/bzz/engine.py** — `GodotEngine` : lance `godot --headless --path godot -- --port=<port libre>`,
  se connecte, envoie les commandes (`send`), `stop()` (commande `quit`, puis kill après 5 s), `restart()`,
  utilisable en `with`. Binaire Godot : `$GODOT_BIN` ou `godot` sur le PATH.
- **backend/bzz/commands.py** — liste blanche des commandes et de leurs arguments, validée avant envoi.
- **backend/bzz/__main__.py** — point d'entrée des données : lit une commande JSON par ligne sur stdin,
  la transmet, imprime le résultat. `restart` est géré côté Python.

### Protocole (JSON, une ligne par message)

- Requête : `{"id": 1, "cmd": "ping", "args": {}}`
- Réponse : `{"id": 1, "ok": true, "result": ...}` ou `{"id": 1, "ok": false, "error": "..."}`

## Fonctionnalités implémentées

| Commande    | Effet                                                           |
|-------------|-----------------------------------------------------------------|
| `ping`      | renvoie `"pong"`                                                |
| `get_state` | `physics_frames`, `process_frames`, `node_count` (0 : monde vide) |
| `quit`      | Godot répond `"bye"` puis s'arrête                              |
| `restart`   | (CLI Python uniquement) arrête et relance Godot                 |

## Utilisation

```sh
cd backend
python3 -m bzz                                   # puis taper : {"cmd": "get_state"}
python3 -m unittest discover tests -v            # tests d'intégration (Godot réel requis)
```

## Décisions techniques

- **TCP local + JSON lignes** : standard des deux côtés (`TCPServer` Godot, `socket` Python), pas de dépendance.
- **Port libre choisi par Python** et passé en argument : plusieurs instances possibles, pas de conflit fixe.
- **Validation double** : liste blanche Python avant envoi, Godot rejette aussi les commandes inconnues.
- **Aucune dépendance Python externe** (stdlib uniquement, Python ≥ 3.10).
- La simulation tourne en continu (pas de pas-à-pas piloté) : Godot garde son cycle natif.

## Problèmes connus / limites

- Petite fenêtre de course entre le choix du port libre et l'écoute par Godot (rare).
- Si `main.gd` a une erreur de parse, Godot ne quitte pas : `start()` échoue après le timeout (10 s).
- `send()` est synchrone et un seul client à la fois côté Python (Godot accepte plusieurs connexions).
- `.godot/` (cache d'import) n'est pas versionné ; il est régénéré au premier lancement.

## Tâches en cours

- Aucune.

## Prochaines étapes possibles

- Commandes de création/suppression d'objets dans le monde (`spawn`, `remove`) et `get_state` détaillé.
- Pas de simulation piloté par Python (pause / `step N`) si un déterminisme est requis.
- Source de données entrantes réelle (HTTP, file, fichier) à la place de stdin.
