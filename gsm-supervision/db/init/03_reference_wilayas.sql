-- 03 : référentiel des wilayas
-- Les lignes sont chargées par « python -m app.cli init-db » depuis db/reference/wilayas.csv
-- (upsert ON CONFLICT). Ce script ne contient que les fonctions SQL utilitaires.

-- Wilaya contenant un point (NULL si aucun contour chargé ou point hors Algérie).
CREATE OR REPLACE FUNCTION wilaya_for_point(p geometry)
RETURNS smallint
LANGUAGE sql STABLE AS $$
    SELECT w.code
      FROM wilayas w
     WHERE w.geom IS NOT NULL AND ST_Intersects(w.geom, p)
     ORDER BY w.code
     LIMIT 1
$$;
