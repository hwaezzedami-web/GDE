# Référentiel géographique

## `wilayas.csv`

69 wilayas : `code, name_fr, name_ar, region, parent_code, a_verifier`.

- Codes 1 à 58 : découpage historique.
- Codes 59 à 69 : wilayas créées en 2025. **Les numéros et l'ordre sont à vérifier contre le texte
  officiel** (colonne `a_verifier = oui`) avant toute mise en production ; `parent_code` donne la
  wilaya mère.
- `region` (direction régionale, DR) est volontairement vide : c'est une donnée propre à l'opérateur,
  à remplir à partir de son organisation réelle.

Le fichier est chargé (upsert) à chaque `python -m app.cli init-db`.

## `wilaya_boundaries.geojson`

Contours des wilayas (MultiPolygon, WGS 84), propriété `code` obligatoire. Le fichier livré est vide :
aucun contour n'est inventé. Le construire à partir d'une source officielle ou libre (par exemple un
découpage administratif OpenStreetMap ou geoBoundaries) avec :

```bash
python scripts/build_wilaya_reference.py source.geojson --name-property NOM_DU_CHAMP
```

Le script rapproche chaque entité d'une wilaya par son nom (ou `--code-property`) et refuse d'écrire
le fichier si des wilayas restent non rapprochées, sauf `--allow-missing`.
