# Décision : des abeilles pilotées par des LLM

Résumé de la discussion du 27 octobre 2026 : pourquoi des agents LLM, les problèmes et leurs solutions,
comment les abeilles interagissent, un scénario complet et ce qu'il manque pour passer à la pratique.

> **Sujet retenu.** *Est-ce que des agents LLM arrivent à prendre une décision collective comme un vrai essaim ?*

---

### 1. Point de départ

- Les abeilles ont un **rôle** (éclaireuse `SCOUT` ou suiveuse `FOLLOWER`), une **personnalité** (4 traits) et
  des **actions** déclarées mais vides : elles sont sans cerveau.
- Tout le modèle est résumé dans [bzz_complet.pdf](bzz_complet.pdf) (rôles, habitats, caractéristiques, personnalité).
- **Question posée :** faut-il des règles simples (formules) ou des agents LLM qui décident ?

### 2. Pourquoi des agents LLM

Une simulation à règles est rapide, testable et réglable. Mais elle répond à une autre question : « est-ce
qu'on reproduit l'essaim ». Avec les LLM, la question devient : **« est-ce que des LLM, chacun avec sa
personnalité, arrivent ensemble au bon choix ? »**. C'est un vrai sujet d'expérience. Les LLM *sont*
l'expérience, ce n'est pas un détail d'implémentation.

LangGraph a été évoqué. Il organise des appels LLM, mais il ne rend pas la simulation plus rapide : chaque
étape qui « réfléchit » reste un appel LLM. On pourra l'utiliser comme outil, mais il ne règle aucun des
problèmes ci-dessous.

### 3. Les trois problèmes et leurs solutions

| Problème | Solution retenue | Point d'attention |
|---|---|---|
| **Lenteur** : beaucoup d'appels LLM | petits modèles (1–3B) ; la LLM n'est appelée qu'aux **moments de décision** ; **la simulation attend les abeilles** (le temps simulé est découplé du temps réel) | un run prend plus de temps, mais la simulation reste correcte |
| **Non reproductible** | **température ~0,7 + une seed fixe par abeille** (et une « seed de run » pour varier les runs) | à température 0, des abeilles de même personnalité deviennent des clones : plus de décision collective. Il faut garder le même modèle et la même machine |
| **Calculs sur des chiffres** | les abeilles perçoivent des **adjectifs sur 5 niveaux** ; **les chiffres restent stockés** | moins de nuance (deux sites « large » se valent) ; les chiffres servent à mesurer le résultat |

**Reproductible et varié.** *Reproductible* : relancer le même run donne exactement le même résultat.
*Varié* : dans un même run, les abeilles ne pensent pas toutes pareil. La seed par abeille donne les deux.
C'est comme si chaque abeille avait son propre paquet de cartes, mélangé différemment, et qu'on rejouait
toujours les mêmes paquets.

### 4. Adjectifs : ce qui est fait

C'est implémenté : `HabitatCatalog.LEVELS` et `HabitatCatalog.describe()`. `get_entity` renvoie
maintenant `features` (les chiffres) **et** `description` (les mots). Le détail est dans [bzz_complet.pdf](bzz_complet.pdf).

- Les mots sont en **anglais**, parce que les petits modèles le comprennent mieux. On peut les changer dans `LEVELS`.
- Un volume ou une entrée à 0 devient `no cavity` / `no entrance` (« sans objet »).
- La capacité n'est pas décrite : ce n'est pas un critère que l'abeille juge.
- Exemple de cavité d'arbre : *large cavity, wide entrance, high, partly sunny, moderately humid, many flowers, safe, no old nest*.

### 5. Comment les abeilles interagissent

**Le prompt, c'est ce que l'abeille perçoit et pense. L'action, c'est ce qu'elle fait.** La LLM ne touche
jamais le monde directement : elle choisit une action, et Godot l'exécute.

```
Monde (Godot) → perception en texte → prompt → LLM → action (JSON) → Godot exécute → le monde change
```

- **Abeille ↔ habitat :** l'habitat est passif. Godot place `describe(habitat)` et la personnalité dans le
  prompt, puis la LLM rend un jugement. Une même description donne des notes différentes selon la personnalité.
- **Abeille ↔ abeille :** pas de chat, **uniquement la danse**. L'éclaireuse fait `dance(site, force)`,
  Godot diffuse la danse sur l'essaim, et les suiveuses proches la voient dans leur prompt. Des messages en
  texte libre feraient négocier les abeilles comme des humains. Ça pourra servir de variante à comparer, pas de version de base.

| Action | Qui décide | Qui exécute |
|---|---|---|
| `explore()` | Godot (au hasard) | Godot |
| `evaluate(habitat)` | **LLM** | — |
| `go_back()` | Godot | Godot |
| `dance()` | **LLM** (danser ? avec quelle force ?) | Godot (diffusion) |
| `evaluation_signal_danse()` | **LLM** (je suis cette danse ?) | — |
| `visit_habitat()` | Godot | Godot |
| `stay()` / `go_back_to_branch()` | **LLM** (je reste ou je repars ?) | Godot |
| Quorum, départ de l'essaim | **Godot uniquement** | Godot |

La LLM intervient à **3 moments** : juger un site, juger une danse, rester ou repartir. Le quorum n'est
jamais décidé par une LLM : sinon la décision n'est plus collective.

### 6. Scénario de test sur papier

**Décor.** 3 sites : **A** cavité d'arbre (sûre, en hauteur : le meilleur), **B** ruche dangereuse,
**C** terrier minuscule. 2 éclaireuses (S1 audacieuse, S2 prudente), 3 suiveuses (F1 prudente,
F2 audacieuse, F3 sociable). Quorum = 3.

| Tick | Étape | Ce qui se passe |
|---|---|---|
| 1 | `explore` | S1 trouve B ; S2 trouve C puis A |
| 2 | `evaluate` | S1 donne 4 à B (« le danger ne me fait pas peur ») ; S2 donne 1 à C et 5 à A |
| 3 | `go_back` | les éclaireuses rentrent sur la branche |
| 4 | `dance` | S1 danse pour B (force 3), S2 pour A (force 5) ; C n'a pas de danse |
| 5 | `evaluation_signal_danse` | F1 suit B ; F2 et F3 suivent A |
| 6 | `visit_habitat` | chaque suiveuse va voir le site |
| 7 | `evaluate`, `stay` / `go_back_to_branch` | F1 juge B dangereux et rentre ; F2 et F3 restent à A |
| 8 | retour de F1 | S1 danse plus faiblement pour B ; F1 suit A et reste |
| 9 | quorum | 3 abeilles à A : l'essaim part vers A |

**Résultat :** l'essaim choisit A, même si S1 poussait pour B, parce que F1 a jugé par elle-même. Toutes
les actions ont été appelées. Les réponses de la LLM sont celles qu'on *espère* : c'est exactement ce que
l'expérience doit mesurer.

### 7. Pièces manquantes révélées par le scénario

1. **Les suiveuses doivent pouvoir danser.** Une recrue qui approuve un site retourne sur la branche et
   devient éclaireuse (`set_role(SCOUT)`). C'est ce qui crée l'effet boule de neige vers le meilleur site.
2. **Un objet « Danse » dans le monde** : site, direction, force, danseuse. Il est visible par les abeilles proches.
3. **Un compteur de quorum** dans Godot : le nombre d'abeilles présentes en même temps sur chaque site.
4. **La plomberie** : la construction des prompts (perception → texte), le client LLM, le format de réponse JSON.

### 8. Protocole d'expérience proposé

Sur le modèle de l'expérience de Seeley (5 nichoirs, 1 bon et 4 moyens) :

- 5 habitats, dont 1 meilleur que les autres d'après les chiffres ;
- 3 versions de l'essaim : **LLM**, **règles simples**, **hasard** (la référence la plus basse) ;
- 20 runs par version, chacun avec sa propre seed ;
- les mesures : % de choix du meilleur site, temps de décision, essaim qui se divise ou non ;
- le bonus : plusieurs tailles de modèle (1B, 3B, 8B), pour voir à partir de quelle taille l'essaim devient « intelligent ».

### 9. Prochaines étapes

Le passage à la pratique se fera étape par étape, selon les priorités qui seront données. Les pistes sont
dans l'ordre logique : les 3 prompts et leur format JSON, le client LLM, l'objet Danse, le quorum, puis le
protocole d'expérience.
