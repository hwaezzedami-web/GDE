-- =============================================================================
-- GSM Supervision Algérie — Extensions PostgreSQL
-- Exécuté automatiquement par l'image postgis/postgis au premier démarrage
-- (répertoire /docker-entrypoint-initdb.d), ou manuellement :
--   psql -d gsm_supervision -f db/init/01_extensions.sql
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS postgis;   -- coordonnées GPS, requêtes géographiques
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- recherche rapide par nom / identifiant de site
