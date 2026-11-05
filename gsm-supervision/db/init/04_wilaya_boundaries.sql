-- 04 : contours des wilayas
-- Les géométries sont chargées par « python -m app.cli init-db » depuis
-- db/reference/wilaya_boundaries.geojson (propriété « code » = code wilaya).
-- Ce fichier se construit avec scripts/build_wilaya_reference.py à partir d'une source
-- officielle ; aucun contour n'est inventé.

-- Vue simplifiée servie à la carte (allège le transfert vers le navigateur).
CREATE OR REPLACE VIEW wilaya_boundaries_simplified AS
SELECT code,
       name_fr,
       region,
       ST_SimplifyPreserveTopology(geom, 0.005) AS geom
  FROM wilayas
 WHERE geom IS NOT NULL;
