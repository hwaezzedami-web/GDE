export const STATUS = {
  UP: { label: 'UP', long: 'Opérationnel', color: '#16a34a' },
  DOWN: { label: 'DOWN', long: 'En panne', color: '#dc2626' },
  DEGRADED: { label: 'DÉGRADÉ', long: 'Dégradé / alarme majeure', color: '#ea8a0c' },
  UNKNOWN: { label: 'INCONNU', long: 'Inconnu : données manquantes, pas une panne', color: '#6b4fbb' },
  // Site du référentiel qu'aucun OMC ne remonte (marqueur creux) : ni panne, ni état connu
  UNSUPERVISED: { label: 'NON SUPERVISÉ', long: 'Non supervisé (aucun OMC ne le remonte)', color: '#9aa3b2' },
};
export const STATUS_ORDER = ['DOWN', 'DEGRADED', 'UNKNOWN', 'UNSUPERVISED', 'UP'];

// Catégories du référentiel (cycle de vie de l'opérateur, regroupé)
export const REF_STATUS = {
  IN_SERVICE: { label: 'En service', color: '#16a34a' },
  TEMP_OFF: { label: 'Arrêt temporaire', color: '#ca8a04' },
  PLANNED: { label: 'En projet', color: '#2563eb' },
  REMOVED: { label: 'Démonté', color: '#64748b' },
  OTHER: { label: 'Autre', color: '#9333ea' },
};
export const ANOMALY = {
  UNKNOWN_SITE: { label: 'Site inconnu du référentiel', short: 'Inconnu du référentiel', color: '#dc2626',
    help: 'Remonté par un OMC mais absent du référentiel : site à ajouter au référentiel, ou code erroné dans l\'OMC.' },
  REMOVED_BUT_ACTIVE: { label: 'Démonté mais actif', short: 'Démonté mais actif', color: '#ea8a0c',
    help: 'Démonté / désinstallé au référentiel, mais UP ou dégradé dans l\'OMC.' },
  PLANNED_BUT_ACTIVE: { label: 'En projet mais déjà actif', short: 'Projet déjà actif', color: '#2563eb',
    help: 'En projet au référentiel mais déjà en service : cycle de vie à mettre à jour.' },
  SUPERVISION_LOST: { label: 'Supervision perdue', short: 'Supervision perdue', color: '#7c3aed',
    help: 'En service au référentiel, déjà vu par un OMC, mais plus remonté depuis plusieurs jours.' },
  NEVER_SUPERVISED: { label: 'Jamais supervisé', short: 'Jamais supervisé', color: '#64748b',
    help: 'En service au référentiel, jamais remonté par aucun OMC (contrôle optionnel).' },
};

// Anneau autour du marqueur = technologie la plus récente présente sur le site
export const TECH = {
  '2G': { color: '#334155' },
  '3G': { color: '#0e7490' },
  '4G': { color: '#2563eb' },
  '5G': { color: '#9333ea' },
};
export const TECHS = ['2G', '3G', '4G', '5G'];
export const VENDORS = ['ERICSSON', 'HUAWEI', 'ZTE'];
export const VENDOR_LABEL = { ERICSSON: 'Ericsson', HUAWEI: 'Huawei', ZTE: 'ZTE', MULTI: 'Multi', UNKNOWN: 'Non renseigné' };
export const SEVERITY = {
  CRITICAL: { label: 'Critique', color: '#b91c1c' },
  MAJOR: { label: 'Majeure', color: '#ea8a0c' },
  MINOR: { label: 'Mineure', color: '#ca8a04' },
  WARNING: { label: 'Avertissement', color: '#0e7490' },
  INDETERMINATE: { label: 'Indéterminée', color: '#64748b' },
};

export const TILE_URL = import.meta.env.VITE_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const TILE_ATTRIBUTION = import.meta.env.VITE_TILE_ATTRIBUTION || '&copy; contributeurs OpenStreetMap';
// Fond de carte par défaut : 'offline' (carte embarquée), 'auto' (OSM, bascule si injoignable) ou 'osm'
export const BASEMAP = import.meta.env.VITE_BASEMAP || 'offline';
export const REFRESH_MS = 1000 * Number(import.meta.env.VITE_REFRESH_SECONDS || 60);

const dtf = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Africa/Algiers', day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
export const fmtDate = (v) => (v ? dtf.format(new Date(v)) : '—');

export function fmtDuration(seconds) {
  if (seconds == null) return '—';
  const s = Math.max(0, Math.round(seconds));
  const d = Math.floor(s / 86400); const h = Math.floor((s % 86400) / 3600); const m = Math.floor((s % 3600) / 60);
  if (d) return `${d} j ${h} h`;
  if (h) return `${h} h ${String(m).padStart(2, '0')}`;
  return `${m} min`;
}
export const since = (v) => (v ? fmtDuration((Date.now() - new Date(v).getTime()) / 1000) : '—');
export const fmtInt = (n) => (n == null ? '—' : new Intl.NumberFormat('fr-FR').format(n));
