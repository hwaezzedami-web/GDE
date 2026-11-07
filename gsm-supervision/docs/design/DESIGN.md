# Direction artistique : Supervision GSM Algérie

## Le sujet, le public, le travail principal

- **Sujet** : supervision de sites radio 2G/3G/4G/5G sur tout le territoire (69 wilayas).
- **Public** : ingénieurs réseau et superviseurs d'un centre de supervision. Ils regardent l'écran
  longtemps, parfois de nuit, et doivent agir vite.
- **Travail principal** : voir *où* il y a une panne maintenant, et savoir *si l'information est fiable*.

## Le point de départ : la règle qui guide tout le design

Le cahier des charges impose qu'une collecte en échec donne **INCONNU**, jamais **DOWN**. Une interface
générique afficherait l'inconnu en gris, comme un état neutre. Ici, c'est une information différente :
« je ne sais pas » n'est pas « c'est en panne ». Le design doit donc rendre cette différence visible,
sans compter sur la couleur seule.

## Concept : le pylône dit son état

Chaque site est un pylône sur la carte. Sa **forme** porte l'état, la couleur n'en est que le renfort :

| État | Pylône | Lecture |
|---|---|---|
| UP | corps plein, deux ondes | stable |
| DÉGRADÉ | corps plein, une seule onde | partiellement opérationnel |
| DOWN | corps barré, sans ondes | hors service |
| INCONNU | corps en traits pointillés | données manquantes, pas une panne |
| NON SUPERVISÉ | simple point, creux | aucun OMC ne remonte ce site |

C'est l'élément mémorable de l'interface : un superviseur qui distingue une panne d'un doute en un
coup d'œil, même en daltonisme ou sur un écran médiocre.

## Tokens

### Couleurs (6 valeurs de base, claires ; sombres dans `tokens.css`)

| Nom | Hex | Rôle |
|---|---|---|
| Fond | `#EEF1F4` | gris bleuté froid, pas crème |
| Surface | `#FFFFFF` | panneaux, tableaux |
| Encre | `#17202A` | texte principal |
| Encre atténuée | `#556272` | libellés secondaires |
| Trait | `#D3DAE3` | séparations, bordures de surface |
| Accent | `#1F5FBF` | sélection, action principale, focus |

Couleurs d'état (chacune avec un fond teinté pour les badges) : UP `#1C7C54`, DÉGRADÉ `#A65F00`,
DOWN `#B42318`, INCONNU `#5E4B8B`, NON SUPERVISÉ `#6B7685`. Tous les textes respectent un contraste
d'au moins 4,5:1 sur leur fond.

### Typographie

- **Une seule famille** : *Atkinson Hyperlegible Next*, conçue pour la lisibilité (chiffres et lettres
  difficiles à confondre). Elle sert aux titres, au texte et aux données.
- **Chiffres tabulaires** (`font-variant-numeric: tabular-nums`) partout où il y a des compteurs : les
  colonnes de chiffres restent alignées quand ils changent.
- **Arabe** (noms de wilayas) : repli sur *Noto Naskh Arabic*, car la famille latine n'en contient pas.
- **Échelle** : base 14 px, rapport 1,2 ; 14 / 17 / 20 / 24 / 29 px.
- Pas de majuscules pour les libellés, pas de police monospace, pas de mot mis en italique dans un titre.

### Espacement et rayons

- Grille de 4 px. Rayon **3 px** pour les contrôles, **8 px** pour les panneaux. Rien d'autre.
- Une seule ombre, réservée au panneau de détail qui flotte au-dessus de la carte.

## Mise en page

Concept : **la carte est le héros**, plein écran. Une bande de statuts en haut donne les compteurs ; un
panneau latéral s'ouvre au clic sur un site. Alignement à gauche pour le texte, à droite pour les
nombres dans les tableaux.

```
+--------------------------------------------------------------------------+
| Supervision GSM · Algérie          [Rechercher un site…]   Dernière mise à jour 14:32 |
+--------------------------------------------------------------------------+
| 1 284 stables | 37 dégradés | 12 hors service | 9 inconnus | 214 non supervisés |
+----------+---------------------------------------------------+-----------+
| Carte    |                                                   | Site      |
| Sites    |        ^      ^                                   | 160001    |
| Tableau  |       /|\    /|\          ^                       | Alger     |
| Alarmes  |        |      |          /|\                      | ● Hors    |
| Dashbord |                                                   |   service |
| Admin    |   ^ (inconnu)          ·  (non supervisé)          | …         |
|          |                                                   |           |
+----------+---------------------------------------------------+-----------+
| Légende : pylône stable, dégradé, hors service, inconnu, non supervisé   |
+--------------------------------------------------------------------------+
```

- **Navigation** : rail étroit avec icône et libellé, jamais un menu « hamburger » caché.
- **Mobile** : la bande de statuts devient une ligne défilante, le panneau de détail passe en feuille
  pleine hauteur, le rail devient une barre en bas.

## Mouvement

- **Un seul moment orchestré** : à l'ouverture de l'application, les pylônes apparaissent par zone.
- **Réponse à une action** : le panneau de détail glisse à l'ouverture, pour montrer ce qui a changé.
- **Changement d'état** : un pylône qui passe en DOWN clignote une fois (et seulement une fois).
- `prefers-reduced-motion` supprime tout le mouvement, sans perte d'information.

## Rédaction (français, phrases à la casse de phrase)

- Les actions gardent leur nom dans tout le parcours : « Acquitter », puis « Alarme acquittée ».
- Une erreur explique ce qui s'est passé et quoi faire : « Collecte Huawei en échec depuis 12 min. Les
  sites de cette source sont affichés en inconnu jusqu'au retour de la collecte. » Bouton : « Relancer
  la collecte ».
- Un état vide invite à agir : « Aucun site ne correspond. Élargissez la wilaya ou retirez le filtre. »

## Revue contre le brief

Le plan a été comparé aux défauts courants des interfaces générées. Modifications apportées :

1. **Fond crème et accent terracotta** : écarté. Le fond est gris bleuté, car un centre de supervision se
   regarde à la lumière froide des écrans.
2. **Fond presque noir et accent vert fluo** : écarté. Le vert et le rouge servent déjà les états ; un
   accent fluo brouillerait ces signaux.
3. **Cartes SaaS identiques** : écarté. Les blocs ont des fonctions différentes (bande, carte, panneau),
   donc des formes et des poids différents.
4. **Étiquettes en majuscules, séparateurs « · », flèches « → »** : écarté. Rien de cela ne porte
   d'information ici.
5. **Dégradé décoratif et numérotation 01 / 02 / 03** : écartés. La numérotation n'a de sens que pour une
   séquence réelle.
6. **Gris pour l'inconnu** : remplacé par un violet pointillé. Un gris « neutre » ferait croire à une
   information absente sans signal d'alerte, ce qui est exactement le risque à éviter.

## Qualité minimale

- Focus clavier visible sur chaque contrôle (anneau de 2 px, couleur d'accent).
- Aucun état n'est transmis par la couleur seule : chaque état a une forme et un libellé.
- Responsive jusqu'à 360 px, sans défilement horizontal de la page.
- Mode sombre prévu dès les tokens (`prefers-color-scheme` et `data-theme`).
