-- 02 : schéma principal (idempotent, rejoué à chaque démarrage par « python -m app.cli init-db »)
-- Toute colonne ajoutée ici doit être mappée dans backend/app/models.py (test_schema.py le vérifie).

CREATE TABLE IF NOT EXISTS schema_version (
    id          smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    version     integer     NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Wilayas (69) ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wilayas (
    code         smallint PRIMARY KEY CHECK (code BETWEEN 1 AND 99),
    name_fr      text NOT NULL,
    name_ar      text,
    region       text,                       -- direction régionale (DR) de l'opérateur
    parent_code  smallint,                   -- wilaya mère pour les wilayas créées en 2025
    geom         geometry(MultiPolygon, 4326),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS wilayas_geom_gix ON wilayas USING gist (geom);

-- Sources OMC -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS omc_sources (
    id               serial PRIMARY KEY,
    code             text NOT NULL UNIQUE,
    name             text NOT NULL,
    vendor           text NOT NULL CHECK (vendor IN ('ERICSSON','HUAWEI','ZTE','OTHER','DEMO')),
    connector        text NOT NULL CHECK (connector IN ('prometheus','file_export','sql_readonly','vendor','demo')),
    config           jsonb NOT NULL DEFAULT '{}'::jsonb,
    value_maps       jsonb NOT NULL DEFAULT '{}'::jsonb,
    stale_after_s    integer NOT NULL DEFAULT 1800 CHECK (stale_after_s > 0),
    interval_s       integer NOT NULL DEFAULT 300  CHECK (interval_s >= 30),
    enabled          boolean NOT NULL DEFAULT false,
    last_status      text CHECK (last_status IN ('OK','FAILED','RUNNING','NEVER')),
    last_run_at      timestamptz,
    last_success_at  timestamptz,
    last_error       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- Sites -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sites (
    id              bigserial PRIMARY KEY,
    external_id     text NOT NULL UNIQUE,     -- code site
    name            text,
    geom            geometry(Point, 4326),
    wilaya_code     smallint REFERENCES wilayas(code),
    commune         text,
    address         text,
    vendor          text,
    technologies    text[] NOT NULL DEFAULT '{}',
    display_status  text NOT NULL DEFAULT 'UNKNOWN'
                    CHECK (display_status IN ('UP','DOWN','DEGRADED','UNKNOWN','UNSUPERVISED')),
    status_since    timestamptz,
    pending_status  text CHECK (pending_status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    pending_since   timestamptz,
    active          boolean NOT NULL DEFAULT true,
    extra           jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sites_geom_gix        ON sites USING gist (geom);
CREATE INDEX IF NOT EXISTS sites_wilaya_idx      ON sites (wilaya_code);
CREATE INDEX IF NOT EXISTS sites_status_idx      ON sites (display_status);
CREATE INDEX IF NOT EXISTS sites_name_trgm       ON sites USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS sites_external_trgm   ON sites USING gin (external_id gin_trgm_ops);

-- Éléments de réseau (NE) par site --------------------------------------
CREATE TABLE IF NOT EXISTS site_elements (
    id              bigserial PRIMARY KEY,
    site_id         bigint NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_id       integer REFERENCES omc_sources(id) ON DELETE SET NULL,
    ne_id           text NOT NULL,
    ne_name         text,
    ne_type         text,
    technology      text NOT NULL DEFAULT 'OTHER' CHECK (technology IN ('2G','3G','4G','5G','OTHER')),
    oper_status     text NOT NULL DEFAULT 'UNKNOWN' CHECK (oper_status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    raw_status      text,
    observed_at     timestamptz,
    status_since    timestamptz,
    pending_status  text CHECK (pending_status IN ('UP','DOWN','DEGRADED','UNKNOWN')),
    pending_since   timestamptz,
    active          boolean NOT NULL DEFAULT true,
    extra           jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS site_elements_source_ne_uq ON site_elements (source_id, ne_id);
CREATE INDEX IF NOT EXISTS site_elements_site_idx ON site_elements (site_id);

-- Historique des transitions --------------------------------------------
CREATE TABLE IF NOT EXISTS status_history (
    id           bigserial PRIMARY KEY,
    site_id      bigint NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    element_id   bigint REFERENCES site_elements(id) ON DELETE SET NULL,
    old_status   text,
    new_status   text NOT NULL,
    changed_at   timestamptz NOT NULL,
    source_id    integer REFERENCES omc_sources(id) ON DELETE SET NULL,
    reason       text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS status_history_site_idx ON status_history (site_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS status_history_time_idx ON status_history (changed_at DESC);

-- Alarmes -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alarms (
    id             bigserial PRIMARY KEY,
    source_id      integer REFERENCES omc_sources(id) ON DELETE SET NULL,
    omc_alarm_id   text NOT NULL,
    site_id        bigint REFERENCES sites(id) ON DELETE SET NULL,
    element_id     bigint REFERENCES site_elements(id) ON DELETE SET NULL,
    ne_id          text,
    code           text,
    severity       text NOT NULL DEFAULT 'INDETERMINATE'
                   CHECK (severity IN ('CRITICAL','MAJOR','MINOR','WARNING','INDETERMINATE')),
    description    text,
    raised_at      timestamptz,
    cleared_at     timestamptz,
    is_active      boolean NOT NULL DEFAULT true,
    last_seen_at   timestamptz,
    extra          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS alarms_source_omc_uq ON alarms (source_id, omc_alarm_id);
CREATE INDEX IF NOT EXISTS alarms_active_idx ON alarms (site_id) WHERE is_active;
CREATE INDEX IF NOT EXISTS alarms_raised_idx ON alarms (raised_at DESC);

-- Règles d'alarmes (actives seulement si validées par un administrateur) --
CREATE TABLE IF NOT EXISTS alarm_rules (
    id             serial PRIMARY KEY,
    source_id      integer REFERENCES omc_sources(id) ON DELETE CASCADE,
    vendor         text,
    match_code     text,
    match_pattern  text,
    effect         text NOT NULL CHECK (effect IN ('DOWN','DEGRADED')),
    scope          text NOT NULL DEFAULT 'SITE' CHECK (scope IN ('SITE','ELEMENT')),
    description    text,
    enabled        boolean NOT NULL DEFAULT true,
    validated      boolean NOT NULL DEFAULT false,
    validated_by   text,
    validated_at   timestamptz,
    created_by     text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (match_code IS NOT NULL OR match_pattern IS NOT NULL)
);

-- Paramètres --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text
);

-- Journal des collectes ----------------------------------------------------
CREATE TABLE IF NOT EXISTS collection_runs (
    id               bigserial PRIMARY KEY,
    source_id        integer NOT NULL REFERENCES omc_sources(id) ON DELETE CASCADE,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    status           text NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','OK','FAILED')),
    elements_count   integer NOT NULL DEFAULT 0,
    alarms_count     integer NOT NULL DEFAULT 0,
    unmapped_count   integer NOT NULL DEFAULT 0,
    error            text,
    details          jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS collection_runs_source_idx ON collection_runs (source_id, started_at DESC);

-- Tendances et santé des services -----------------------------------------
CREATE TABLE IF NOT EXISTS kpi_snapshots (
    id            bigserial PRIMARY KEY,
    taken_at      timestamptz NOT NULL,
    scope         text NOT NULL DEFAULT 'GLOBAL' CHECK (scope IN ('GLOBAL','WILAYA','DR','VENDOR','TECHNOLOGY')),
    scope_key     text NOT NULL DEFAULT '',
    total         integer NOT NULL DEFAULT 0,
    up            integer NOT NULL DEFAULT 0,
    down          integer NOT NULL DEFAULT 0,
    degraded      integer NOT NULL DEFAULT 0,
    unknown       integer NOT NULL DEFAULT 0,
    unsupervised  integer NOT NULL DEFAULT 0,
    availability  numeric(7,4)
);
CREATE UNIQUE INDEX IF NOT EXISTS kpi_snapshots_uq ON kpi_snapshots (taken_at, scope, scope_key);

CREATE TABLE IF NOT EXISTS service_heartbeats (
    service       text PRIMARY KEY,
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    details       jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Utilisateurs ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                    serial PRIMARY KEY,
    username              text NOT NULL,
    full_name             text,
    password_hash         text NOT NULL,
    role                  text NOT NULL DEFAULT 'VIEWER' CHECK (role IN ('ADMIN','SUPERVISOR','VIEWER')),
    can_export            boolean NOT NULL DEFAULT false,
    is_active             boolean NOT NULL DEFAULT true,
    failed_logins         integer NOT NULL DEFAULT 0,
    locked_until          timestamptz,
    must_change_password  boolean NOT NULL DEFAULT true,
    token_version         integer NOT NULL DEFAULT 0,
    last_login_at         timestamptz,
    password_changed_at   timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS users_username_uq ON users (lower(username));

-- Audit ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id        bigserial PRIMARY KEY,
    at        timestamptz NOT NULL DEFAULT now(),
    user_id   integer REFERENCES users(id) ON DELETE SET NULL,
    username  text,
    action    text NOT NULL,
    target    text,
    details   jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip        text
);
CREATE INDEX IF NOT EXISTS audit_log_at_idx ON audit_log (at DESC);
CREATE INDEX IF NOT EXISTS audit_log_action_idx ON audit_log (action);
