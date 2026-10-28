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

Lancer : `cd backend && python -m bzz.server` puis ouvrir <http://localhost:8000>, ou `docker compose up`.

---

## 1. Conventions

- **Noms lisibles** partout : `"tree_cavity"`, `"honey_bee"`, `"scout"`, jamais de numéro d'énumération.
  Ils sont générés depuis les énumérations GDScript (`Habitat.Type`, `BeeSpecies.Id`, `BeeRole.Id`).
- **Identifiants** : `hab-N` ou `bee-N`, uniques et stables, jamais réutilisés pendant la vie du processus Godot
  (même après `clear_world`).
- **Positions** en unités du monde : `0 ≤ x ≤ largeur`, `0 ≤ y ≤ hauteur`. Taille par défaut 1000 × 700
  (`WorldApi.DEFAULT_SIZE`), modifiable par `WORLD_WIDTH` / `WORLD_HEIGHT`.
- **Validation double** : Python (`commands.py`, à partir du catalogue que Godot génère) puis Godot (`world_api.gd`).
  Une valeur hors bornes est **refusée, jamais corrigée** ; le message d'erreur liste les valeurs acceptées.
  Tout est vérifié avant la création : une commande refusée ne laisse aucune entité partielle.
- **Temps** : les événements sont horodatés en **ticks de simulation**. Le compteur n'avance que lorsque la simulation
  tourne ; à la vitesse ×1, 60 ticks valent une seconde simulée.

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
| `list_entities` | — |
| `get_entity` | `id` |
| `remove_entity` | `id` |
| `clear_world` | — |
| `pause`, `resume` | — |
| `set_speed` | `speed` (0.25 à 8) |
| `get_events` | `since?` (curseur, défaut 0) |

### `get_state`

```json
← {"tick": 1435, "paused": false, "speed": 1.0, "ticks_per_second": 60,
   "world": {"width": 1000, "height": 700}, "habitats": 5, "bees": 5, "node_count": 10,
   "last_event_seq": 12, "decision_mechanism": null, "physics_frames": 2210, "process_frames": 2205}
```

`decision_mechanism` vaut `null` : aucun mécanisme de décision n'existe encore.

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

La personnalité s'écrit sous l'une de ces trois formes :

| Forme | Exemple |
|---|---|
| préréglage | `{"preset": "prudente"}` |
| traits explicites (les 4, entre 0 et 1) | `{"traits": {"pickiness": 0.2, "boldness": 0.4, "sociability": 0.6, "curiosity": 0.8}}` |
| aléatoire, graine facultative (entier de 1 à 2³¹−1) | `{"random": true, "seed": 1234}` |

- Sans `personality`, la personnalité est aléatoire.
- La graine utilisée est toujours enregistrée (`get_entity` → `seed`). Une abeille aléatoire peut donc être recréée à
  l'identique : même espèce et même graine donnent la même personnalité.
- L'abeille reçoit les préférences par défaut de son espèce (`Bee.create`) et le rôle `follower`, sauf si `role` est donné.
- Elle est créée **sans habitat** (`home_id: null`).
- `x` et `y` sont facultatifs (les deux ou aucun). Sans position, l'abeille se pose **sur la branche de l'essaim**,
  au centre du monde (`get_catalog` → `branch`), en grappe avec les autres abeilles.

### `list_entities`

```json
← [{"id": "hab-1", "kind": "habitat", "type": "tree_cavity", "x": 200.0, "y": 150.0, "capacity": 1, "occupants": 0},
   {"id": "bee-2", "kind": "bee", "species": "honey_bee", "name": "Ada", "role": "scout", "x": 300.0, "y": 200.0,
    "personality": {...}, "home_id": null}]
```

### `get_entity`

```json
→ {"id": "bee-2"}
← {..., "accepted_habitat_types": ["tree_cavity", "hive_box"], "preferences": [{"criterion": "cavity_volume_l", ...}],
   "seed": 1867123, "personality_source": "preset:curieuse"}
→ {"id": "hab-1"}
← {..., "features": {"cavity_volume_l": 40.0, ...},
   "description": {"cavity_volume_l": "large cavity", "sun_exposure": "partly sunny", ...}, "occupant_ids": []}
```

`description` traduit les caractéristiques en mots, sur une échelle de 5 niveaux (`HabitatCatalog.LEVELS`).
C'est ce que perçoit une abeille. Les chiffres de `features` restent la référence.

### `remove_entity` et `clear_world`

```json
→ {"id": "hab-1"}
← {"id": "hab-1", "kind": "habitat", "released_bee_ids": []}
→ clear_world
← {"removed": 4}
```

Retirer un habitat libère ses occupants (`Bee.leave_home`) ; leurs identifiants sont listés dans `released_bee_ids`.

### `move_entity`

```json
→ {"id": "bee-2", "x": 300, "y": 200}
← {"id": "bee-2", "kind": "bee", "x": 300.0, "y": 200.0, ...}
```

Déplace une entité dans le monde (glisser-déposer du tableau de bord). Émet `entity_moved` `{"id", "x", "y"}`.

### `update_habitat`

```json
→ {"id": "hab-1", "features": {"sun_exposure": 0.05, "capacity": 3}}
← {...même réponse que get_entity, avec features et description à jour...}
```

Modifie les caractéristiques d'un habitat existant, avec les mêmes règles qu'à la création. Les clés absentes ne
changent pas. La capacité ne peut pas descendre sous le nombre d'occupants. Émet `habitat_updated` `{"id", "features"}`.

### Recherche de nid : `answer_decision`

Quand la simulation tourne, l'essaim cherche un nid (`godot/entities/swarm.gd`) :

- Godot fait voler les abeilles, garde les danses et compte le quorum (**3** abeilles engagées sur un même site :
  tout l'essaim s'y envole et s'y installe).
- Pour juger, une abeille émet `decision_needed` et attend. Le backend pose la question à la LLM (1 appel, voir
  [methode_jeton.md](methode_jeton.md)) puis répond :

```json
→ {"bee_id": "bee-3", "kind": "evaluate_site", "answer": {"score": 4}}
← {...résumé de l'abeille...}
```

| `kind` | `answer` |
|---|---|
| `evaluate_site` | `{"score": 1..5}` (suivi automatiquement d'une question `stay_or_leave`) |
| `stay_or_leave` | `{"choice": "stay" \| "go_back"}` |
| `judge_dances` | `{"follow": "<id d'un site dansé>" \| "none"}` |

Une réponse refusée (l'abeille n'attend plus cette question, valeur hors limites) renvoie une erreur et ne change rien.
Le résumé d'une abeille gagne `state` (`resting`, `flying`, `waiting`, `dancing`, `at_site`, `settled`), `site_id`
(site pour lequel elle s'est engagée), `dance_level` et `waiting_for`. Celui d'un habitat gagne `committed`.
`get_state` gagne `swarm` : `{"phase": "searching" | "moving" | "settled", "chosen_id", "quorum", "dances", "waiting"}`.

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

---

## 3. Événements

Chaque événement a la forme `{"seq": int, "tick": int, "type": str, "data": {...}}`.

| `type` | `data` |
|---|---|
| `entity_added` | le résumé de l'entité (comme dans `list_entities`) |
| `entity_removed` | `{"id", "kind", "released_bee_ids"}` |
| `entity_moved` | `{"id", "x", "y"}` |
| `habitat_updated` | `{"id", "features"}` |
| `decision_needed` | `{"bee_id", "kind", "personality", "situation"}` : question pour le cerveau (consommée par le backend) |
| `bee_decided` | `{"bee_id", "kind", "answer", "habitat_id"?}` |
| `bee_committed` | `{"bee_id", "habitat_id", "score"}` |
| `bee_danced` | `{"bee_id", "habitat_id", "level"}` |
| `bee_acted` | `{"bee_id", "fn", "target"}` : fonction exécutée (`explore`, `visit_habitat`, `go_back`, `go_back_to_branch`, `join_swarm`) |
| `swarm_decided` | `{"habitat_id", "committed"}` : quorum atteint, l'essaim part |
| `world_cleared` | `{"removed": n}` |
| `paused`, `resumed` | `{}` |
| `speed_changed` | `{"speed"}` |
| `decision` | voir ci-dessous — **jamais émis à cette étape** |

### Format d'un événement de décision

Défini dans [`godot/entities/decision_event.gd`](../godot/entities/decision_event.gd), il est déjà lu par les KPI et
par le tableau de bord. Il ne dépend pas de la source de la décision : un mécanisme individuel ou collectif
le remplit de la même façon.

```json
{"seq": 42, "tick": 900, "type": "decision", "data": {
  "bee_id": "bee-7",
  "evaluated": [
    {"habitat_id": "hab-1", "score": 0.82, "breakdown": {"cavity_volume_l": 1.0, "entrance_height_m": 0.9, "...": 0}},
    {"habitat_id": "hab-4", "score": 0.31, "breakdown": {"...": 0}}
  ],
  "chosen_habitat_id": "hab-1",
  "outcome": "chosen",
  "reason": "meilleur score au-dessus du seuil d'exigence",
  "source": "individual",
  "result": "settled"
}}
```

| Champ | Contenu |
|---|---|
| `bee_id` | abeille qui décide |
| `evaluated` | habitats évalués : score total et détail par critère (forme de `Bee.score_breakdown`) |
| `chosen_habitat_id` | habitat retenu, ou `null` en cas de refus |
| `outcome` | `"chosen"` ou `"refused"` (déduit de `chosen_habitat_id`) |
| `reason` | justification libre (facultative) |
| `source` | origine de la décision : `"individual"`, `"collective"`… |
| `result` | ce qui a suivi : `"settled"`, `"pending"`, `"none"`… |

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
| `PUT /api/entities/{id}/position` | `move_entity` (`{"x": 300, "y": 200}`) | 200 |
| `PUT /api/habitats/{id}/features` | `update_habitat` (corps = caractéristiques, ex. `{"humidity": 0.8}`) | 200 |
| `POST /api/habitats` | `add_habitat` (corps = arguments) | 201 |
| `POST /api/bees` | `add_bee` (corps = arguments) | 201 |
| `POST /api/world/clear` | `clear_world` | 200 |
| `POST /api/simulation/pause` | `pause` | 200 |
| `POST /api/simulation/resume` | `resume` | 200 |
| `POST /api/simulation/speed` | `set_speed` (`{"speed": 2}`) | 200 |
| `GET /api/events?since=N` | `get_events` | 200 |
| `GET /api/kpi` | KPI de la dernière capture | 200 |
| `WS /ws` | flux temps réel (voir §5) | — |

**Modèles LLM (Ollama).** Ces routes ne passent pas par Godot. Elles pilotent le modèle utilisé par le cerveau
des abeilles (`backend/bzz/brain.py`, voir [methode_jeton.md](methode_jeton.md)).

| Méthode et route | Rôle | Code de succès |
|---|---|---|
| `GET /api/models` | `{"current", "url", "available", "installed": [{"name", "size"}]}` ; `available: false` si Ollama ne répond pas | 200 |
| `PUT /api/models/current` | `{"model": "llama3.2:1b"}` change le modèle par défaut des abeilles ; il doit être installé | 200 |
| `PUT /api/bees/{id}/model` | `{"model": "qwen2.5:0.5b"}` donne à cette abeille son propre modèle ; `{"model": null}` la remet sur le modèle par défaut | 200 |
| `GET /api/bees/{id}/brain` | `{"model", "notebook", "calls"}` : son modèle propre (`null` = défaut), son carnet, ses derniers appels LLM (chacun avec le `model` utilisé) | 200 |
| `POST /api/models/pull` | `{"model": "qwen2.5:0.5b"}` télécharge un modèle ; la requête bloque jusqu'à la fin | 200 |

Erreurs : **400** si le nom est invalide, si le modèle n'est pas installé, ou si Ollama refuse (modèle inconnu) ;
**503** si Ollama est injoignable. Les choix de modèle ne sont pas sauvegardés : au redémarrage, c'est `BZZ_MODEL` qui s'applique.

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

À la connexion, puis à chaque changement (nouvel événement ou tick qui avance), le backend envoie une **capture** :

```json
{"type": "snapshot",
 "state": {...get_state...},
 "entities": [...list_entities...],
 "kpi": {...voir §6...},
 "world_events": [...200 derniers événements du monde...],
 "decision_events": [...200 derniers événements "decision"...],
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
| `sim` | `tick`, `seconds` (ticks / 60), `paused`, `speed` |
| `habitats_by_type`, `bees_by_species` | effectifs (0 inclus pour chaque type et espèce du catalogue) |
| `trait_distribution` | pour chaque trait, nombre d'abeilles dans 5 classes : 0–0,2 … 0,8–1 |
| `bees_settled`, `bees_homeless` | abeilles avec ou sans habitat (toutes sans habitat tant qu'il n'y a pas de décision) |
| `occupancy` | pour chaque habitat : `occupants`, `capacity`, `rate` |
| `decisions` | `mechanism` (`null`), `count`, `chosen`, `refused`, `avg_chosen_score`, `by_species`, `by_trait` |

Les KPI de décision sont déjà calculés à partir du format du §3 (un test le vérifie avec des événements fictifs) ;
ils restent à zéro tant qu'aucun mécanisme n'émet de décision.
