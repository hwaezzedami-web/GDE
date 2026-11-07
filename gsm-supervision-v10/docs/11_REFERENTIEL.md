# Référentiel des sites et rapprochement avec les OMC

Le référentiel est la **liste officielle des sites de l'opérateur** (code, nom, position GPS, wilaya,
direction régionale, cycle de vie, technologies). Il est importé depuis un fichier et mis à jour aussi
souvent que nécessaire. Il sert à trois choses :

1. afficher **tous** les sites sur la carte, y compris ceux qu'aucun OMC ne remonte encore ;
2. faire foi pour le nom, la position et la localisation des sites (les OMC n'ont souvent ni coordonnées
   ni nom fiable) ;
3. **détecter les écarts** entre le référentiel et ce que remontent réellement les OMC.

Menu **Référentiel** (tous les utilisateurs en lecture ; import et paramètres : administrateur ;
prise en compte des anomalies : superviseur).

## 1. Formats acceptés

| Format | Lecture |
|---|---|
| **KMZ / KML** (Google Earth) | un repère (Placemark) = un site ; position = coordonnées du point ; attributs lus dans `ExtendedData` et dans le tableau HTML de la description (`<tr><th>Champ</th><td>Valeur</td></tr>`). Le texte hors tableau (pied de page, mentions) est ignoré. |
| **Excel .xlsx** | feuille la plus remplie (ou feuille choisie) ; la ligne d'en-tête est détectée même si un titre la précède. `.xls` (97-2003) : réenregistrer en `.xlsx`. |
| **CSV** | séparateur `;` `,` tabulation ou `|` détecté ; UTF-8, Windows-1252 ou Latin-1 ; lignes `#` ignorées. |
| **GeoJSON** | `FeatureCollection` de points ; propriétés = colonnes. |

Taille maximale 50 Mo. Sécurité : XML lu sans DTD ni entités externes (defusedxml), taille décompressée
des KMZ plafonnée, formules Excel lues en valeur, aucune exécution de contenu.

Un **modèle Excel** (lignes fictives) est téléchargeable depuis *Référentiel → Synthèse*.

## 2. Correspondance des colonnes

Reconnue automatiquement (sans accents ni casse), modifiable dans l'assistant :

| Champ | Exemples d'en-têtes reconnus | |
|---|---|---|
| Code site | `Code site`, `Site ID`, `code_site`, `Code` | obligatoire |
| Latitude / longitude | position du repère KML/GeoJSON, sinon `Latitude`/`Lat`, `Longitude`/`Lon`/`Long` | obligatoires |
| Nom | `Nom du site`, `Site name`, `Nom` | |
| Wilaya | `Wilaya` (nom, chef-lieu, numéro 1-69, « Alger Centre/Est/Ouest »…) | |
| Commune, adresse | `Commune`, `Adresse` | |
| Direction régionale | `Region`, `DR`, `Direction régionale` | |
| Cycle de vie | `Etape cycle de vie`, `Statut site`, `Lifecycle` | |
| Technologies | `Technologies radio` (`2G/3G/4G`, `GSM`, `UMTS`, `LTE`, `NR`…) | |

Toutes les autres colonnes sont **conservées** et affichées dans la fiche du site (« Référentiel des sites »).

Contrôles et corrections à la lecture :

- codes vides, trop longs ou en double : ligne rejetée (motif et numéro de ligne affichés) ;
- coordonnées décimales (`36,75` ou `36.75`) ou degrés-minutes-secondes (`36°45'09"N`) ;
- latitude et longitude **inversées** : corrigées automatiquement et signalées ;
- coordonnées hors d'Algérie ou illisibles : ligne rejetée ;
- valeurs vides du type `---`, `???`, `N/A`, `nan` traitées comme absentes ;
- **zéros de tête perdus par Excel** (`5474` au lieu de `05474`) : avertissement, et option
  « compléter les codes numériques à N chiffres ».

## 3. Import : prévisualisation puis application

L'assistant (*Référentiel → Importer*) ne modifie rien avant la confirmation :

1. **Analyse** du fichier : format, colonnes, correspondance proposée, aperçu des 20 premières lignes ;
2. **Différentiel** avec la base : nouveaux sites, sites modifiés (déplacés de plus de 30 m, nom, cycle
   de vie, DR, wilaya, commune, technologies), inchangés, retirés (mode synchronisation), lignes rejetées,
   corrections automatiques ;
3. **Application** (le fichier doit être identique à celui analysé : empreinte SHA-256 vérifiée).

Deux modes :

| Mode | Effet |
|---|---|
| **Mise à jour** (défaut) | ajoute les nouveaux sites et met à jour ceux du fichier ; aucun site n'est retiré. Adapté aux fichiers partiels (une DR, une wilaya). |
| **Synchronisation complète** | idem, et les sites du référentiel **absents du fichier en sortent**. Ils ne sont pas supprimés : un site encore remonté par un OMC reste visible et devient une anomalie « site inconnu du référentiel ». |

**Garde-fou** : une synchronisation qui retirerait plus de `max_removal_pct` % des sites (10 % par
défaut) est refusée sans confirmation explicite (fichier tronqué, mauvaise feuille, export filtré…).
Le refus est tracé dans l'historique.

Chaque import est historisé (date, utilisateur, origine, fichier, empreinte, mode, compteurs, messages)
et journalisé dans l'audit (`REFERENCE_IMPORT`).

Autres moyens d'import :

```bash
# Ligne de commande (simulation puis application)
docker compose exec api python -m app.cli reference-import /chemin/sites.kmz --dry-run
docker compose exec api python -m app.cli reference-import /chemin/sites.kmz [--mode sync] [--code-digits 5]
```

**Dossier surveillé** (désactivé par défaut, *Paramètres → Dossier surveillé*) : déposer le fichier
dans `referentiel-depot/` sur le serveur (`REFERENCE_DROP_DIR`, monté en lecture seule dans le service
de collecte). Le fichier le plus récent, inchangé depuis 30 s, est importé une seule fois, avec la
correspondance de colonnes du dernier import réussi du même format. Faire le premier import depuis
l'interface pour valider la correspondance. Le garde-fou s'applique.

## 4. Cycle de vie → catégories

La valeur brute du fichier est conservée et rangée dans une catégorie, **paramétrable**
(*Référentiel → Paramètres*) ; la modification reclasse immédiatement tous les sites.

| Catégorie | Valeurs par défaut | Carte (par défaut) |
|---|---|---|
| En service | `en_air` | affiché |
| Arrêt temporaire | `halte`, `not_on_air` | affiché |
| En projet | `planning`, `acquisition`, `construction`, `implementation`, `construit` | masqué s'il n'est pas supervisé |
| Démonté | `desinstalle`, `vandalise` | masqué s'il n'est pas supervisé |
| Autre | toute valeur non listée | affiché |

> Le sens exact de valeurs comme « halte », « construit » ou « not_on_air » est propre à l'opérateur :
> **table à valider avec l'exploitation**.

Le filtre **Référentiel** de la carte, du tableau de bord et des exports permet d'afficher toutes les
catégories, une seule, ou les sites « hors référentiel » (remontés par un OMC seulement). Le filtre
**Direction régionale** apparaît dès qu'un référentiel contenant des DR est importé.

## 5. Sites « non supervisés »

Un site du référentiel qu'**aucun OMC ne remonte** est affiché :

- en **petit pylône blanc-gris** sur la carte, sans balise d'état ;
- avec l'état **NON SUPERVISÉ**, distinct de **INCONNU** (site supervisé dont les données sont
  périmées ou la collecte interrompue) ;
- dans un compteur à part du bandeau ; il n'entre ni dans les pannes, ni dans la disponibilité, ni dans
  les courbes d'évolution.

Il redevient supervisé dès qu'un OMC le remonte.

## 6. Rapprochement avec les OMC : anomalies

Recalculé après chaque collecte, toutes les 5 minutes (service de collecte), après chaque import, et à
la demande (bouton « Rapprocher maintenant »). Une anomalie se **résout d'elle-même** quand la cause
disparaît (référentiel ou OMC corrigé).

| Anomalie | Condition | Action attendue |
|---|---|---|
| **Site inconnu du référentiel** | un OMC remonte un site absent du référentiel (contrôle actif dès qu'un référentiel est importé) | ajouter le site au référentiel, ou corriger le code dans l'OMC. Un **code proche** du référentiel est suggéré (faute de frappe). |
| **Démonté mais actif** | démonté au référentiel, UP ou DÉGRADÉ dans l'OMC | vérifier : site réactivé, ou erreur de code |
| **En projet mais déjà actif** | en projet au référentiel, déjà en service | mettre à jour le cycle de vie |
| **Supervision perdue** | en service, déjà vu par un OMC, plus remonté depuis `supervision_lost_days` jours (2) | vérifier l'inventaire OMC / le raccordement |
| **Jamais supervisé** | en service, jamais remonté (optionnel : `detect_never_supervised`, à activer quand tous les OMC sont raccordés) | |

Un superviseur peut **prendre en compte** une anomalie (avec commentaire : ticket, action prévue) ; elle
sort du compteur « à traiter » (badge du menu) mais reste listée jusqu'à sa résolution. Export Excel/CSV
disponible (droit d'export).

### Codes avec ou sans zéros de tête

Si un OMC remonte `5474` et que le référentiel contient `05474` (paramètre `match_leading_zeros`, actif
par défaut), les deux sont rapprochés **si la correspondance est unique** : les équipements et alarmes
de l'OMC sont rattachés au site du référentiel. Un site créé par un OMC avant l'import du référentiel
reprend le code du référentiel (son historique est conservé, l'ancien code est noté dans `omc_code`).

### Le référentiel fait foi

Pour un site du référentiel, la collecte OMC ne modifie ni le nom, ni la position, ni la wilaya, ni la
commune, ni l'adresse (le nom remonté par l'OMC est conservé à titre d'information : `omc_name`). Un
inventaire OMC complet qui ne contient plus un site du référentiel ne le fait pas disparaître : il devient
« non supervisé ».

## 7. Wilaya

Par défaut (`wilaya_from = file`), la wilaya est celle **indiquée dans le fichier** (référentiel de
l'opérateur) ; un libellé non reconnu est remplacé par la wilaya déduite des coordonnées. Avec
`wilaya_from = coordinates`, la wilaya est toujours déduite de la position (découpage à 69 wilayas).

La synthèse indique combien de sites ont des coordonnées hors de la wilaya indiquée : cas typique d'un
fichier encore organisé selon l'ancien découpage (58 wilayas), de sites frontaliers, ou d'erreurs de
saisie à corriger dans le référentiel.

## 7 bis. Gestion des sites (onglet « Sites »)

Liste de tous les sites du référentiel avec recherche (code, nom, commune, adresse, code OMC rattaché),
filtres (wilaya, DR, catégorie, supervision, origine import / saisie, avec anomalie), tri par colonne,
pagination et export Excel.

| Action | Droit | Effet |
|---|---|---|
| **+ Nouveau site** | admin | fenêtre de saisie : code, nom, position (saisie ou clic sur la carte, repère déplaçable, sites voisins affichés), wilaya (déduite de la position si vide), commune, adresse, DR, cycle de vie (catégorie affichée en direct), technologies |
| **Modifier** (✎) | admin | mêmes champs, code non modifiable ; les changements sont tracés dans l'audit (avant / après) |
| **Retirer du référentiel** (🗑, ou en lot) | admin | le site sort du référentiel ; s'il est encore remonté par un OMC il reste visible et devient « site inconnu » ; historique conservé |
| **Supprimer définitivement** (en lot) | admin | efface le site et son historique ; refusé pour un site encore remonté par un OMC |
| **Voir sur la carte** (⌖) | tous | ouvre la fiche du site sur la carte |

Chaque site indique son **origine** (« Import » ou « Manuel »), l'auteur et la date de la dernière
modification. Le fichier importé reste la source de référence : un réimport remplace les valeurs saisies
à la main pour les sites qu'il contient, et la prévisualisation l'annonce (« N site(s) modifié(s)
manuellement seront remplacés »). En synchronisation complète, les sites ajoutés à la main et absents
du fichier sont signalés avant application.

## 7 ter. Sites inconnus remontés par les OMC (onglet « Sites inconnus (OMC) »)

Liste des sites que les OMC remontent alors qu'ils sont absents du référentiel, avec l'OMC et
l'équipementier, les technologies, l'état, les alarmes, la position fournie par l'OMC, la date de
détection et **le site le plus proche au référentiel** (code voisin et distance). Filtres : à traiter /
ignorés, recherche, OMC. Pour chaque site :

| Action | Droit | Effet |
|---|---|---|
| **Rattacher à …** | admin | le code OMC désigne un site existant (faute de frappe, ancien code, nommage propre à l'équipementier) : équipements, alarmes et historique des équipements sont transférés, et une **correspondance de codes** est enregistrée ; elle s'applique automatiquement à toutes les collectes suivantes |
| **Ajouter** | admin | nouveau site : il entre au référentiel avec ses équipements et son historique (fenêtre de saisie préremplie, position à placer si l'OMC n'en fournit pas) |
| **Ignorer** (ou en lot) | superviseur | site de test, équipement temporaire… : sort du compteur « à traiter », motif obligatoire conseillé |

La section **Correspondances de codes** liste les rattachements (code OMC → site, auteur, commentaire) ;
supprimer une correspondance fait réapparaître le code comme site inconnu à la collecte suivante.

## 8. Données réelles

Le référentiel de l'opérateur est une donnée d'exploitation : il ne doit pas être versionné
(`.gitignore` : `referentiel-depot/*`, `*.kmz`) ni joint à des tickets ou documents externes. Les tests
automatisés utilisent uniquement des fichiers fictifs générés à la volée (`tests/test_reference.py`).

## 9. API

| Méthode | Chemin | Droit |
|---|---|---|
| GET | `/api/site-reference/summary` | lecture |
| POST | `/api/site-reference/import/preview` (multipart : `file`, `mapping` JSON, `mode`, `code_digits`, `sheet`) | admin |
| POST | `/api/site-reference/import/apply` (+ `expected_sha256`, `confirm_large_removal`) | admin |
| GET | `/api/site-reference/imports` | lecture |
| GET | `/api/site-reference/anomalies?type=&state=&q=&wilaya=` | lecture |
| GET | `/api/site-reference/anomalies/count` | lecture |
| POST | `/api/site-reference/anomalies/{id}/ack` · `/reopen` | superviseur |
| POST | `/api/site-reference/reconcile` | superviseur |
| GET | `/api/site-reference/anomalies/export`, `/api/site-reference/export` | export |
| GET | `/api/site-reference/template` | lecture |
| PUT | `/api/admin/settings/reference` | admin |
| GET | `/api/site-reference/options` | lecture |
| GET | `/api/site-reference/sites?q=&wilaya=&dr=&ref=&supervised=&source=&anomalies=&sort=&page=` · `/sites/export` | lecture · export |
| POST | `/api/site-reference/sites` (création ; adopte un site inconnu de même code) | admin |
| PUT | `/api/site-reference/sites/{id}` | admin |
| POST | `/api/site-reference/sites/delete` (`ids`, `mode` = `remove` ou `purge`) | admin |
| GET | `/api/site-reference/unknown-sites?state=&q=&source=` · `/unknown-sites/export` | lecture · export |
| POST | `/api/site-reference/unknown-sites/{site_id}/link` (`target_code`, `note`) | admin |
| POST | `/api/site-reference/unknown-sites/ack` (`anomaly_ids`, `note`) | superviseur |
| GET · DELETE | `/api/site-reference/aliases` · `/api/site-reference/aliases/{omc_code}` | lecture · admin |

Filtres ajoutés à `/api/sites`, `/api/sites/map`, `/api/dashboard/*`, `/api/export/*` :
`ref` (`IN_SERVICE`, `TEMP_OFF`, `PLANNED`, `REMOVED`, `OTHER`, `NONE`, `ALL`), `dr`, `supervised`,
et l'état `UNSUPERVISED`.
