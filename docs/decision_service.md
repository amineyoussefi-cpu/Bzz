# Service de décision OpenJev

Les abeilles choisissent leur habitat grâce à **OpenJev**, un modèle de décision open source exécuté **sur la
machine de l'utilisateur**. Il ne faut ni clé API ni service en ligne : seul le premier lancement télécharge les poids
depuis Hugging Face.

```
Tableau de bord ◄──► Backend Python (Docker ou local) ◄──TCP JSON──► Godot (état du monde, validation)
                          │
                          └──HTTP local──► Service de décision OpenJev (hors Docker : decision/service.py)
```

- **Modèle** : [`alanhuangya/OpenJev-1.7B`](https://huggingface.co/alanhuangya/OpenJev-1.7B), sous licence
  Apache-2.0. Le code vient du projet [`alanhuangyoo/OpenJev`](https://github.com/alanhuangyoo/OpenJev) (paquet
  `openjev-ai` 0.2.1, importé sous le nom `wev`).
- **Révision figée** : `7418ae8b6e3b6a6507a8a58729ae491cd1c732d9`. Tout le monde obtient les mêmes poids, donc les
  mêmes résultats.
- **Pourquoi hors de Docker** : Docker sur Mac n'a pas accès au GPU. Godot, le backend et le tableau de bord restent
  dans Docker Compose ; seul ce service tourne directement sur la machine.

---

## 1. Installation pas à pas

### macOS (Apple Silicon)

1. Installer Python 3.10 ou plus récent (`python3 --version`), par exemple avec `brew install python`.
2. Depuis le dossier du dépôt :
   ```sh
   cp .env.example .env        # facultatif : pour changer les paramètres
   ./decision/start.sh
   ```
   - **Au premier lancement**, le script crée `decision/.venv`, installe les dépendances figées
     (`decision/requirements.txt`, environ 1 Go), puis télécharge les poids (environ 3,2 Go) dans `decision/.cache`.
   - **Aux lancements suivants**, tout est déjà là : le service démarre hors ligne en quelques secondes.
3. Le service affiche par exemple `OpenJev ready: model=alanhuangya/OpenJev-1.7B revision=7418ae8b6e3b device=mps`
   et écoute sur `http://127.0.0.1:8009`.
4. Dans un autre terminal, lancer le projet : `docker compose up -d`, ou sans Docker
   `cd backend && ../.venv/bin/python -m bzz.server`. Ouvrir ensuite <http://localhost:8000>.

### Windows + carte NVIDIA (16 Go de VRAM)

1. Installer un pilote NVIDIA récent, puis Python 3.10 ou plus récent depuis python.org, en cochant le lanceur `py`.
2. Dans PowerShell, depuis le dossier du dépôt :
   ```powershell
   Copy-Item .env.example .env   # facultatif
   powershell -ExecutionPolicy Bypass -File .\decision\start.ps1
   ```
   - **Au premier lancement**, le script crée `decision\.venv` et installe torch 2.14.1 **compilé pour CUDA** :
     `cu126` par défaut, `cu130` détecté automatiquement pour les RTX 50xx. Le choix est forçable avec `TORCH_CUDA`.
   - Il installe ensuite les autres dépendances et télécharge les poids.
3. Le service doit afficher `device=cuda`. S'il affiche `cpu`, le pilote ou la version CUDA de torch ne correspondent
   pas : supprimer `decision\.venv` et relancer avec `TORCH_CUDA=cu130` (ou `cu126`).
4. Lancer le projet avec `docker compose up -d` (Docker Desktop), puis ouvrir <http://localhost:8000>.

### Vérifier

```sh
curl http://127.0.0.1:8009/health
# {"status":"ok","model":"alanhuangya/OpenJev-1.7B","revision":"7418ae8b...","device":"mps","dtype":"float32",
#  "requests":0,"errors":0,"avg_latency_ms":null}
```

Le tableau de bord affiche le même état dans la section « Décisions des abeilles » : modèle, révision, appareil, temps
de réponse moyen et disponibilité.

---

## 2. Paramètres

Tous sont facultatifs, dans `.env` (voir `.env.example`). Les scripts de lancement lisent `.env`.

| Variable | Défaut | Rôle |
|---|---|---|
| `OPENJEV_MODEL` | `alanhuangya/OpenJev-1.7B` | dépôt Hugging Face du modèle (par ex. `alanhuangya/OpenJev-4B` sur une machine plus puissante) |
| `OPENJEV_REVISION` | `7418ae8b…` | révision figée ; la changer avec le modèle |
| `OPENJEV_DEVICE` | `auto` | `auto` (CUDA, sinon MPS, sinon processeur), `cuda`, `mps`, `cpu` |
| `OPENJEV_CACHE_DIR` | `.cache` | dossier des poids, relatif à `decision/` (ignoré par git) |
| `OPENJEV_HOST`, `OPENJEV_PORT` | `127.0.0.1`, `8009` | adresse d'écoute du service |
| `TORCH_CUDA` | auto | Windows : `cu126` ou `cu130` |
| `DECISION_SERVICE_URL` | `http://127.0.0.1:8009` | adresse du service vue par le backend hors Docker |
| `DECISION_SERVICE_URL_FROM_DOCKER` | `http://host.docker.internal:8009` | même adresse vue depuis le conteneur backend |
| `DECISION_INTERVAL_TICKS` | `120` | chaque abeille sans habitat demande une décision tous les N ticks (2 s simulées à ×1) |
| `DECISION_CONCURRENCY` | `2` | décisions calculées en même temps |
| `DECISION_MAX_CANDIDATES` | `12` | habitats montrés au modèle (présélection, §4) |
| `DECISION_TIMEOUT` | `30` | secondes avant d'abandonner un appel au modèle |

Choisir le modèle 4B ne demande aucune modification du code : il suffit de définir `OPENJEV_MODEL` et
`OPENJEV_REVISION`, puis de relancer le service. La version 0.2 de ce modèle n'a pas été testée dans ce projet.

---

## 3. Mesures sur Mac (première tâche de l'étape)

Mac mini Apple M4 Pro, 24 Go de mémoire unifiée, torch 2.14.1, révision `7418ae8b`, le 2026-10-20.

| Appareil | Chargement depuis le cache | Requête courte (3 options) | Requête du projet (§5) | Mémoire |
|---|---|---|---|---|
| MPS | 2,5 s | 97 ms (médiane) | ~550 ms (médiane, 75 scénarios) | 7,7 Go alloués sur le GPU (float32) |
| Processeur | 1,2 s | 295 ms (médiane) | non mesuré | ~10,6 Go de RAM au pic |

- Le premier téléchargement des poids (3,2 Go) a pris environ 6 minutes.
- Les rechargements suivants fonctionnent avec `HF_HUB_OFFLINE=1`, sans aucun accès réseau.
- Sur MPS et sur processeur, le modèle tourne en float32 ; sur CUDA, `wev` utilise bf16, d'où environ deux fois
  moins de mémoire.
- La configuration Windows + NVIDIA 16 Go **n'a pas pu être testée** ici : le script et les valeurs sont fournis,
  mais à valider sur une vraie machine.

---

## 4. Déroulement d'une décision

La boucle de décision vit dans le backend ([`backend/bzz/decision/loop.py`](../backend/bzz/decision/loop.py)).

1. **Cadence** : uniquement quand la simulation tourne, tous les `DECISION_INTERVAL_TICKS` ticks, pour chaque abeille
   en recherche et chaque essaim en grappe qui n'a pas déjà une décision en cours. Les abeilles en vol, installées
   ou en attente, et les essaims à découvert, ne demandent rien. Au plus `DECISION_CONCURRENCY` décisions à la fois. Les appels
   passent par des threads : ils ne bloquent ni l'API, ni le tableau de bord, ni Godot.
2. **Situation** : `get_decision_situation` (Godot) décrit l'abeille et chaque habitat : caractéristiques, distance,
   type accepté, place libre.
3. **Présélection** : seuls les habitats **éligibles** (type accepté par l'espèce, place libre) sont proposés, les plus
   proches d'abord, `DECISION_MAX_CANDIDATES` au maximum. Avec 12 candidats, la requête reste très loin de la limite
   de 4096 tokens d'OpenJev. Sans aucun candidat éligible, aucun appel n'est fait et aucun événement n'est émis.
4. **OpenJev** (`OpenJevProvider`) répond. En parallèle, la **référence** (`ReferenceProvider`, logique d'origine de
   `Bee`, exécutée par Godot) calcule son propre choix **sans l'appliquer**.
5. **Application** : `apply_decision` (Godot) vérifie que l'abeille existe et n'a pas d'habitat, que l'habitat existe,
   que son type est accepté et qu'il reste de la place.
   - Si la décision est valide, l'abeille (ou l'essaim, mené par sa reine via une `ColonyDecision`) **s'envole**
     vers l'habitat et ne s'y installe qu'à l'arrivée ; Godot publie `decision`, puis `flight_started` et `arrived`
     (ou `arrival_failed` si l'habitat est plein ou retiré entre-temps).
   - Sinon, Godot la **rejette** et publie un événement `decision` dont `result` vaut `"rejected"`.
   - Si la simulation a été mise en pause entre-temps, rien n'est appliqué et aucun événement n'est publié.
6. **Service indisponible** : aucune décision n'est prise et le tableau de bord l'indique. Il n'y a **pas de bascule**
   vers la logique de référence.

**Essaims.** La situation envoyée à OpenJev décrit un essaim d'abeilles mellifères en grappe. Elle ajoute :

- sa **population** et son **délai restant** ;
- la **distance** de chaque cavité depuis la grappe ;
- une règle : « refuser est possible tant qu'il reste du temps ; quand le temps manque, une cavité acceptable vaut
  mieux que rien ».

La logique de référence, elle, ignore le délai et la distance.

---

## 5. Requêtes envoyées au modèle

OpenJev n'est pas réentraîné. Il s'imprègne de la logique d'origine (`Bee.score_breakdown`, `choose_habitat`,
[référence §3–5](reference_abeilles.md)) par la façon dont la situation et les questions sont rédigées, en anglais,
la langue du modèle.

Ce travail est fait dans [`backend/bzz/decision/prompting.py`](../backend/bzz/decision/prompting.py), testé séparément
dans `tests/test_decisions.py`. **Les scores de la logique de référence ne sont jamais transmis** : un test le vérifie.
Chaque critère est décrit par l'écart entre la valeur et l'idéal, rapporté à la tolérance. C'est un simple calcul sur
la situation, pas un score.

Exemple réel : une abeille mellifère « prudente » face à une cavité d'arbre et une petite ruche.

```json
{
  "state": {
    "task": "A bee is choosing a habitat to nest in. Judge every candidate with this bee's preferences and personality, following the rules.",
    "bee": "honey bee (Apis mellifera), a social bee whose swarm needs a nest cavity",
    "accepted habitat types": "tree cavity, hive box",
    "preferences": [
      "cavity volume (L): ideal 40, tolerance 35, weight 2",
      "entrance diameter (mm): ideal 40, tolerance 40, weight 1",
      "entrance height above ground (m): ideal 5, tolerance 5, weight 1",
      "old nest present (1 = yes, 0 = no): ideal 1, tolerance 1, weight 0.5",
      "flowers nearby (from 0 to 1): ideal 1, tolerance 1, weight 1"
    ],
    "personality": {
      "pickiness 0.80 (high)": "how demanding the bee is: needs a very good overall fit",
      "boldness 0.10 (low)": "tolerance to predator risk: strongly avoids predator risk",
      "sociability 0.40 (medium)": "attitude to busy shared sites: is indifferent to other nests",
      "curiosity 0.20 (low)": "how unpredictable its judgement is: judges consistently"
    },
    "acceptance threshold": "0.70 (minimum overall fit to accept a habitat)",
    "rules": [
      "Each preference gives a fit between 0 and 1: 1 at the ideal value, falling linearly to 0 at ideal plus or minus the tolerance.",
      "The overall fit is the weighted average of the preference fits (a weight of 2 counts twice).",
      "Predator risk lowers the overall fit by risk x (1 - boldness).",
      "On a site that hosts several nests, a sociability above 0.5 adds up to 0.2 in proportion to how busy the site is; below 0.5 it removes up to 0.2.",
      "Only habitat types the species accepts, with free space, are listed as candidates.",
      "Choose the candidate with the best overall fit if that fit reaches the acceptance threshold; otherwise choose none."
    ],
    "candidates": {
      "hab-1": "tree cavity, cavity volume 40 L (at the ideal), entrance diameter 40 mm (at the ideal), entrance height above ground 5 m (at the ideal), old nest present 0 (outside the tolerance), flowers nearby 0.6 (0.4 from the ideal, tolerance 1), predator risk 0.2",
      "hab-2": "hive box, cavity volume 12 L (28 from the ideal, tolerance 35), entrance diameter 40 mm (at the ideal), entrance height above ground 1 m (4 from the ideal, tolerance 5), old nest present 0 (outside the tolerance), flowers nearby 0.6 (0.4 from the ideal, tolerance 1), predator risk 0.1"
    }
  },
  "questions": {
    "best": {"type": "choice", "instructions": "Which candidate has the best overall fit for this bee?",
             "criteria": {"hab-1": "…même description…", "hab-2": "…"}},
    "accept": {"type": "noul",
               "instructions": "The best candidate's overall fit reaches this bee's acceptance threshold (0.70).",
               "criteria": {"true": "Good enough: the bee settles there.", "false": "Not good enough: the bee keeps looking."}}
  }
}
```

Le modèle répond aux deux questions **en une seule passe**, avec des probabilités calibrées :

```json
{"model": "wev-latest",
 "answers": {"best": {"type": "choice", "choice": "hab-1", "confidence": 0.3915, "probabilities": {"hab-1": 0.6957, "hab-2": 0.3043}},
             "accept": {"type": "noul", "noul": 0.3441}},
 "usage": {"input_tokens": 839, "output_tokens": 80}, "latency_ms": 1364}
```

Ici, OpenJev désigne bien la cavité d'arbre comme le meilleur habitat, mais juge à 0,34 qu'elle atteint le seuil de
0,70 de cette abeille exigeante. Il refuse donc. La référence, elle, choisit `hab-1` : c'est un désaccord typique,
situé autour du seuil (voir §6).

La décision se lit ainsi (`read_answer`) :

- l'abeille choisit le meilleur habitat si P(accept) ≥ 0,5, et aucun sinon ;
- la probabilité d'un habitat vaut P(meilleur = habitat) × P(accept) ;
- la probabilité de « aucun » vaut 1 − P(accept).

Pourquoi deux questions : une question unique avec une option « aucun » ne menait presque jamais à un refus. Voir
l'historique des formulations dans le [rapport de comparaison](rapport_comparaison.md).

---

## 6. Comparaison avec la logique de référence

- **En direct** : chaque événement de décision contient le choix d'OpenJev, celui de la référence, les probabilités
  et `agreement`. Le tableau de bord affiche le taux d'accord, global et par espèce.
- **Scénarios fixes** : `cd backend && python -m bzz.decision.compare` (service lancé). Le script évalue 5 espèces ×
  5 profils × 3 jeux d'habitats, avec des graines fixes. Il écrit [docs/rapport_comparaison.md](rapport_comparaison.md)
  et `docs/comparison/results.json`.

**Résultat actuel** :

- **53 % d'accord** sur la décision finale ;
- **75 %** sur le meilleur habitat, en ignorant le seuil d'acceptation.

La logique de référence **ne peut pas encore être supprimée** : l'écart vient surtout du jugement « assez bon pour
s'installer » autour du seuil.

---

## 7. Conditions d'utilisation des données d'entraînement

- Le modèle est sous Apache-2.0, mais certaines de ses **données d'entraînement ont leurs propres conditions** :
  - plusieurs tâches de `tasksource-jev` sont réservées à la recherche ;
  - des épisodes « enseignant » sont des sorties de qwen3-max, soumises aux conditions de leur fournisseur.
- La fiche du modèle demande de le traiter comme un **artefact de recherche** et de **vérifier ces conditions avant
  tout usage commercial**.

---

## 8. Dépannage

| Symptôme | Cause probable |
|---|---|
| Tableau de bord : « Service de décision OpenJev indisponible » | service non lancé, mauvais `DECISION_SERVICE_URL`, ou pare-feu |
| Depuis Docker sous Linux, service injoignable | lancer le service avec `OPENJEV_HOST=0.0.0.0` (Docker Desktop Mac/Windows n'en a pas besoin) |
| `device 'cuda' is not available` | torch installé sans CUDA : supprimer `decision/.venv` et relancer le script Windows |
| Premier lancement long | téléchargement des poids (3,2 Go), une seule fois |
| Les abeilles ne décident pas | simulation en pause, aucun habitat éligible, ou service indisponible (voir le tableau de bord) |
