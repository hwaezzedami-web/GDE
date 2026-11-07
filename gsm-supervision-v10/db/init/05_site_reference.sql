-- =============================================================================
-- v1.4 — Référentiel des sites (import KMZ / KML / Excel / CSV / GeoJSON) et
-- détection des écarts entre le référentiel et ce que remontent les OMC.
-- Script idempotent (rejoué à chaque démarrage de l'API).
-- =============================================================================

-- Équipementier inconnu : site connu du référentiel mais pas encore vu par un OMC
ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_vendor_check;
ALTER TABLE sites ADD CONSTRAINT sites_vendor_check
    CHECK (vendor IN ('ERICSSON','HUAWEI','ZTE','MULTI','UNKNOWN'));

ALTER TABLE sites ADD COLUMN IF NOT EXISTS in_reference        BOOLEAN NOT NULL DEFAULT FALSE; -- présent dans le dernier référentiel
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_status          TEXT;      -- catégorie normalisée du cycle de vie
ALTER TABLE sites ADD COLUMN IF NOT EXISTS lifecycle           TEXT;      -- valeur brute du fichier (ex. en_air, planning)
ALTER TABLE sites ADD COLUMN IF NOT EXISTS dr                  TEXT;      -- direction régionale de l'opérateur
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_technologies    TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE sites ADD COLUMN IF NOT EXISTS reference_seen_at   TIMESTAMPTZ;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS reference_import_id BIGINT;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS is_supervised       BOOLEAN NOT NULL DEFAULT FALSE; -- au moins un équipement OMC actif
ALTER TABLE sites ADD COLUMN IF NOT EXISTS last_supervised_at  TIMESTAMPTZ;                   -- dernière observation OMC connue

ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_ref_status_check;
ALTER TABLE sites ADD CONSTRAINT sites_ref_status_check
    CHECK (ref_status IS NULL OR ref_status IN ('IN_SERVICE','TEMP_OFF','PLANNED','REMOVED','OTHER'));

CREATE INDEX IF NOT EXISTS ix_sites_dr         ON sites (dr);
CREATE INDEX IF NOT EXISTS ix_sites_ref_status ON sites (in_reference, ref_status);
CREATE INDEX IF NOT EXISTS ix_sites_supervised ON sites (is_supervised);
CREATE INDEX IF NOT EXISTS ix_sites_extid_ltrim ON sites ((ltrim(external_id, '0'))) WHERE in_reference;

-- Les sites existants qui ont des équipements sont supervisés
UPDATE sites s SET is_supervised = TRUE, last_supervised_at = coalesce(s.last_supervised_at, s.last_observed_at)
WHERE NOT s.is_supervised AND EXISTS (SELECT 1 FROM site_elements e WHERE e.site_id = s.id AND e.is_active);

-- -----------------------------------------------------------------------------
-- Journal des imports du référentiel
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_imports (
    id            BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    username      TEXT,
    origin        TEXT NOT NULL CHECK (origin IN ('UI','WATCH','CLI')),
    file_name     TEXT,
    file_sha256   TEXT,
    file_format   TEXT,
    mode          TEXT NOT NULL CHECK (mode IN ('update','sync')),
    status        TEXT NOT NULL CHECK (status IN ('APPLIED','REFUSED','FAILED')),
    mapping       JSONB NOT NULL DEFAULT '{}'::jsonb,
    counts        JSONB NOT NULL DEFAULT '{}'::jsonb,
    messages      JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_refimports_time ON reference_imports (started_at DESC);
CREATE INDEX IF NOT EXISTS ix_refimports_sha  ON reference_imports (file_sha256);

-- -----------------------------------------------------------------------------
-- Anomalies référentiel ↔ OMC
--   UNKNOWN_SITE       : remonté par un OMC, absent du référentiel
--   REMOVED_BUT_ACTIVE : démonté / désinstallé au référentiel, mais en service dans l'OMC
--   PLANNED_BUT_ACTIVE : en projet au référentiel, mais déjà en service dans l'OMC
--   SUPERVISION_LOST   : en service au référentiel, plus remonté par aucun OMC depuis N jours
--   NEVER_SUPERVISED   : en service au référentiel, jamais remonté par un OMC (contrôle optionnel)
-- Une anomalie disparue est résolue automatiquement ; un acquittement la masque tant qu'elle persiste.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS site_anomalies (
    id                BIGSERIAL PRIMARY KEY,
    anomaly_type      TEXT NOT NULL CHECK (anomaly_type IN
                        ('UNKNOWN_SITE','REMOVED_BUT_ACTIVE','PLANNED_BUT_ACTIVE','SUPERVISION_LOST','NEVER_SUPERVISED')),
    site_id           BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_external_id  TEXT NOT NULL,
    details           JSONB NOT NULL DEFAULT '{}'::jsonb,
    state             TEXT NOT NULL DEFAULT 'OPEN' CHECK (state IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    first_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_detected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at       TIMESTAMPTZ,
    acknowledged_by   TEXT,
    acknowledged_at   TIMESTAMPTZ,
    note              TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_anomaly_current ON site_anomalies (anomaly_type, site_id) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_anomaly_state ON site_anomalies (state, anomaly_type);

INSERT INTO schema_version (version, description) VALUES (3, 'Référentiel des sites et anomalies')
ON CONFLICT (version) DO NOTHING;
