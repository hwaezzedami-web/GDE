# 9. Carte de l'Algérie et référentiel des 69 wilayas

## Ce qui est embarqué

| Élément | Emplacement | Source | Licence |
|---|---|---|---|
| Référentiel des **69 wilayas** : codes, noms FR/AR, chef-lieu, wilaya mère, année de création | `db/reference/wilayas.csv` → `db/init/03_reference_wilayas.sql` | Paquet `geoalgeria` 2.4.0 (compilation de textes officiels) | MIT |
| **Contours des 69 wilayas** (69 polygones, ~7 800 sommets) | `db/reference/wilaya_boundaries.geojson` → `db/init/04_wilaya_boundaries.sql` (PostGIS) | OpenStreetMap, relations `admin_level=4`, via `geoalgeria` (corrections documentées par le paquet) | ODbL 1.0, © contributeurs OpenStreetMap |
| Pays voisins (fond hors ligne) | `frontend/public/geo/voisins.geojson` | Natural Earth 1:50m, via `world-atlas` | Domaine public |
| Régions d'exploitation (Centre, Est, Ouest, Sud) | `db/reference/wilayas.csv` | Découpage propre au projet, à adapter | — |

**Réforme 2026** : la loi n° 26-06 (Journal officiel n° 25 du 5 avril 2026) porte le nombre de wilayas de 58 à 69. Les wilayas 59 à 69 (Aflou, Barika, El Kantara, Bir El Ater, El Aricha, Ksar Chellala, Aïn Ouessara, Messaad, Ksar El Boukhari, Bou Saâda, El Abiodh Sidi Cheikh) exercent pleinement leurs compétences à partir du 1er janvier 2027. La colonne `parent_code` indique la wilaya mère de chacune.

Aucun service Internet n'est nécessaire : les contours sont en base, le fond des pays voisins est servi par nginx avec l'interface.

## Fonds de carte dans l'interface

| Fond | Contenu | Prérequis |
|---|---|---|
| **Algérie (hors ligne)** | Mer, pays voisins, 69 wilayas teintées par région, limites et noms des wilayas | Aucun |
| Plan OpenStreetMap | Fond détaillé (villes, routes, relief) + limites des wilayas en surimpression | Accès Internet des postes vers `tile.openstreetmap.org` (ou serveur de tuiles interne : `VITE_TILE_URL`) |

Paramètre `VITE_BASEMAP` (au build de l'interface) :
- `offline` (défaut) : carte embarquée ;
- `auto` : fond OpenStreetMap ; si le serveur de tuiles est injoignable, bascule sur la carte embarquée avec un message ;
- `osm` : fond en ligne uniquement.

**OpenStreetMap public** : son serveur de tuiles exige un en-tête `Referer` (l'interface l'envoie) et applique une politique d'usage qui interdit les usages intensifs ; il peut répondre par des tuiles « Access blocked » (HTTP 403). La bascule automatique ne détecte pas ce cas : les tuiles de refus sont des images valides. Pour une exploitation quotidienne, utiliser la carte embarquée ou un serveur de tuiles interne (`VITE_TILE_URL`).

L'utilisateur peut changer de fond à tout moment (icône des couches) ; son choix est mémorisé sur le poste.

## Rattachement des sites à leur wilaya

- La wilaya fournie par la source (OMC ou import CSV) est **toujours conservée**.
- Un site sans wilaya est rattaché automatiquement d'après ses coordonnées (requête PostGIS `ST_Covers`), à l'ingestion et à chaque initialisation de la base.
- Après la réforme, des sites encore déclarés dans leur wilaya mère (ex. Laghouat) peuvent être basculés vers la nouvelle wilaya (ex. Aflou) :

```bash
docker compose exec api python -m app.cli reassign-wilayas          # seulement les sites sans wilaya
docker compose exec api python -m app.cli reassign-wilayas --all    # tous les sites d'après leur position
```

À décider avec l'exploitation : tant que les OMC et les rapports utilisent l'ancien découpage, conserver la wilaya fournie par la source.

## Précision et contours officiels

Les contours embarqués sont **simplifiés** (environ 100 m à 3 km d'écart selon les zones ; surface totale 2,31 millions de km² contre 2,38 officiellement). Ils suffisent pour l'affichage et pour rattacher la grande majorité des sites, mais un site situé à quelques centaines de mètres d'une limite peut être rattaché à la wilaya voisine, ou à aucune wilaya près d'une frontière.

Pour une précision officielle, charger les contours de référence (INCT, ONS ou SIG de l'opérateur), au format GeoJSON en coordonnées WGS 84 (EPSG:4326) :

```bash
docker compose cp contours_officiels.geojson api:/tmp/
docker compose exec api python -m app.cli load-boundaries /tmp/contours_officiels.geojson --code-property CODE_WILAYA
docker compose exec api python -m app.cli reassign-wilayas --all     # si souhaité
```

Les contours chargés ainsi sont marqués `custom` et ne sont jamais écrasés par les mises à jour du projet.

## Mettre à jour les données cartographiques

```bash
cd /tmp && npm pack geoalgeria && tar -xzf geoalgeria-*.tgz          # nouvelle version du référentiel
python3 <projet>/scripts/build_wilaya_reference.py /tmp/package       # régénère CSV, GeoJSON et scripts SQL 03/04
npm pack world-atlas@2 topojson-client@3 && mkdir wa tc && tar -xzf world-atlas-*.tgz -C wa && tar -xzf topojson-client-*.tgz -C tc
node <projet>/scripts/build_basemap.mjs wa/package/countries-50m.json tc/package/dist/topojson-client.js <projet>/frontend/public/geo/voisins.geojson
```

Puis redéployer : l'API rejoue les scripts SQL au démarrage (les contours `custom` sont préservés).

## Obligations de licence

Les contours de wilayas sont dérivés d'OpenStreetMap (ODbL 1.0). L'attribution « © contributeurs OpenStreetMap » est affichée en permanence sur la carte et rappelée dans [NOTICE.md](../NOTICE.md). Usage interne : aucune autre obligation. En cas de diffusion publique d'une base de données dérivée de ces contours, elle doit être proposée sous la même licence ODbL.
