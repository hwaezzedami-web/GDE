-- 05 : référentiel des sites (idempotent)

ALTER TABLE sites ADD COLUMN IF NOT EXISTS in_reference        boolean NOT NULL DEFAULT false;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_status          text;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_source          text;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_updated_at      timestamptz;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_updated_by      text;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS is_supervised       boolean NOT NULL DEFAULT false;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS last_supervised_at  timestamptz;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS dr                  text;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sites_ref_status_chk') THEN
        ALTER TABLE sites ADD CONSTRAINT sites_ref_status_chk
            CHECK (ref_status IS NULL OR ref_status IN ('IN_SERVICE','TEMP_OFF','PLANNED','REMOVED','OTHER'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sites_ref_source_chk') THEN
        ALTER TABLE sites ADD CONSTRAINT sites_ref_source_chk
            CHECK (ref_source IS NULL OR ref_source IN ('IMPORT','MANUAL'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS sites_in_reference_idx ON sites (in_reference, ref_status);

CREATE TABLE IF NOT EXISTS reference_imports (
    id            bigserial PRIMARY KEY,
    imported_at   timestamptz NOT NULL DEFAULT now(),
    imported_by   text,
    filename      text NOT NULL,
    file_sha256   text,
    file_format   text,
    origin        text NOT NULL DEFAULT 'UPLOAD' CHECK (origin IN ('UPLOAD','WATCH','CLI')),
    added         integer NOT NULL DEFAULT 0,
    updated       integer NOT NULL DEFAULT 0,
    removed       integer NOT NULL DEFAULT 0,
    unchanged     integer NOT NULL DEFAULT 0,
    rejected      integer NOT NULL DEFAULT 0,
    mapping       jsonb NOT NULL DEFAULT '{}'::jsonb,
    details       jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS site_anomalies (
    id             bigserial PRIMARY KEY,
    site_id        bigint NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    kind           text NOT NULL CHECK (kind IN ('UNKNOWN_SITE','REMOVED_BUT_ACTIVE','PLANNED_BUT_ACTIVE',
                                                 'SUPERVISION_LOST','NEVER_SUPERVISED')),
    status         text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ACK','RESOLVED')),
    details        jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at  timestamptz NOT NULL DEFAULT now(),
    last_seen_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at    timestamptz,
    ack_by         text,
    ack_at         timestamptz,
    ack_comment    text
);
CREATE UNIQUE INDEX IF NOT EXISTS site_anomalies_open_uq
    ON site_anomalies (site_id, kind) WHERE status <> 'RESOLVED';
CREATE INDEX IF NOT EXISTS site_anomalies_status_idx ON site_anomalies (status, kind);
