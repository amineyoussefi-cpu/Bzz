# Plan : carte infinie et menu en bas

Inspiré de *Civilization* : la carte prend tout l'écran, on s'y déplace librement, et le dashboard tient dans
une barre en bas.

## Ce qui change

1. **Carte plein écran.** En haut, une barre fine garde le nom, l'état et les boutons Lancer/Pause et vitesse.
2. **Caméra :**
    - glisser le sol pour se déplacer ;
    - molette ou pinch pour zoomer ;
    - bouton « Recentrer » pour revenir sur l'essaim ;
    - glisser une abeille ou un habitat le déplace, comme avant.
3. **Map infinie à l'écran :**
    - le décor (herbe, fleurs, buissons) est généré par morceaux autour de la caméra, toujours le même au même endroit ;
    - les abeilles et les habitats restent dans la zone de jeu de Godot, marquée au sol.
4. **Menu en bas :**
    - un bouton par élément : Composer, Décisions, Modèle, Éléments, Journal, Légende ;
    - un seul panneau ouvert à la fois, qui se replie en recliquant ou avec Échap ;
    - la relecture reste toujours visible dans la barre ;
    - la fiche d'une abeille ou d'un habitat reste flottante à droite.

## Ce qui ne change pas

- Godot, le backend et l'API.
- Le contenu des panneaux.

## Vérification

- Navigateur : déplacement, zoom, sélection, glisser-déposer, chaque panneau, relecture, mode pas à pas, aucune erreur.
- Les tests Python passent toujours.

**Hors périmètre :** mini-carte, grille hexagonale, brouillard de guerre, monde sans bord dans Godot.
