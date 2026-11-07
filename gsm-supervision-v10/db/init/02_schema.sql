-- =============================================================================
-- GSM Supervision Algérie — Schéma de la base de données (source de vérité)
-- Cible : PostgreSQL 14+ avec PostGIS 3+
-- Les modèles SQLAlchemy (backend/app/models.py) sont alignés sur ce fichier ;
-- le test tests/test_schema.py vérifie leur cohérence.
-- =============================================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    description TEXT NOT NULL
);

-- -----------------------------------------------------------------------------
-- Référentiel géographique : wilayas
-- boundary : contour administratif optionnel (chargé depuis un GeoJSON officiel,
-- voir scripts/load_wilaya_boundaries.py). S'il est présent, la wilaya d'un site
-- sans wilaya renseignée est déduite de ses coordonnées.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wilayas (
    code        SMALLINT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_ar     TEXT,
    region      TEXT NOT NULL,
    chef_lieu   TEXT,
    center_lat  DOUBLE PRECISION,
    center_lon  DOUBLE PRECISION,
    boundary    geography(MultiPolygon, 4326)
);
-- Réforme 2026 (loi n° 26-06) : wilaya mère des wilayas 59 à 69, origine des contours
ALTER TABLE wilayas ADD COLUMN IF NOT EXISTS parent_code SMALLINT REFERENCES wilayas(code);
ALTER TABLE wilayas ADD COLUMN IF NOT EXISTS created_year SMALLINT;
ALTER TABLE wilayas ADD COLUMN IF NOT EXISTS boundary_source TEXT;   -- 'osm-geoalgeria' | 'custom'
CREATE INDEX IF NOT EXISTS ix_wilayas_boundary ON wilayas USING GIST (boundary);

-- -----------------------------------------------------------------------------
-- Sources OMC (une ligne par serveur / instance OMC)
-- Aucun secret ici : les identifiants sont lus dans des variables
-- d'environnement OMC_<CODE>_* (voir docs/04_CONNECTEURS_OMC.md).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS omc_sources (
    id                    SERIAL PRIMARY KEY,
    code                  TEXT NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9_-]{2,40}$'),
    name                  TEXT NOT NULL,
    vendor                TEXT NOT NULL CHECK (vendor IN ('ERICSSON','HUAWEI','ZTE')),
    connector_type        TEXT NOT NULL CHECK (connector_type IN
                            ('manual_csv','file_export','sql_readonly','ericsson','huawei','zte','demo','prometheus')),
    enabled               BOOLEAN NOT NULL DEFAULT FALSE,
    is_demo               BOOLEAN NOT NULL DEFAULT FALSE,     -- données fictives
    integration_validated BOOLEAN NOT NULL DEFAULT FALSE,     -- validée sur données réelles ?
    poll_interval_s       INTEGER NOT NULL DEFAULT 300 CHECK (poll_interval_s BETWEEN 30 AND 86400),
    stale_after_s         INTEGER CHECK (stale_after_s IS NULL OR stale_after_s >= 60),  -- NULL = jamais périmé (import manuel)
    config                JSONB NOT NULL DEFAULT '{}'::jsonb,  -- paramètres NON secrets (chemins, mapping colonnes…)
    sync_requested_at     TIMESTAMPTZ,                         -- demande de synchronisation immédiate
    last_attempt_at       TIMESTAMPTZ,
    last_success_at       TIMESTAMPTZ,
    last_status           TEXT CHECK (last_status IN ('SUCCESS','PARTIAL','FAILED','RUNNING')),
    last_error            TEXT,
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- v1.2 : connecteur Prometheus (mise à niveau des bases existantes)
ALTER TABLE omc_sources DROP CONSTRAINT IF EXISTS omc_sources_connector_type_check;
ALTER TABLE omc_sources ADD CONSTRAINT omc_sources_connector_type_check CHECK (connector_type IN
    ('manual_csv','file_export','sql_readonly','ericsson','huawei','zte','demo','prometheus'));

-- -----------------------------------------------------------------------------
-- Sites radio
-- external_id : code site opérateur (commun aux technologies d'un même site).
-- status      : état consolidé calculé par le moteur d'états (services/status_engine.py)
-- technologies: dénormalisé (maintenu par le moteur) pour filtrer vite sur la carte
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sites (
    id                   BIGSERIAL PRIMARY KEY,
    external_id          TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    vendor               TEXT NOT NULL CHECK (vendor IN ('ERICSSON','HUAWEI','ZTE','MULTI')),
    primary_source_id    INTEGER REFERENCES omc_sources(id) ON DELETE SET NULL,
    wilaya_code          SMALLINT REFERENCES wilayas(code),
    commune              TEXT,
    address              TEXT,
    latitude             DOUBLE PRECISION CHECK (latitude  IS NULL OR latitude  BETWEEN 18.0 AND 38.5),
    longitude            DOUBLE PRECISION CHECK (longitude IS NULL OR longitude BETWEEN -9.5 AND 12.5),
    geom                 geography(Point, 4326) GENERATED ALWAYS AS (
                             CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                                  THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography END
                         ) STORED,
    technologies         TEXT[] NOT NULL DEFAULT '{}',
    status               TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    status_since         TIMESTAMPTZ NOT NULL DEFAULT now(),
    status_reason        TEXT,
    pending_status       TEXT CHECK (pending_status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    pending_since        TIMESTAMPTZ,                -- anti-rebond (délai de confirmation)
    last_observed_at     TIMESTAMPTZ,                -- observation la plus récente reçue d'un OMC
    is_stale             BOOLEAN NOT NULL DEFAULT FALSE,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    extra                JSONB NOT NULL DEFAULT '{}'::jsonb,   -- infos complémentaires OMC
    first_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sites_geom        ON sites USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_sites_status      ON sites (status) WHERE is_active;
CREATE INDEX IF NOT EXISTS ix_sites_wilaya      ON sites (wilaya_code, commune);
CREATE INDEX IF NOT EXISTS ix_sites_vendor      ON sites (vendor);
CREATE INDEX IF NOT EXISTS ix_sites_techs       ON sites USING GIN (technologies);
CREATE INDEX IF NOT EXISTS ix_sites_name_trgm   ON sites USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_sites_extid_trgm  ON sites USING GIN (external_id gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_sites_status_since ON sites (status_since);

-- -----------------------------------------------------------------------------
-- Équipements radio / technologies (BTS, NodeB, eNodeB, gNodeB, cellules…)
-- oper_status : état normalisé fourni par la source
-- raw_status  : valeur brute telle que reçue (traçabilité)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS site_elements (
    id                    BIGSERIAL PRIMARY KEY,
    site_id               BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    omc_source_id         INTEGER NOT NULL REFERENCES omc_sources(id) ON DELETE CASCADE,
    external_id           TEXT NOT NULL,
    technology            TEXT NOT NULL CHECK (technology IN ('2G','3G','4G','5G')),
    element_type          TEXT NOT NULL DEFAULT 'NE',
    name                  TEXT,
    oper_status           TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (oper_status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    raw_status            TEXT,
    status_observed_at    TIMESTAMPTZ,
    status_changed_at     TIMESTAMPTZ,
    last_communication_at TIMESTAMPTZ,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    extra                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_element_source_ext UNIQUE (omc_source_id, external_id)
);
CREATE INDEX IF NOT EXISTS ix_elements_site ON site_elements (site_id) WHERE is_active;

-- -----------------------------------------------------------------------------
-- Historique des changements d'état (sites et équipements)
-- Une ligne par transition : sert au calcul des durées de panne et de la
-- disponibilité. Les observations sans changement ne sont pas historisées
-- ligne à ligne (volumétrie) : la dernière observation est portée par
-- sites.last_observed_at / site_elements.status_observed_at.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS status_history (
    id            BIGSERIAL PRIMARY KEY,
    entity_type   TEXT NOT NULL CHECK (entity_type IN ('SITE','ELEMENT')),
    site_id       BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    element_id    BIGINT REFERENCES site_elements(id) ON DELETE CASCADE,
    old_status    TEXT CHECK (old_status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    new_status    TEXT NOT NULL CHECK (new_status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    changed_at    TIMESTAMPTZ NOT NULL,
    observed_at   TIMESTAMPTZ,
    source        TEXT NOT NULL,          -- code OMC, 'ENGINE', 'IMPORT'
    reason        TEXT,
    alarm_id      BIGINT
);
CREATE INDEX IF NOT EXISTS ix_hist_site_time ON status_history (site_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS ix_hist_site_level ON status_history (changed_at DESC, new_status) WHERE entity_type = 'SITE';

-- -----------------------------------------------------------------------------
-- Alarmes
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alarms (
    id                 BIGSERIAL PRIMARY KEY,
    omc_source_id      INTEGER NOT NULL REFERENCES omc_sources(id) ON DELETE CASCADE,
    external_alarm_id  TEXT NOT NULL,
    site_id            BIGINT REFERENCES sites(id) ON DELETE SET NULL,
    element_id         BIGINT REFERENCES site_elements(id) ON DELETE SET NULL,
    alarm_code         TEXT,
    description        TEXT,
    severity           TEXT NOT NULL DEFAULT 'INDETERMINATE'
                         CHECK (severity IN ('CRITICAL','MAJOR','MINOR','WARNING','INDETERMINATE')),
    state              TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','CLEARED')),
    raised_at          TIMESTAMPTZ,
    cleared_at         TIMESTAMPTZ,
    last_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    extra              JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_alarm_source_ext UNIQUE (omc_source_id, external_alarm_id)
);
CREATE INDEX IF NOT EXISTS ix_alarms_site_active ON alarms (site_id, raised_at DESC) WHERE state = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_alarms_site_time   ON alarms (site_id, raised_at DESC);

-- -----------------------------------------------------------------------------
-- Règles de déduction d'état à partir des alarmes
-- Une règle n'est appliquée que si enabled = TRUE ET validated_at IS NOT NULL
-- (validation explicite par un administrateur — exigence §4 du cahier des charges).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alarm_rules (
    id             SERIAL PRIMARY KEY,
    vendor         TEXT NOT NULL CHECK (vendor IN ('ERICSSON','HUAWEI','ZTE')),
    alarm_code     TEXT,          -- correspondance exacte sur le code
    text_pattern   TEXT,          -- ou expression régulière (insensible à la casse) sur la description
    effect         TEXT NOT NULL CHECK (effect IN ('DOWN','DEGRADED')),
    scope          TEXT NOT NULL DEFAULT 'ELEMENT' CHECK (scope IN ('ELEMENT','SITE')),
    enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    note           TEXT,
    validated_by   TEXT,
    validated_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (alarm_code IS NOT NULL OR text_pattern IS NOT NULL)
);

-- -----------------------------------------------------------------------------
-- Paramètres applicatifs (règles d'états, seuils…) — clé/valeur JSON
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  TEXT
);

-- -----------------------------------------------------------------------------
-- Journal des collectes
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collection_runs (
    id                BIGSERIAL PRIMARY KEY,
    omc_source_id     INTEGER NOT NULL REFERENCES omc_sources(id) ON DELETE CASCADE,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')),
    attempts          INTEGER NOT NULL DEFAULT 1,
    sites_processed     INTEGER NOT NULL DEFAULT 0,
    elements_processed  INTEGER NOT NULL DEFAULT 0,
    alarms_processed    INTEGER NOT NULL DEFAULT 0,
    records_rejected    INTEGER NOT NULL DEFAULT 0,
    error_message     TEXT,
    details           JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_runs_source_time ON collection_runs (omc_source_id, started_at DESC);

-- -----------------------------------------------------------------------------
-- Instantanés agrégés (courbes d'évolution du tableau de bord)
-- Écrits par le service de collecte toutes les N minutes.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kpi_snapshots (
    taken_at     TIMESTAMPTZ NOT NULL,
    vendor       TEXT NOT NULL,
    wilaya_code  SMALLINT NOT NULL DEFAULT 0,      -- 0 = wilaya non renseignée
    total        INTEGER NOT NULL,
    up           INTEGER NOT NULL,
    down         INTEGER NOT NULL,
    degraded     INTEGER NOT NULL,
    unknown      INTEGER NOT NULL,
    PRIMARY KEY (taken_at, vendor, wilaya_code)
);

-- -----------------------------------------------------------------------------
-- Battement de cœur des services (supervision technique)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_heartbeats (
    service     TEXT NOT NULL,
    host        TEXT NOT NULL,
    last_beat   TIMESTAMPTZ NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL,
    info        JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (service, host)
);

-- -----------------------------------------------------------------------------
-- Utilisateurs et audit
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id               SERIAL PRIMARY KEY,
    username         TEXT NOT NULL UNIQUE CHECK (username ~ '^[a-zA-Z0-9._-]{3,64}$'),
    full_name        TEXT,
    email            TEXT,
    password_hash    TEXT NOT NULL,
    role             TEXT NOT NULL CHECK (role IN ('ADMIN','SUPERVISOR','VIEWER')),
    can_export       BOOLEAN NOT NULL DEFAULT FALSE,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    failed_logins    INTEGER NOT NULL DEFAULT 0,
    locked_until     TIMESTAMPTZ,
    token_version    INTEGER NOT NULL DEFAULT 0,      -- incrémenté pour révoquer les sessions
    last_login_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username   TEXT,
    action     TEXT NOT NULL,
    target     TEXT,
    details    JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip         TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_at ON audit_log (at DESC);

-- -----------------------------------------------------------------------------
-- Paramètres par défaut des règles d'états (modifiables dans l'interface Admin)
-- -----------------------------------------------------------------------------
INSERT INTO app_settings (key, value, updated_by) VALUES
 ('status_rules', '{
    "default_stale_after_s": 1800,
    "down_confirm_s": 0,
    "up_confirm_s": 0,
    "unknown_elements_policy": "ignore",
    "major_alarm_degrades": true,
    "partial_down_is_degraded": true
  }'::jsonb, 'install'),
 ('collector', '{
    "evaluate_every_s": 60,
    "snapshot_every_s": 900,
    "max_retries": 3,
    "retry_backoff_s": 10,
    "history_retention_days": 730,
    "runs_retention_days": 90,
    "snapshots_retention_days": 400
  }'::jsonb, 'install')
ON CONFLICT (key) DO NOTHING;

INSERT INTO schema_version (version, description) VALUES (1, 'Schéma initial')
ON CONFLICT (version) DO NOTHING;
