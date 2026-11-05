-- 06 : gestion des sites et correspondances de codes OMC (idempotent)

CREATE TABLE IF NOT EXISTS site_code_aliases (
    omc_code    text PRIMARY KEY,
    site_code   text NOT NULL REFERENCES sites(external_id) ON UPDATE CASCADE ON DELETE CASCADE,
    comment     text,
    created_by  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS site_code_aliases_site_idx ON site_code_aliases (site_code);

-- Version du schéma (dernier script) ------------------------------------
INSERT INTO schema_version (id, version) VALUES (1, 4)
ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, updated_at = now()
WHERE schema_version.version < EXCLUDED.version;
