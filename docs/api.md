# API Bzz : protocole Godot et API du tableau de bord

```
Tableau de bord (navigateur) ──HTTP + WebSocket──► Backend Python ──TCP JSON──► Godot headless
                             ◄── snapshots (état, KPI, événements) ──       ◄── résultats, événements ──
```

- **Godot** possède l'état du monde et l'horloge de simulation ([`godot/api/world_api.gd`](../godot/api/world_api.gd)).
- **Python** est l'unique point d'entrée vers Godot : il valide, transmet, relève les événements et calcule les KPI
  ([`backend/bzz/`](../backend/bzz/)).
- **Le tableau de bord** ([`backend/bzz/static/index.html`](../backend/bzz/static/index.html)) n'affiche que ce que
  le backend lui fournit.
- **Les décisions** viennent du service OpenJev local : voir [decision_service.md](decision_service.md).

Lancer : `cd backend && python -m bzz.server` puis ouvrir <http://localhost:8000>, ou `docker compose up`.

---

## 1. Conventions

- **Noms lisibles** partout : `"tree_cavity"`, `"honey_bee"`, `"scout"`, jamais de numéro d'énumération.
  Ils sont générés depuis les énumérations GDScript (`Habitat.Type`, `BeeSpecies.Id`, `BeeRole.Id`).
- **Identifiants** : `hab-N`, `bee-N` ou `swarm-N`, uniques et stables, jamais réutilisés pendant la vie du processus Godot
  (même après `clear_world`).
- **Positions** en unités du monde (1 unité = 1 m) : `0 ≤ x ≤ largeur`, `0 ≤ y ≤ hauteur`. Taille par défaut
  1000 × 700 (`WorldApi.DEFAULT_SIZE`), modifiable par `WORLD_WIDTH` / `WORLD_HEIGHT`.
- **Validation double** : Python (`commands.py`, à partir du catalogue que Godot génère) puis Godot (`world_api.gd`).
  Une valeur hors bornes est **refusée, jamais corrigée** ; le message d'erreur liste les valeurs acceptées.
  Tout est vérifié avant la création : une commande refusée ne laisse aucune entité partielle.
- **Temps** : les événements sont horodatés en **ticks de simulation**. Le compteur n'avance que lorsque la simulation
  tourne (60 ticks par seconde réelle à ×1). Une **journée simulée** dure `day_ticks` ticks (`DAY_TICKS`, 3600 par
  défaut, soit une minute réelle à ×1). La pause arrête le temps, les vols et les délais ; la vitesse les accélère
  tous de la même façon.
- **Paramètres de simulation** (valeurs par défaut uniquement dans `WorldApi.DEFAULT_CONFIG`, modifiables par
  variables d'environnement) : `DAY_TICKS`, `FLIGHT_SPEED_FACTOR` (unités par tick pour 1 m/s, 0,05), `SWARM_SPEED_MPS`
  (2,7), `SWARM_CLUSTER_DAYS` (3). Le catalogue les renvoie.

---

## 2. Protocole TCP Python ↔ Godot

Une requête et une réponse par ligne, en JSON :

```json
→ {"id": 7, "cmd": "add_habitat", "args": {"type": "tree_cavity", "x": 200, "y": 150}}
← {"id": 7, "ok": true, "result": {...}}
← {"id": 7, "ok": false, "error": "unknown habitat type nest; accepted: tree_cavity, hive_box, ..."}
```

Ces commandes sont accessibles en Python (`GodotEngine.send(cmd, **args)`) et par l'entrée standard
(`python -m bzz`, une commande JSON `{"cmd": ..., "args": {...}}` par ligne).

| Commande | Arguments |
|---|---|
| `ping`, `quit` | — |
| `get_state` | — |
| `get_catalog` | — |
| `add_habitat` | `type`, `x`, `y`, `features?` |
| `add_bee` | `species`, `x`, `y`, `personality?`, `name?`, `role?` |
| `add_swarm` | `x`, `y`, `population`, `personality?`, `name?` |
| `list_entities` | — |
| `get_entity` | `id` |
| `remove_entity` | `id` |
| `clear_world` | — |
| `pause`, `resume` | — |
| `set_speed` | `speed` (0.25 à 8) |
| `get_events` | `since?` (curseur, défaut 0) |
| `get_decision_situation` | `bee_id` (abeille ou essaim) |
| `apply_decision` | `bee_id` (abeille ou essaim), `habitat_id` (ou `null`), `decision?` |
| `reference_decision` | `bee_id` (abeille ou essaim), `habitat_ids` |

### `get_state`

```json
← {"tick": 1435, "paused": false, "speed": 1.0, "ticks_per_second": 60,
   "world": {"width": 1000, "height": 700}, "habitats": 5, "bees": 5, "swarms": 1, "node_count": 11,
   "day_ticks": 3600.0, "last_event_seq": 12, "physics_frames": 2210, "process_frames": 2205}
```

### `get_catalog`

Généré à partir des classes, jamais recopié à la main :

```json
← {"habitat_types": [{"name": "tree_cavity", "defaults": {"cavity_volume_l": 40.0, "entrance_diameter_mm": 40.0,
      "entrance_height_m": 5.0, "sun_exposure": 0.4, "humidity": 0.4, "floral_abundance": 0.6,
      "predator_risk": 0.2, "previously_occupied": false, "capacity": 1}}, ...],
   "features": {"humidity": {"type": "float", "min": 0.0, "max": 1.0}, "capacity": {"type": "int", "min": 1, "max": 1000},
                "previously_occupied": {"type": "bool"}, ...},
   "species": [{"name": "honey_bee", "accepted_habitat_types": ["tree_cavity", "hive_box"],
                "preferences": [{"criterion": "cavity_volume_l", "ideal": 40.0, "tolerance": 35.0, "weight": 2.0}, ...]}, ...],
   "roles": ["scout", "follower", "queen"], "default_role": "follower",
   "traits": [{"name": "pickiness", "min": 0.0, "max": 1.0}, ...],
   "presets": {"prudente": {"pickiness": 0.8, "boldness": 0.1, "sociability": 0.4, "curiosity": 0.2}, ...},
   "world": {"width": 1000, "height": 700}, "speed": {"min": 0.25, "max": 8.0, "default": 1.0},
   "ticks_per_second": 60, "max_name_length": 40}
```

À partir de cette étape, le catalogue contient aussi :

```json
   "species": [{"name": "honey_bee", ..., "flight_speed_mps": 7.5, "flight_speed_sourced": true, "lives_in_swarms": true}, ...],
   "time": {"day_ticks": 3600.0, "flight_speed_factor": 0.05},
   "swarm": {"species": "honey_bee", "population": {"min": 1000, "max": 50000, "default": 10000},
             "speed_mps": 2.7, "cluster_days": 3.0}
```

**Caractéristiques par défaut des habitats** (`HabitatCatalog`, d'après [la référence](reference_abeilles.md) ;
l'ensoleillement, l'humidité, les fleurs et le risque sont des réglages de jeu) :

| Type | Volume (L) | Entrée (mm) | Hauteur (m) | Soleil | Humidité | Risque | Ancien nid | Capacité |
|---|---|---|---|---|---|---|---|---|
| `tree_cavity` | 40 | 40 | 5 | 0,4 | 0,4 | 0,2 | non | 1 |
| `hive_box` | 40 | 40 | 1 | 0,5 | 0,3 | 0,1 | non | 1 |
| `rodent_burrow` | 2 | 30 | 0 | 0,1 | 0,5 | 0,3 | oui | 1 |
| `bare_soil` | 0 | 0 | 0 | 0,9 | 0,2 | 0,3 | non | 50 |
| `hollow_stem` | 0 | 7 | 1 | 0,8 | 0,3 | 0,2 | non | 20 |
| `dead_wood` | 0 | 0 | 1,5 | 0,7 | 0,2 | 0,2 | non | 5 |

`floral_abundance` vaut 0,6 par défaut pour tous les types.

**Préréglages de personnalité** (`BeePersonality.PRESETS`) :

| Préréglage | Exigence | Audace | Sociabilité | Curiosité |
|---|---|---|---|---|
| `prudente` | 0,8 | 0,1 | 0,4 | 0,2 |
| `audacieuse` | 0,3 | 0,9 | 0,5 | 0,6 |
| `sociable` | 0,5 | 0,5 | 0,9 | 0,4 |
| `curieuse` | 0,4 | 0,6 | 0,5 | 0,9 |
| `équilibrée` | 0,5 | 0,5 | 0,5 | 0,5 |

### `add_habitat`

```json
→ {"type": "bare_soil", "x": 700, "y": 500, "features": {"capacity": 12, "humidity": 0.1}}
← {"id": "hab-3", "kind": "habitat", "type": "bare_soil", "x": 700.0, "y": 500.0, "capacity": 12, "occupants": 0}
```

`features` surcharge seulement les clés données ; le reste prend les valeurs par défaut du type.
Refus : type inconnu, position hors du monde, clé inconnue, mauvais type (`capacity` entier, `previously_occupied` booléen),
valeur hors bornes.

### `add_bee`

```json
→ {"species": "honey_bee", "x": 300, "y": 200, "name": "Ada", "role": "scout", "personality": {"preset": "curieuse"}}
← {"id": "bee-2", "kind": "bee", "species": "honey_bee", "name": "Ada", "role": "scout", "x": 300.0, "y": 200.0,
   "personality": {"pickiness": 0.4, "boldness": 0.6, "sociability": 0.5, "curiosity": 0.9}, "home_id": null}
```

La personnalité s'écrit sous l'une de ces trois formes, chacune avec une graine `seed` facultative (entier de 1 à 2³¹−1) :

| Forme | Exemple |
|---|---|
| préréglage | `{"preset": "prudente"}` ou `{"preset": "prudente", "seed": 7}` |
| traits explicites (les 4, entre 0 et 1) | `{"traits": {"pickiness": 0.2, "boldness": 0.4, "sociability": 0.6, "curiosity": 0.8}}` |
| aléatoire | `{"random": true, "seed": 1234}` |

- Sans `personality`, la personnalité est aléatoire.
- La graine initialise le générateur aléatoire de l'abeille : tirage des traits aléatoires et bruit de curiosité de la
  logique de référence. Elle est toujours enregistrée (`get_entity` → `seed`), donc une abeille peut être recréée à
  l'identique : même espèce, même forme et même graine.
- L'abeille reçoit les préférences par défaut de son espèce (`Bee.create`) et le rôle `follower`, sauf si `role` est donné.
- Elle est créée **sans habitat** (`home_id: null`).
- **L'abeille mellifère est refusée** : `"honey_bee lives in swarms: use add_swarm instead of add_bee"`.

### `add_swarm`

Pose un essaim d'abeilles mellifères **en grappe** sur une branche à la position donnée. L'essaim a une reine (une
`Bee` de rôle `queen`), une population d'ouvrières (un nombre) et une personnalité collective (mêmes formes que pour
`add_bee`). Son délai de grappe vaut `swarm.cluster_days`.

```json
→ {"x": 450, "y": 330, "population": 12000, "name": "Essaim A", "personality": {"preset": "audacieuse"}}
← {"id": "swarm-7", "kind": "swarm", "species": "honey_bee", "name": "Essaim A", "population": 12000,
   "state": "cluster", "waiting": false, "days_left": 3.0, "cluster_x": 450.0, "cluster_y": 330.0,
   "x": 450.0, "y": 330.0, "personality": {...}, "home_id": null}
```

Refus : population hors de 1000–50 000, position hors du monde, personnalité ou nom invalides.

### `list_entities`

```json
← [{"id": "hab-1", "kind": "habitat", "type": "tree_cavity", "x": 200.0, "y": 150.0, "capacity": 1, "occupants": 0},
   {"id": "bee-2", "kind": "bee", "species": "mining_bee", "name": "Ada", "role": "scout", "x": 312.4, "y": 207.1,
    "state": "flying", "personality": {...}, "home_id": null,
    "target_id": "hab-3", "target_x": 700.0, "target_y": 520.0, "speed": 0.15, "flight_ticks": 120},
   {"id": "swarm-7", "kind": "swarm", "state": "cluster", "population": 12000, "days_left": 2.4, ...}]
```

**États** (`state`) :

| Entité | États |
|---|---|
| abeille | `searching` (en recherche), `waiting` (en attente : aucun habitat compatible dans le monde), `flying` (en vol), `settled` (installée) |
| essaim | `cluster` (en grappe, délai qui s'écoule ; `waiting: true` si aucune cavité compatible), `flying` (en vol), `settled` (installé), `exposed` (nid à découvert : délai écoulé, échec) |

Une entité en vol a aussi `target_id`, `target_x`, `target_y`, `speed` (unités par tick) et `flight_ticks`.

### `get_entity`

```json
→ {"id": "bee-2"}
← {..., "accepted_habitat_types": ["tree_cavity", "hive_box"], "preferences": [{"criterion": "cavity_volume_l", ...}],
   "seed": 1867123, "personality_source": "preset:curieuse"}
→ {"id": "hab-1"}
← {..., "features": {"cavity_volume_l": 40.0, ...}, "occupant_ids": []}
→ {"id": "swarm-7"}
← {..., "accepted_habitat_types": ["tree_cavity", "hive_box"], "preferences": [...], "seed": 42,
   "queen": {"role": "queen", "target_habitat_id": "hab-1", "decision_support": 12000}}
```

### `remove_entity` et `clear_world`

```json
→ {"id": "hab-1"}
← {"id": "hab-1", "kind": "habitat", "released_bee_ids": []}
→ clear_world
← {"removed": 4}
```

- **Retirer un habitat** libère ses occupants, listés dans `released_bee_ids` : les abeilles reprennent leur
  recherche, les essaims se reposent en grappe sur place.
- **Vols en cours** : les abeilles ou essaims qui volaient vers cet habitat s'arrêtent sur place, avec un événement
  `arrival_failed` (`reason: "removed"`).
- **Retirer un essaim** libère sa place.

### `pause`, `resume`, `set_speed`

```json
→ resume                 ← {"paused": false, "tick": 0}
→ {"speed": 2}           ← {"speed": 2.0}
→ pause                  ← {"paused": true, "tick": 312}
```

- Le monde **démarre en pause**, pour pouvoir le construire avant de lancer la simulation.
- `set_speed` change le nombre de ticks par seconde réelle (60 × vitesse).

### `get_events`

```json
→ {"since": 3}
← {"events": [{"seq": 4, "tick": 22, "type": "entity_removed", "data": {"id": "hab-1", "kind": "habitat", "released_bee_ids": []}},
              {"seq": 5, "tick": 22, "type": "world_cleared", "data": {"removed": 2}}],
   "last_seq": 5, "lost": false}
```

`since` est le dernier `seq` déjà reçu. Godot garde les 1000 derniers événements. Si le curseur est trop ancien,
`lost` passe à `true`.

### `get_decision_situation`

Ce dont un décideur a besoin pour une abeille **ou un essaim** : son profil complet et **tous** les habitats.

- `eligible` signifie que le type est accepté par l'espèce et qu'il reste de la place.
- Pour un essaim, le profil est celui de la reine, plus `population` et `days_left`, et `distance` est mesurée
  depuis la grappe.

```json
→ {"bee_id": "bee-3"}
← {"tick": 240, "paused": false,
   "bee": {"id": "bee-3", "species": "honey_bee", "personality": {...}, "home_id": null, "role": "follower", "x": 330.0, "y": 240.0,
           "accepted_habitat_types": ["tree_cavity", "hive_box"], "preferences": [{"criterion": "cavity_volume_l", "ideal": 40.0, ...}],
           "acceptance_threshold": 0.7},
   "habitats": [{"id": "hab-1", "type": "tree_cavity", "x": 300.0, "y": 200.0, "capacity": 1, "occupants": 0,
                 "features": {...}, "distance": 50.0, "type_accepted": true, "full": false, "eligible": true}, ...]}
```

### `apply_decision`

Godot **valide puis applique** une décision prise ailleurs (par OpenJev). Il vérifie que :

- l'abeille est en recherche (ou l'essaim en grappe), ni en vol, ni installée, ni à découvert ;
- l'habitat existe, son type est accepté et il reste de la place **au moment de la décision**.

**L'abeille s'envole alors vers l'habitat** (`flight_started`) **et ne s'y installe qu'à l'arrivée** (`arrived`).
L'habitat n'est pas réservé : s'il est plein à l'arrivée, c'est un échec (`arrival_failed`) et l'abeille reprend sa
recherche. Pour un essaim, la décision passe par la reine : `follow_colony_decision(ColonyDecision)`, puis
`move_to_habitat`, qui emmène tout l'essaim. `habitat_id: null` signifie qu'aucun habitat n'est choisi. `decision` porte les champs de l'événement (§3) ; Godot impose lui-même `bee_id`,
`chosen_habitat_id`, `outcome` et `result`.

```json
→ {"bee_id": "bee-3", "habitat_id": "hab-1", "decision": {"source": "openjev", "probabilities": {...}, ...}}
← {"bee_id": "bee-3", "habitat_id": "hab-1", "result": "flying"}
→ {"bee_id": "bee-4", "habitat_id": "hab-6"}
← {"ok": false, "error": "honey_bee does not accept habitat type bare_soil"}
```

- **Décision valide** : un événement `decision` est publié, avec `result` valant `"flying"`, ou `"none"` sans choix.
- **Décision invalide** : elle est refusée, et un événement `decision` est quand même publié avec `result: "rejected"`,
  `outcome: "refused"` et le motif dans `reason`.
- **Simulation en pause** : la décision est refusée (`simulation is paused`) sans événement.

### `reference_decision`

La logique de choix d'origine (`Bee.score_breakdown` + `Bee.choose_habitat`), **calculée pour comparaison, jamais
appliquée**.

```json
→ {"bee_id": "bee-3", "habitat_ids": ["hab-1", "hab-2"]}
← {"choice": "hab-1", "threshold": 0.7,
   "scores": [{"habitat_id": "hab-1", "score": 0.68, "breakdown": {"cavity_volume_l": 1.0, ...}}, ...]}
```

Le bruit de curiosité est tiré à chaque évaluation. Le choix peut donc, rarement, différer du meilleur score listé.

---

## 3. Événements

Chaque événement a la forme `{"seq": int, "tick": int, "type": str, "data": {...}}`.

| `type` | `data` |
|---|---|
| `entity_added` | le résumé de l'entité (comme dans `list_entities`) |
| `entity_removed` | `{"id", "kind", "released_bee_ids"}` |
| `world_cleared` | `{"removed": n}` |
| `paused`, `resumed` | `{}` |
| `speed_changed` | `{"speed"}` |
| `decision` | voir ci-dessous (publié par `apply_decision`) |
| `flight_started` | `{"id", "kind", "habitat_id", "from_x", "from_y", "to_x", "to_y", "distance", "speed"}` |
| `arrived` | `{"id", "kind", "habitat_id", "flight_ticks", "found_after_days"}` : arrivée **et** installation |
| `arrival_failed` | `{"id", "kind", "habitat_id", "flight_ticks", "reason"}` : `"full"` (plein à l'arrivée) ou `"removed"` (retiré pendant le vol) |
| `swarm_exposed` | `{"id", "x", "y", "population"}` : délai de grappe écoulé, nid à découvert |

### Format d'un événement de décision

Défini dans [`godot/entities/decision_event.gd`](../godot/entities/decision_event.gd), il ne dépend pas de la source
de la décision. Le backend le remplit (source `"openjev"`), Godot le publie. Exemple :

```json
{"seq": 21, "tick": 596, "type": "decision", "data": {
  "bee_id": "bee-8",
  "evaluated": [
    {"habitat_id": "hab-1", "score": 0.24, "reference_score": 0.66, "breakdown": {"cavity_volume_l": 1.0, "entrance_height_m": 1.0, "...": 0}},
    {"habitat_id": "hab-2", "score": 0.10, "reference_score": 0.39, "breakdown": {"...": 0}}
  ],
  "chosen_habitat_id": null,
  "outcome": "refused",
  "reason": "best fit hab-1 judged below the threshold (p accept=0.34)",
  "source": "openjev",
  "result": "none",
  "probabilities": {"hab-1": 0.24, "hab-2": 0.10, "none": 0.66},
  "reference": {"choice": null, "threshold": 0.7},
  "agreement": true,
  "model": {"model": "alanhuangya/OpenJev-1.7B", "revision": "7418ae8b6e3b6a6507a8a58729ae491cd1c732d9", "device": "mps", "latency_ms": 612}
}}
```

| Champ | Contenu |
|---|---|
| `bee_id` | abeille qui décide |
| `evaluated` | habitats évalués : `score` = probabilité donnée par la source, `reference_score` et `breakdown` = score total et détail par critère de la logique de référence |
| `chosen_habitat_id` | habitat retenu, ou `null` en cas de refus ou de rejet |
| `outcome` | `"chosen"` ou `"refused"` (déduit de `chosen_habitat_id`) |
| `reason` | justification (pour un rejet : le motif donné par Godot) |
| `source` | origine de la décision : `"openjev"` ; `"collective"` plus tard |
| `result` | ce qui a suivi : `"flying"` (envol ; l'installation est l'événement `arrived`), `"none"` (aucun choix), `"rejected"` (refusée par Godot) |
| `probabilities` | probabilité de chaque option, `"none"` compris |
| `reference` | choix de la logique de référence (`choice`) et seuil d'acceptation, pour comparaison |
| `agreement` | `true` si la source et la référence font le même choix |
| `model` | modèle, révision, appareil et temps de réponse |
| `context` | informations données au décideur : `distances` (habitat → m) ; pour un essaim, `population` et `days_left` (ignorés par la référence) |

---

## 4. API HTTP du backend

Toutes les réponses sont en JSON. En cas d'erreur, la réponse est `{"error": "message"}`, avec le code :

- **400** : validation refusée, par Python ou par Godot ;
- **404** : entité inconnue ;
- **503** : simulation indisponible.

| Méthode et route | Commande | Code de succès |
|---|---|---|
| `GET /` | page du tableau de bord | 200 |
| `GET /api/catalog` | `get_catalog` | 200 |
| `GET /api/state` | `get_state` | 200 |
| `GET /api/entities` | `list_entities` | 200 |
| `GET /api/entities/{id}` | `get_entity` | 200 |
| `DELETE /api/entities/{id}` | `remove_entity` | 200 |
| `POST /api/habitats` | `add_habitat` (corps = arguments) | 201 |
| `POST /api/bees` | `add_bee` (corps = arguments) | 201 |
| `POST /api/swarms` | `add_swarm` (corps = arguments) | 201 |
| `POST /api/world/clear` | `clear_world` | 200 |
| `POST /api/simulation/pause` | `pause` | 200 |
| `POST /api/simulation/resume` | `resume` | 200 |
| `POST /api/simulation/speed` | `set_speed` (`{"speed": 2}`) | 200 |
| `GET /api/events?since=N` | `get_events` | 200 |
| `GET /api/decision/status` | état du service de décision (voir §5) | 200 |
| `GET /api/kpi` | KPI de la dernière capture | 200 |
| `WS /ws` | flux temps réel (voir §5) | — |

Exemples :

```sh
curl -X POST localhost:8000/api/habitats -H 'content-type: application/json' \
     -d '{"type":"tree_cavity","x":200,"y":150}'
# 201 {"id":"hab-1","kind":"habitat","type":"tree_cavity","x":200.0,"y":150.0,"capacity":1,"occupants":0}

curl -X POST localhost:8000/api/bees -H 'content-type: application/json' -d '{"species":"wasp","x":1,"y":1}'
# 400 {"error":"unknown species 'wasp'; accepted: honey_bee, bumblebee, mason_bee, mining_bee, carpenter_bee"}

curl localhost:8000/api/entities/nope
# 404 {"error":"unknown entity nope"}

curl -X POST localhost:8000/api/simulation/speed -H 'content-type: application/json' -d '{"speed":4}'
# 200 {"speed":4.0}
```

---

## 5. Temps réel (WebSocket `/ws`)

À la connexion, puis à chaque changement (nouvel événement ou tick qui avance), et au plus toutes les
`DASHBOARD_UPDATE_INTERVAL` secondes (0,25 par défaut), le backend envoie une **capture**. Les positions ne sont donc
pas envoyées à chaque tick ; le navigateur fait glisser chaque entité vers sa nouvelle position entre deux captures.

```json
{"type": "snapshot",
 "state": {...get_state...},
 "entities": [...list_entities...],
 "kpi": {...voir §6...},
 "world_events": [...200 derniers événements du monde...],
 "decision_events": [...200 derniers événements "decision"...],
 "decision_service": {"provider": "openjev", "available": true, "model": "alanhuangya/OpenJev-1.7B",
                      "revision": "7418ae8b…", "device": "mps", "dtype": "float32", "avg_latency_ms": 559.2,
                      "decisions": 20, "pending": 0, "interval_ticks": 120, "concurrency": 2, "max_candidates": 12,
                      "last_error": null},
 "events_lost": false}
```

Le canal ne va que du backend vers le navigateur ; toutes les actions passent par l'API HTTP.

### Choix techniques

- **Relevé périodique avec curseur, plutôt qu'envoi spontané par Godot.**
  - Toutes les 250 ms, le backend appelle `get_events(since=curseur)`, puis `get_state` et `list_entities`.
  - Le protocole TCP reste purement requête/réponse : aucun message spontané ne peut se glisser entre une
    requête et sa réponse, et Godot n'a pas à gérer la diffusion à plusieurs clients.
  - Le curseur garantit qu'aucun événement n'est perdu entre deux relevés ; un débordement du journal est signalé
    par `lost`.
  - Les événements gardent leur tick de simulation, donc une latence de 250 ms ne fausse pas leur chronologie.
  - Limite : les entités et les événements viennent de requêtes distinctes, donc une capture peut montrer une
    entité un relevé avant son événement (≤ 250 ms).
- **Une seule connexion TCP, protégée par un verrou.** `GodotEngine.send` réserve la connexion pendant chaque paire
  requête/réponse. Les requêtes HTTP (exécutées en parallèle par FastAPI) et le relevé passent donc l'un après
  l'autre sans jamais mélanger leurs réponses. Chaque commande Godot est très courte, donc l'attente reste
  négligeable à l'échelle d'un tableau de bord local.

---

## 6. KPI

Calculés par le backend ([`backend/bzz/kpi.py`](../backend/bzz/kpi.py)) à partir de l'état, des entités et des
événements fournis par Godot. Le navigateur ne fait aucun calcul de simulation.

| Clé | Contenu |
|---|---|
| `sim` | `tick`, `seconds` (ticks / 60), `day` (à partir de 1), `hour` (0–24), `paused`, `speed` |
| `habitats_by_type`, `bees_by_species` | effectifs (0 inclus pour chaque type et espèce du catalogue) |
| `trait_distribution` | pour chaque trait, nombre d'abeilles dans 5 classes : 0–0,2 … 0,8–1 |
| `bees_by_state` | abeilles en recherche, en attente, en vol, installées |
| `swarms_by_state`, `swarms` | essaims en grappe, en vol, installés, à découvert ; liste avec population et jours restants |
| `bees_settled`, `bees_homeless` | abeilles installées ou non |
| `movement` | `arrivals`, `arrival_failures`, `failures_by_reason` (`full`, `removed`), `avg_days_to_habitat` (de l'ajout à l'installation, en jours simulés), `avg_flight_hours` (heures simulées), `swarms_exposed` |
| `occupancy` | pour chaque habitat : `occupants`, `capacity`, `rate` |
| `decisions` | `service` (état du service), `count`, `chosen`, `refused`, `rejected`, `avg_chosen_score` (probabilité moyenne des habitats choisis), `avg_chosen_reference_score`, `agreement_rate`, `agreement_by_species`, `by_species`, `by_trait` |

Les KPI de décision et de déplacement portent sur les 20 000 derniers événements de ce type reçus depuis le
démarrage du backend.
