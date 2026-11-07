-- =============================================================================
-- v1.5 — Gestion manuelle du référentiel et correspondances de codes OMC.
-- Script idempotent (rejoué à chaque démarrage de l'API).
-- =============================================================================

-- Origine de la dernière écriture d'un site du référentiel : import de fichier ou saisie manuelle
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_source     TEXT CHECK (ref_source IN ('IMPORT', 'MANUAL'));
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_updated_at TIMESTAMPTZ;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ref_updated_by TEXT;
UPDATE sites s SET ref_source = 'IMPORT', ref_updated_at = coalesce(s.reference_seen_at, now()),
    ref_updated_by = coalesce((SELECT coalesce(i.username, lower(i.origin)) FROM reference_imports i
                               WHERE i.id = s.reference_import_id), 'import')
WHERE s.in_reference AND s.ref_source IS NULL;
CREATE INDEX IF NOT EXISTS ix_sites_ref_source ON sites (ref_source) WHERE in_reference;

-- -----------------------------------------------------------------------------
-- Correspondances de codes : un code remonté par un OMC (faute de frappe, ancien code,
-- nommage propre à l'équipementier) est rattaché à un site du référentiel.
-- Appliquées à chaque collecte avant toute écriture.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS site_code_aliases (
    omc_code          TEXT PRIMARY KEY,
    site_external_id  TEXT NOT NULL REFERENCES sites(external_id) ON UPDATE CASCADE ON DELETE CASCADE,
    note              TEXT,
    created_by        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (omc_code <> site_external_id)
);
CREATE INDEX IF NOT EXISTS ix_alias_site ON site_code_aliases (site_external_id);

INSERT INTO schema_version (version, description) VALUES (4, 'Gestion manuelle du référentiel, correspondances de codes')
ON CONFLICT (version) DO NOTHING;
