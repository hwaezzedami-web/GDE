# Attributions et licences des données tierces

| Données | Fichiers | Source | Licence |
|---|---|---|---|
| Contours des 69 wilayas | `db/reference/wilaya_boundaries.geojson`, `db/init/04_wilaya_boundaries.sql` | © contributeurs OpenStreetMap, compilation [geoalgeria](https://github.com/yasserstudio/geoalgeria) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| Référentiel des wilayas (codes, noms, chefs-lieux, wilayas mères) | `db/reference/wilayas.csv`, `db/init/03_reference_wilayas.sql` | geoalgeria (textes officiels : lois 84-09, 19-12, 26-06) — coordonnées des chefs-lieux en partie issues d'OpenStreetMap | MIT ; parties OSM : ODbL 1.0 |
| Pays voisins (fond hors ligne) | `frontend/public/geo/voisins.geojson` | [Natural Earth](https://www.naturalearthdata.com) 1:50m via [world-atlas](https://github.com/topojson/world-atlas) | Domaine public (Natural Earth) ; ISC (world-atlas) |
| Fond de carte en ligne (optionnel) | — (tuiles chargées par le navigateur) | © contributeurs OpenStreetMap | ODbL 1.0 ; politique d'usage des tuiles OSM |
| Jeu de données de test | `data/test/sites_fictifs.csv` | Généré aléatoirement — **entièrement fictif** | — |

Prometheus et Alertmanager (images `prom/prometheus`, `prom/alertmanager` de la pile optionnelle) : licence Apache 2.0, non redistribués dans ce projet.

Bibliothèques logicielles : voir `backend/requirements.txt` et `frontend/package.json` (licences libres MIT, BSD, Apache 2.0, ISC, LGPL pour psycopg).
