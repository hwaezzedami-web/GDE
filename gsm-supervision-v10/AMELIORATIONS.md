# Améliorations de l'interface (version 10)

Base : `gsm-supervision_10.zip`. Le backend n'a pas été modifié : ses 63 tests passent (1 ignoré).

## Modifications

1. **Inconnu distinct du neutre** : la couleur de l'état INCONNU passe du gris à un violet
   (`#6b4fbb`). Les grappes de la carte, les filtres, la légende et les compteurs suivent ce changement.
   Motif : une perte de collecte ne doit pas se lire comme une absence d'information anodine.
2. **Pylône inconnu en pointillés** : le contour du pylône est tracé en pointillés, pour que la forme
   aussi distingue l'inconnu (et ne dépende pas de la seule couleur).
3. **Non supervisé plus visible** : la couleur du marqueur creux passe de `#b8c0cc` à `#9aa3b2`.
4. **Police embarquée** : Atkinson Hyperlegible Next (lisibilité des chiffres) via `@fontsource`.
   Elle est incluse dans le build, donc l'interface reste utilisable hors ligne.
5. **Compteurs** : les pourcentages ne se coupent plus en deux lignes. Sur téléphone, les compteurs
   tiennent sur deux colonnes.
6. **Navigation mobile** : la barre défile horizontalement avec un fondu à droite, pour signaler
   qu'il reste des onglets à voir.

## Vérifications

- `npm run build` : OK.
- Captures bureau (1440 px) et téléphone (390 px) de la page Carte : aucun débordement horizontal,
  aucune erreur dans la console du navigateur.

## Non vérifié (à revoir)

- Pages Tableau de bord, Alarmes, Référentiel et Administration : non captées pendant cette passe.
- Pylône inconnu en pointillés : vérifié dans le code, pas à fort zoom sur un site réel.
- Le taux de passage de la fiche site sur téléphone (panneau en bas) n'a pas été recontrôlé.
- La taille du bundle JavaScript (≈ 880 Ko) reste élevée ; un découpage par page serait à étudier.

## Deuxième passe : finition et mouvement

Ajouts (tous désactivés si l'utilisateur demande moins d'animations) :

- **Entrée de page** : fondu et léger glissement à chaque changement de page.
- **Tableau de bord** : les cartes apparaissent l'une après l'autre, en une seule séquence à l'ouverture.
- **Compteurs** : les chiffres s'incrémentent en douceur quand leur valeur change ; le texte final est exact.
- **Chargement** : un reflet parcourt les blocs en attente, au lieu d'un vide.
- **Boutons et compteurs** : retour visuel au clic (léger tassement), focus clavier plus net.
- **Navigation** : le soulignement de l'onglet actif glisse en douceur.
- **Panneau de détail** : glisse depuis la droite (ou monte depuis le bas sur téléphone).
- **Tableaux** : survol discret des lignes.
- **Titres de section** : passés en casse de phrase (plus de MAJUSCULES), plus lisibles.

Accessibilité : `prefers-reduced-motion` supprime toutes les animations ; aucune information n'est
transmise par le seul mouvement.

Vérifié : pages Carte, Tableau de bord, Alarmes, Référentiel, Administration (bureau et téléphone),
aucune erreur console, hauteur de la carte inchangée.

Limites connues :
- La page Administration affiche les statuts en texte brut (« SUCCESS »), alors que les autres pages
  utilisent des badges : à harmoniser.
- Les graphiques du tableau de bord gardent les couleurs d'état ; une palette dédiée serait plus élégante.
