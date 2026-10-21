# PROJECT_STATUS

_Dernière mise à jour : 2026-10-21 (prompt 7 : Godot dans sa propre fenêtre, tableau de bord dans le navigateur)_

Référence de reprise entre sessions. Ne décrit que ce qui existe réellement dans le dépôt.
Spécifications d'origine : [prompts/](prompts/) (`prompt1.txt` à `prompt7.txt`, `github_versioning.txt`, `portability.txt`).

## Architecture actuelle

```
Navigateur : tableau de bord ◄─HTTP+WebSocket─► Backend Python ◄─TCP JSON─► Godot 4.7.2 en FENÊTRE (sur l'hôte)
  actions + KPI                                  (Docker ou local)           main.gd → WorldApi + WorldView (lecture seule)
  bzz/static/index.html                          bzz/server.py, decision/      état, temps, vols, validation, affichage
                                                       │
                                                       └─HTTP local─► Service OpenJev (HORS Docker : decision/service.py)
```

**Évolution de décision (prompt 7).** Le prompt 1 imposait un Godot sans fenêtre. Godot devient aussi **la vue
principale de la simulation**, dans sa propre fenêtre native :

- il reste le seul propriétaire de l'état, du temps, des vols et de la validation ;
- la fenêtre est une **vue en lecture seule**, sans aucune action qui modifie le monde ;
- Python reste l'unique point d'entrée des commandes, et le protocole TCP ne change pas (`get_state` gagne seulement
  les champs informatifs `display` et `view_loaded`) ;
- le tableau de bord, dans le navigateur, garde toutes les actions et les KPI.

Docker ne pouvant pas ouvrir de fenêtre sur le bureau, **en mode fenêtre Godot tourne directement sur la machine**
(comme OpenJev), et le backend du conteneur l'atteint via `host.docker.internal`.

**Modes d'affichage** (`GODOT_DISPLAY`) :

- **`window`** (défaut de `.env.example`, pour l'utilisateur) : `godot/start.sh` ou `godot/start.ps1` lance Godot sur
  l'hôte, en fenêtre, sur `GODOT_LISTEN:GODOT_PORT` (`127.0.0.1:9876`). Compose ne démarre alors que le backend.
- **`headless`** (défaut du code, pour les tests, l'intégration continue et les serveurs) : comportement d'avant, avec
  Godot lancé par Python sans fenêtre, ou dans Docker avec `COMPOSE_PROFILES=headless` et
  `GODOT_HOST_FROM_DOCKER=godot`. La vue n'est alors ni chargée ni dessinée.

- **Godot** possède l'état du monde et le temps. Il décrit la situation d'une abeille ou d'un essaim, **valide et
  applique** les décisions, **fait voler** les abeilles et les essaims dans son cycle natif (`WorldApi.step`), et
  publie les événements.
- **Le backend** orchestre : situation → requête → OpenJev → comparaison avec la référence → application par Godot.
  Il expose l'API et calcule les KPI.
- **Le service OpenJev** tourne sur la machine de l'utilisateur, sans Docker (Docker sur Mac n'a pas accès au GPU).
  Il n'a besoin ni de clé API ni de réseau, hormis le téléchargement initial des poids.
- **Le tableau de bord** est un client du backend (décision du prompt 4) ; l'entrée stdin fonctionne toujours.
- **Modes Godot** (`GODOT_HOST`) : local (Python lance Godot ; import automatique si le cache `.godot/` manque) ou
  distant (Compose).

Fichiers :

- **godot/main.gd** — serveur TCP (`--host`, `--port`, `--world-width`, `--world-height`, `--dashboard-url`, et
  `--day-ticks`, `--flight-speed-factor`, `--swarm-speed-mps`, `--swarm-cluster-days`), délègue à `WorldApi`.
  Sans `--headless`, il charge la vue `godot/view/world_view.gd`, qu'il ajoute à côté du nœud World pour que ses
  enfants restent les seules entités.
- **godot/view/world_view.gd** — vue en lecture seule, dessinée avec des formes simples (`_draw`, `Camera2D`) à partir
  de `WorldApi._summary` :
  - limites du monde ;
  - habitats par type, avec identifiant et occupation ;
  - abeilles par espèce et par état ;
  - grappe sur sa branche, avec population et jours restants ;
  - trajectoires des vols ;
  - bandeau : jour, heure, état, vitesse, effectifs ;
  - message quand le monde est vide.

  Interactions de vue uniquement : molette pour zoomer, glisser ou flèches pour déplacer, F pour tout voir, survol ou
  clic pour les détails.
- **godot/start.sh / godot/start.ps1** — trouvent Godot (`GODOT_BIN`, `PATH`, emplacements habituels), vérifient la
  version (`GODOT_VERSION`), lisent `.env` et lancent Godot en fenêtre.
- **godot/tests/render_view.gd** — vérification visuelle manuelle : construit un monde, l'affiche en fenêtre et
  enregistre une capture PNG. Ce script ne fait pas partie de la suite de tests.
- **godot/api/world_api.gd** — catalogue, entités (`hab-N`, `bee-N`, `swarm-N`), horloge (tick, pause, vitesse,
  journée simulée), **vols et délais d'essaim** (`step`), journal d'événements, validation, paramètres
  (`DEFAULT_CONFIG`, seule source des valeurs par défaut). Décisions :
  - `get_decision_situation` : profil de l'abeille ou de l'essaim et tous les habitats, avec leur éligibilité ;
  - `apply_decision` : validation, puis **envol** (installation à l'arrivée) ou rejet, et événements ;
  - `reference_decision` : `Bee.score_breakdown` + `choose_habitat` (la reine pour un essaim), pour comparaison
    uniquement, jamais appliqué.
- **godot/entities/** :
  - `Habitat`, `HabitatCatalog` ;
  - `Bee` (logique de choix d'origine **inchangée**, utilisée seulement comme référence ; ajout de `flight` et `fly_to`) ;
  - `BeeSpecies` (ajout des vitesses de vol, et de l'abeille mellifère qui vit en essaim), `BeePersonality`,
    `Preference`, `DecisionEvent` (ajout de `context`) ;
  - **`Flight`** (vol en ligne droite) ;
  - **`Swarm`** (reine `Bee` de rôle `QUEEN` en nœud enfant, population, grappe, délai, états).
  - Rôles dans `roles/` : seul `QueenBehavior.move_to_habitat` est exécuté (le vol de l'essaim).
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
  - [docs/guide_installation.md](docs/guide_installation.md) (+ PDF) : préparer un Mac ou un PC Windows NVIDIA et
    lancer le projet, pas à pas ;
  - [docs/api.md](docs/api.md) : commandes, routes, événements, KPI ;
  - [docs/decision_service.md](docs/decision_service.md) : installation macOS et Windows, paramètres, mesures,
    format des requêtes, conditions d'utilisation ;
  - [docs/rapport_comparaison.md](docs/rapport_comparaison.md) (+ `docs/comparison/results.json`) ;
  - références abeilles et rôles (Markdown + PDF).
- **Docker** — `Dockerfile` (cibles `godot` et `backend`) et `compose.yaml` :
  - le service `godot` n'existe qu'avec le profil `headless` ;
  - le backend joint Godot via `GODOT_HOST_FROM_DOCKER` (`host.docker.internal` par défaut) et OpenJev via
    `DECISION_SERVICE_URL_FROM_DOCKER` ;
  - le port de Godot n'est jamais publié.

## Fonctionnalités implémentées

- **Fenêtre Godot** (prompt 7) : la simulation s'affiche en direct dans une fenêtre native (habitats, abeilles, grappes,
  vols, installations, bandeau d'information). Elle a sa propre fréquence d'affichage (60 images/s au maximum), et les
  ticks de simulation restent indépendants du dessin.
- **Connexion robuste** :
  - le backend démarre même si Godot n'est pas lancé, et s'y connecte dès qu'il l'est ;
  - fermer la fenêtre fait afficher « simulation non connectée » dans le tableau de bord, et la relancer le reconnecte
    automatiquement, sans redémarrer le backend (un nouveau Godot est un nouveau monde) ;
  - `restart` sur un Godot en fenêtre est refusé avec un message (« relancez-le avec godot/start.sh »), sans bloquer.
- **Tableau de bord** : indique « Godot : fenêtre », « headless » ou « non connecté ». La carte 2D est **gardée** comme
  vue simplifiée, car elle sert à cliquer une position lors d'un ajout et la fenêtre Godot ne transmet rien.

- **Construction du monde** depuis le tableau de bord ou l'API :
  - habitats ;
  - abeilles individuelles (personnalité par préréglage, traits ou aléatoire, avec graine facultative) ; l'abeille
    mellifère est refusée en individuel ;
  - **essaims** d'abeilles mellifères (`add_swarm` : population, personnalité collective, branche) ;
  - consultation, retrait, remise à zéro, pause, reprise et vitesse.
- **Temps simulé** : une journée dure `DAY_TICKS` ticks ; le tableau de bord affiche le jour et l'heure. La pause
  arrête le temps, les vols et les délais ; la vitesse accélère tout.
- **Déplacement** (prompt 6) :
  - après une décision, l'abeille ou l'essaim **vole en ligne droite** vers l'habitat, à la vitesse de son espèce
    × `FLIGHT_SPEED_FACTOR`, et **s'installe à l'arrivée** ;
  - l'habitat n'est pas réservé : s'il est plein à l'arrivée, c'est un échec (`arrival_failed`) et l'entité reprend
    sa recherche ;
  - si l'habitat est retiré pendant le vol, l'entité s'arrête sur place ;
  - une entité en vol ne demande aucune décision.
- **États** :
  - abeille : en recherche, **en attente** (aucun habitat compatible dans le monde), en vol, installée ;
  - essaim : en grappe, en vol, installé, **nid à découvert**.
- **Essaim** :
  - il dispose de `SWARM_CLUSTER_DAYS` jours en grappe ; le délai ne s'écoule qu'en grappe ;
  - il prend une décision collective unique (OpenJev) ;
  - la reine suit la `ColonyDecision` et l'emmène en vol ;
  - il occupe une seule place ;
  - s'il est en échec à l'arrivée, il se repose en grappe sur place avec le délai qu'il lui restait ;
  - si le délai expire, il passe en « nid à découvert ».
- **Décisions par OpenJev**, uniquement quand la simulation tourne :
  - tous les `DECISION_INTERVAL_TICKS` ticks, chaque abeille sans habitat demande une décision, avec au plus
    `DECISION_CONCURRENCY` décisions à la fois, exécutées dans des threads, sans bloquer l'API ni Godot
    (abeilles en recherche et essaims en grappe uniquement) ;
  - OpenJev reçoit les habitats éligibles les plus proches (12 au maximum) et répond à deux questions en une passe :
    « meilleur habitat ? » et « atteint le seuil ? » ;
  - pour un essaim, OpenJev reçoit aussi la population, le délai restant et la distance depuis la grappe ;
  - Godot valide la décision : une décision invalide est rejetée et produit un événement de refus.
- **Comparaison** : à chaque décision, la logique de référence calcule son choix sans l'appliquer. L'événement
  contient les deux choix, les probabilités et l'accord.
- **Service indisponible** : aucune décision n'est prise, l'état est affiché, et il n'y a **pas de bascule** vers la
  référence.
- **Tableau de bord** :
  - fil des décisions (choix ou refus, probabilités, source, choix de référence, accord) ;
  - choix, refus et rejets ; probabilité moyenne et score de référence moyen des habitats choisis ;
  - accord global et par espèce ; répartition par espèce et par trait ;
  - état du service : modèle, révision, appareil, temps de réponse, disponibilité ;
  - **carte animée** : déplacement fluide entre deux captures, trajectoire en pointillés, grappe sur sa branche avec
    population et jours restants, états distinguables ;
  - **formulaire d'essaim** ; le formulaire d'abeille ne propose plus l'abeille mellifère ;
  - **KPI** : abeilles par état, essaims par état (avec jours restants), temps moyen pour trouver un habitat (jours),
    durée moyenne des vols (heures simulées), arrivées, échecs à l'arrivée, essaims à découvert ;
  - KPI du monde (prompt 4).

Commandes du protocole : voir [docs/api.md](docs/api.md) §2. Ajouts du prompt 6 :

- `add_swarm` ; route HTTP `POST /api/swarms` ;
- états et informations de vol dans `list_entities` ;
- événements `flight_started`, `arrived`, `arrival_failed` et `swarm_exposed` ;
- `apply_decision` renvoie `result: "flying"`.

## Résultats

**Test préalable sur Mac (M4 Pro, 24 Go)** : le modèle se charge et répond.

| Appareil | Chargement depuis le cache | Requête courte | Requête du projet | Mémoire |
|---|---|---|---|---|
| MPS | 2,5 s | ~97 ms | ~550 ms | 7,7 Go GPU (float32) |
| Processeur | 1,2 s | ~295 ms | non mesuré | ~10,6 Go RAM |

Le premier téléchargement (3,2 Go) a pris environ 6 minutes. La configuration Windows + NVIDIA **n'a pas été testée**.

**Comparaison avec la logique de référence** (75 scénarios fixes : 5 espèces × 5 profils × 3 jeux d'habitats ;
[rapport](docs/rapport_comparaison.md)) :

- **56 % d'accord** sur la décision finale, dont **60 % pour les essaims** ;
- **77 %** sur le meilleur habitat, en ignorant le seuil d'acceptation.

Pour les essaims, OpenJev reçoit en plus le délai et la distance, que la référence ignore : le rapport le signale.
Le désaccord porte surtout sur « assez bon pour s'installer » autour du seuil. Trois formulations ont été essayées
avant les essaims (41 %, 51 %, puis 53 % pour celle retenue). **Conclusion : la logique de référence ne peut pas
encore être supprimée.**

**Démonstration (prompt 6)** avec le vrai modèle, sur Mac, à vitesse ×4 :

- un essaim, 5 abeilles solitaires et 6 habitats ;
- tous ont choisi, volé puis se sont installés à l'arrivée, sans échec ;
- en moyenne 1,15 jour simulé pour trouver un habitat, et 24 h simulées de vol (`FLIGHT_SPEED_FACTOR` = 0,05).

## Utilisation

```sh
./decision/start.sh                     # 1. OpenJev (Windows : .\decision\start.ps1 ; 1er lancement : installe + télécharge)
./godot/start.sh                        # 2. fenêtre Godot (Windows : .\godot\start.ps1)
docker compose up -d                    # 3. backend + tableau de bord, puis http://localhost:8000
# sans Docker : cd backend && ../.venv/bin/python -m bzz.server
cd backend && ../.venv/bin/python -m bzz.decision.compare      # régénère le rapport de comparaison (service requis)
../.venv/bin/python -m unittest discover tests                 # 48 tests ; le test du vrai modèle n'est lancé que si le service répond
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
- **Déplacement dans Godot** : `WorldApi.step()` fait avancer les vols (`Flight`) et les délais d'essaim à chaque tick
  de simulation, donc la pause et la vitesse s'appliquent sans code spécifique.
- **Deux échelles de temps** :
  - `DAY_TICKS` fixe la longueur d'une journée (délais d'essaim, temps moyens) ;
  - `FLIGHT_SPEED_FACTOR` ralentit tous les vols de la même façon pour qu'ils restent visibles (sinon un vol réel de
    quelques minutes durerait une fraction de seconde à l'écran). Les vitesses relatives entre espèces restent celles
    du catalogue.
- **États calculés, pas stockés** : un état se déduit de `home`, `flight`, `exposed` et des habitats existants, ce qui
  évite les incohérences.
- **La reine est un nœud enfant de l'essaim** : elle se déplace avec lui. `QueenBehavior.move_to_habitat` lance le vol
  de l'essaim (première implémentation réelle d'une action de rôle).
- **Le délai d'essaim ne s'écoule qu'en grappe**, ni pendant le vol ni après l'installation.
- **Positions vers le navigateur** : une capture au plus toutes les `DASHBOARD_UPDATE_INTERVAL` secondes (0,25),
  interpolées côté navigateur pour un mouvement fluide.
- Hérité : TCP JSON en requête/réponse, relevé des événements avec curseur, verrou sur la connexion, validation
  double, noms lisibles générés, configuration par variables d'environnement, entités en GDScript.

## Problèmes connus / limites

- **Mode fenêtre testé sur Mac seulement** (Docker Desktop atteint bien Godot sur `127.0.0.1` via
  `host.docker.internal`). Sous Windows, ce n'est pas testé : si la connexion échoue, il faut
  `GODOT_LISTEN=0.0.0.0`, qui rend Godot joignable depuis le réseau local (à restreindre dans le pare-feu).
- **Affichage vérifié sans capture d'écran automatisée** :
  - les tests contrôlent les éléments dessinés (`build_items`) ;
  - l'aspect visuel a été vérifié à la main avec `godot/tests/render_view.gd` ;
  - le terminal n'a pas l'autorisation de capturer l'écran du Mac.
- **Godot doit être installé sur la machine**, dans la version de l'image Docker (4.7.2) ; les scripts refusent une
  autre version.
- **Fermer la fenêtre perd le monde** (pas de sauvegarde).
- **Mode local** (Python lance Godot) : si Godot s'arrête, il n'est pas relancé automatiquement ; utiliser `restart`.
- **Accord avec la référence de 56 %** seulement : le modèle juge mal le seuil d'acceptation.
- **Vols simplifiés** : ligne droite, sans obstacle ni recherche de chemin. La vitesse absolue est un réglage de jeu,
  et seule la vitesse de l'ouvrière mellifère est bien sourcée. Les durées de vol ne sont pas réalistes par rapport à
  la journée.
- **Essaim simplifié** : une décision unique par intervalle, sans éclaireuses, danse ni quorum. La personnalité
  collective est une invention de jeu. Les essaims se posent à la main (pas d'essaimage depuis une ruche existante).
- **Abeille en attente** : son état « en attente » se recalcule à chaque capture. Elle ne redemande une décision que
  lorsqu'un habitat compatible apparaît, ou se libère quand une entité est retirée.
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
- Décision collective réelle des essaims : éclaireuses qui explorent (`explore_habitats`, `visit_habitat`), danse,
  quorum, produisant la `ColonyDecision` déjà utilisée par la reine.
- Essaimage depuis une ruche existante (une colonie installée produit un essaim), obstacles et recherche de chemin.
- Reproduction (`lay_eggs`, `manage_reproduction_cycle`).
- Sauvegarde et chargement d'un monde, pour survivre à la fermeture de la fenêtre ; authentification si le tableau
  de bord doit être exposé.
- Valider le mode fenêtre sous Windows ; illustrations plus riches dans la vue (sprites dessinés), sans dépendre
  d'actifs sous licence.
