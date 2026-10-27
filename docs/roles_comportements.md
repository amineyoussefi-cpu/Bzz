# Rôles et comportements des abeilles

Document de conception des **rôles** (éclaireuse, suiveuse, reine) que chaque abeille peut tenir.
Il complète la [référence abeilles et habitats](reference_abeilles.md).

> **État actuel.** Les rôles existent dans [`godot/entities/roles/`](../godot/entities/roles/).
> Des abeilles (avec leur rôle) et des habitats peuvent être placés dans le monde depuis le tableau de bord.
> **Les abeilles sont sans cerveau** : les rôles sont déclarés mais aucune action n'est implémentée.

Comme dans la référence, on distingue :

- 🔬 **Biologie** : comportement réel, sourcé ;
- 🎮 **Simulation** : ce que le logiciel prévoit, et les simplifications.

---

## 1. Les trois rôles

| | Rôle | `BeeRole.Id` | Mission |
|---|---|---|---|
| <img src="img/role_eclaireuse.svg" width="150"> | Éclaireuse | `SCOUT` | chercher des habitats, les évaluer, les signaler par une danse |
| <img src="img/role_suiveuse.svg" width="150"> | Suiveuse | `FOLLOWER` | observer les danses, décider d'aller voir, juger l'habitat elle-même |

🔬 **Biologie.** Ce découpage vient de l'essaimage de l'abeille mellifère. Lorsqu'un essaim quitte la colonie,
seule une petite partie des ouvrières part en exploration : ce sont les **éclaireuses**. De retour sur l'essaim,
elles annoncent les sites trouvés par une **danse frétillante**. D'autres abeilles suivent ces danses, vont
**inspecter le site elles-mêmes** et, si elles l'approuvent, dansent à leur tour pour lui. Lorsqu'un
**nombre suffisant d'éclaireuses** (un *quorum*) se trouve en même temps sur un même site, l'essaim se prépare
au départ (signaux de « piping ») puis s'envole vers ce site ([Seeley & Visscher 2004][quorum];
[Visscher & Seeley 2007][visscher2007]). **La reine ne participe pas au choix** : elle accompagne l'essaim.

🎮 **Simulation.** Les rôles sont **indépendants des espèces** : les cinq espèces du catalogue peuvent recevoir les
deux rôles. Une abeille a **un rôle à la fois**, `FOLLOWER` par défaut, et peut en changer (`set_role`).
*Simplification assumée* : chez les bourdons et les abeilles solitaires, il n'y a ni danse ni décision
collective ; ces espèces pourront simplement ne pas utiliser le rôle éclaireuse.

---

## 2. Éclaireuse — `SCOUT`

<img src="img/role_eclaireuse.svg" width="240" align="right">

🔬 **Biologie.** L'éclaireuse inspecte une cavité (volume, entrée, hauteur…) puis revient danser. La **force de sa
danse** (nombre de circuits frétillants) **augmente avec la qualité du site** ([Seeley & Buhrman 2001][buhrman];
[J. Exp. Biol. 2008][jeb2008]). Avec le temps, elle danse de moins en moins pour ce site puis s'arrête
(« attrition »), ce qui permet aux bons sites, soutenus par de nouvelles recrues, de l'emporter. Les abeilles
peuvent aussi émettre un **signal stop** (coup de tête) contre les danseuses d'un site concurrent.

🎮 **Simulation** — classe `ScoutBehavior` : rôle déclaré, aucune action implémentée.

À implémenter : exploration des habitats disponibles, évaluation, mémorisation, retour à la colonie, danse.

<img src="img/danse_fretillante.svg" width="300">

---

## 3. Suiveuse — `FOLLOWER`

<img src="img/role_suiveuse.svg" width="240" align="right">

🔬 **Biologie.** Une abeille recrutée par une danse ne copie pas l'avis de la danseuse : elle **va inspecter le
site elle-même** et ne danse pour lui que si elle le juge bon. Ce contrôle indépendant est une raison pour
laquelle l'essaim choisit le plus souvent le meilleur site disponible ([Seeley 2010][seeley2010]).

🎮 **Simulation** — classe `FollowerBehavior` : rôle déclaré, aucune action implémentée.

À implémenter : réception d'une danse, évaluation du signal, décision de suivre, visite de l'habitat, jugement indépendant.

---

## 4. Architecture

<img src="img/classes_roles.svg" width="100%">

Règles retenues :

- **Rôles sans restriction d'espèce** : `BeeRole` ne connaît pas `BeeSpecies`.
- **Composition** : le rôle est un composant (`bee.behavior`) qu'on remplace, pas une sous-classe de `Bee` ;
  une abeille peut donc changer de rôle sans être recréée.
- `BeeBehavior` est une **classe abstraite** (`@abstract`, Godot ≥ 4.5) : chaque rôle doit déclarer `role()` et `actions()`.

| Élément | Responsabilité | Où |
|---|---|---|
| `BeeSpecies` | espèces et types d'habitats acceptés | `entities/bee_species.gd` |
| `BeePersonality` | traits individuels | `entities/bee_personality.gd` |
| `BeeRole` | deux rôles (`SCOUT`, `FOLLOWER`), création du composant | `entities/roles/bee_role.gd` |
| `ScoutBehavior`, `FollowerBehavior` | actions de chaque rôle | `entities/roles/*_behavior.gd` |
| `Bee` | porte espèce, personnalité et rôle | `entities/bee.gd` |
| Évaluation des habitats | **à créer** | — |
| Décision collective | **à créer** | — |

---

## Sources

- Seeley, T. D. & Visscher, P. K. (2004). *Quorum sensing during nest-site selection by honeybee swarms*. Behavioral Ecology and Sociobiology 56, 594–601. [doi:10.1007/s00265-003-0664-6][quorum]
- Visscher, P. K. & Seeley, T. D. (2007). *Coordinating a group departure: who produces the piping signals on honeybee swarms?* [PDF][visscher2007]
- Seeley, T. D. & Buhrman, S. C. (2001). *Nest-site selection in honey bees: how well do swarms implement the "best-of-N" decision rule?* [PDF][buhrman]
- *Sensory coding of nest site value in honeybee swarms*, Journal of Experimental Biology 211 (2008). [lien][jeb2008]
- Seeley, T. D. (2010). *Honeybee Democracy*. Princeton University Press. (présentation : [Science Friday][seeley2010])

[quorum]: https://www.doi.org/10.1007/S00265-003-0664-6
[visscher2007]: https://www.shoalsmarinelaboratory.org/sites/default/files/media/2026-02/Visscher%26Seeley%202007_SML136.pdf
[buhrman]: https://www.shoalsmarinelaboratory.org/sites/default/files/media/2026-02/Seeley%26Buhrman%202001_SML105.pdf
[jeb2008]: https://cob.silverchair.com/jeb/article/211/23/3691/17956/Sensory-coding-of-nest-site-value-in-honeybee
[seeley2010]: https://www.sciencefriday.com/articles/how-do-bees-find-a-home/
