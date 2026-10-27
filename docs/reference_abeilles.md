# Référence : abeilles et habitats

Document de conception du peuplement du monde Bzz. Il décrit les **habitats** disponibles et les **traits de
personnalité** modélisés. Les abeilles n'ont pas de type d'espèce : chaque abeille est une entité générique
avec une personnalité et un rôle. **Les abeilles sont sans cerveau** : aucune logique de choix pour l'instant.

---

## 1. Types d'habitats

| | Type (`Habitat.Type`) | Description | Capacité typique |
|---|---|---|---|
| <img src="img/cavite_arbre.svg" width="120"> | `TREE_CAVITY` | creux dans un tronc, entrée en hauteur | 1 colonie |
| <img src="img/ruche.svg" width="120"> | `HIVE_BOX` | ruche ou nichoir artificiel | 1 colonie |
| <img src="img/terrier.svg" width="120"> | `RODENT_BURROW` | ancien terrier de rongeur, souterrain | 1 colonie |
| <img src="img/sol_nu.svg" width="120"> | `BARE_SOIL` | sol nu, sablonneux, ensoleillé | nombreux nids |
| <img src="img/tiges_creuses.svg" width="120"> | `HOLLOW_STEM` | tiges creuses, hôtel à insectes | un nid par tube |
| <img src="img/bois_mort.svg" width="120"> | `DEAD_WOOD` | tronc ou branche morte | quelques nids |

### Caractéristiques d'un habitat

Chaque instance de `Habitat` a ses propres valeurs :

| Attribut | Unité | Rôle |
|---|---|---|
| `habitat_type` | énumération | type du site |
| `cavity_volume_l` | litres | volume intérieur (≈ 0 pour un sol ou une tige) |
| `entrance_diameter_mm` | mm | diamètre d'entrée (0 = sans objet) |
| `entrance_height_m` | m | hauteur de l'entrée au-dessus du sol |
| `sun_exposure` | 0–1 | ensoleillement |
| `humidity` | 0–1 | humidité |
| `floral_abundance` | 0–1 | ressources florales à proximité |
| `predator_risk` | 0–1 | exposition aux prédateurs et parasites |
| `previously_occupied` | booléen | présence d'un ancien nid / de vieux rayons |
| `capacity`, `occupants` | entier, liste | combien d'abeilles ou colonies peuvent s'y installer, et qui y vit |

---

## 2. Personnalité

Chaque abeille porte une `BeePersonality` avec quatre traits entre 0 et 1. C'est une **invention de jeu**
destinée à rendre les individus distincts. Ces traits n'ont **aucun effet pour l'instant** — les abeilles sont
sans cerveau. Ils seront utilisés quand la logique de choix sera ajoutée.

| Trait | Description |
|---|---|
| `pickiness` (exigence) | à quel point l'abeille est difficile sur la qualité d'un habitat |
| `boldness` (audace) | tolérance au risque de prédation |
| `sociability` (sociabilité) | attrait pour les sites déjà fréquentés |
| `curiosity` (curiosité) | imprévisibilité dans les évaluations |

---

## 3. Modèle logiciel

Classes GDScript dans [`godot/entities/`](../godot/entities/) :

```
Bee (Node2D)                  Habitat (Node2D)
  bee_name                      habitat_type, caractéristiques…
  personality: BeePersonality   capacity, occupants
  home: Habitat
  role: BeeRole.Id
  behavior: BeeBehavior
  set_role(id)
```

Aucune logique d'évaluation ou de choix. La logique de choix d'habitat sera ajoutée ultérieurement.

### Rôles

Chaque abeille porte un **rôle** (`SCOUT` éclaireuse ou `FOLLOWER` suiveuse) —
voir le document dédié [Rôles et comportements](roles_comportements.md).
