# Architecture pipeline et décisions RAG

## Version 1 — Pipeline de données

```text
Godot (simulation + UI)
  ⇄ bridge Python (protocole Godot actuel + Kafka)
  ⇄ Kafka
  ⇄ consommateurs Python
      └─ PostgreSQL (état durable et journaux)
```

Godot est propriétaire de l'état du monde. Le bridge traduit les événements, publie dans Kafka et transmet les commandes destinées à Godot. Les consommateurs persistent les événements; les écritures et reprises doivent être idempotentes.

### Tables PostgreSQL

- `worlds(id, config_json, created_at)`
- `entities(id, world_id, type, state_json, updated_at)`
- `world_events(event_id, world_id, tick, type, payload_json, occurred_at)`
- `bee_logs(event_id, bee_id, world_id, tick, kind, content, metadata_json, occurred_at)`

Clés primaires sur les identifiants. Index sur `(world_id, tick)` et `(bee_id, occurred_at)`.

### Topics Kafka

| Topic | Contenu | Clé de partition |
|---|---|---|
| `world.events` | Changements du monde, exploration, récolte, prédation | `world_id` |
| `bee.logs` | Observations, actions, résultats, dialogues | `bee_id` |
| `bee.commands` | Décisions à appliquer par Godot | `bee_id` |

Enveloppe commune : `event_id`, `world_id`, `tick`, `type`, `payload`, `occurred_at`, `schema_version`. Godot déduplique par `event_id`; le consommateur valide l'offset Kafka après l'écriture en base.

Le dépôt utilise actuellement un protocole TCP JSON entre le backend Python et Godot; Kafka n'est pas encore intégré. L'UI web actuelle devra être remplacée par l'UI Godot selon la cible produit.

## Version 2 — RAG et décision LLM

### Journal canonique par abeille

```json
{
  "event_id": "uuid",
  "world_id": "uuid",
  "bee_id": "bee-17",
  "tick": 420,
  "kind": "observation|action|result|dialogue",
  "content": "Nectar abondant à l'est; prédateur aperçu près de la rivière.",
  "metadata": {"x": 12, "y": 8, "confidence": 0.91},
  "occurred_at": "2026-11-15T12:00:00Z"
}
```

La source durable est `bee_logs`. Indexer les embeddings de `content` avec `world_id`, `bee_id`, `tick` et `kind` comme métadonnées. La recherche filtre d'abord par monde et abeille, puis classe par similarité et récence. Les décisions proposées restent distinctes des observations vérifiées.

### Contrat de décision

```text
Rôle : tu contrôles l'abeille {bee_id}.
État actuel : {state_json}
Actions autorisées : {allowed_actions}
Souvenirs récupérés : {rag_context}

Choisis une action valide selon l'état et les souvenirs. N'invente pas d'observations.
Si l'information manque, explore ou observe.
Réponds uniquement en JSON :
{"action":"explore|collect|return|communicate","target":null,"reason":"...","dialogue":"..."}
```

Le backend valide le JSON, l'action et la cible avant publication sur `bee.commands`. Conserver la réponse brute, les souvenirs utilisés, la validation et le résultat pour audit. En cas d'erreur ou de délai dépassé, utiliser une action de repli déterministe (`explore`).
