import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import FiltersPanel from '../components/FiltersPanel';
import KpiStrip from '../components/KpiStrip';
import MapView from '../components/MapView';
import SiteDetail from '../components/SiteDetail';
import SitesTable from '../components/SitesTable';
import { ErrorBox } from '../components/ui';
import { api } from '../lib/api';
import { REFRESH_MS, fmtDate } from '../lib/constants';
import { useFilters } from '../lib/filters';
import { useReference } from '../lib/reference';

const COORD_RX = /^\s*(-?\d{1,2}(?:[.,]\d+)?)\s*[,; ]\s*(-?\d{1,2}(?:[.,]\d+)?)\s*$/;
const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export default function MapPage() {
  const { filters, setFilters, query } = useFilters();
  const [params, setParams] = useSearchParams();
  const ref = useReference();
  const [points, setPoints] = useState(null);
  const [summary, setSummary] = useState(null);
  const [err, setErr] = useState(null);
  const [focus, setFocus] = useState(null);
  const [tick, setTick] = useState(0);
  const [showTable, setShowTable] = useState(params.get('table') === '1');
  const [showFilters, setShowFilters] = useState(window.innerWidth > 900);
  const [geo, setGeo] = useState('');
  const [geoMsg, setGeoMsg] = useState('');
  const selectedId = params.get('site') ? Number(params.get('site')) : null;

  const select = useCallback((id) => {
    setParams((p) => { const n = new URLSearchParams(p); id ? n.set('site', id) : n.delete('site'); return n; },
      { replace: true });
  }, [setParams]);

  useEffect(() => {
    let alive = true;
    Promise.all([api.get(`/api/sites/map?${query}`), api.get(`/api/dashboard/summary?${query}`)])
      .then(([m, s]) => { if (alive) { setPoints({ ...m, q: query }); setSummary(s); setErr(null); } })
      .catch((e) => alive && setErr(e));
    return () => { alive = false; };
  }, [query, tick]);

  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), REFRESH_MS);
    return () => clearInterval(t);
  }, []);

  const onRow = (s) => {
    select(s.id);
    if (s.latitude != null) setFocus({ lat: s.latitude, lon: s.longitude, zoom: 14, t: Date.now() });
  };

  const geoSearch = async (e) => {
    e.preventDefault();
    setGeoMsg('');
    const v = geo.trim();
    if (!v) return;
    const m = v.match(COORD_RX);
    if (m) {
      const lat = parseFloat(m[1].replace(',', '.')); const lon = parseFloat(m[2].replace(',', '.'));
      setFocus({ lat, lon, zoom: 14, t: Date.now() });
      return;
    }
    const w = ref?.wilayas.find((x) => norm(x.name).startsWith(norm(v)) || String(x.code) === v);
    if (w) { setFocus({ lat: w.center_lat, lon: w.center_lon, zoom: 9, t: Date.now() }); return; }
    try {
      const r = await api.get(`/api/sites?q=${encodeURIComponent(v)}&page_size=1`);
      if (r.items.length) onRow(r.items[0]);
      else setGeoMsg('Aucun lieu ni site trouvé.');
    } catch (ex) { setGeoMsg(ex.message); }
  };

  const failing = summary?.omc_sources.filter((o) => o.health === 'FAILED' || o.health === 'LATE') || [];
  const collectorDown = summary && summary.omc_sources.some((o) => o.enabled && o.connector_type !== 'manual_csv')
    && !summary.services.some((x) => x.service === 'collector' && x.alive);
  return (
    <div className={`map-page${showFilters ? '' : ' no-filters'}${selectedId ? ' with-detail' : ''}${showTable ? ' with-table' : ''}`}>
      {showFilters && <FiltersPanel filters={filters} setFilters={setFilters} />}
      <div className="map-main">
        <div className="toolbar">
          <button type="button" className="btn btn-ghost" onClick={() => setShowFilters((x) => !x)}
            aria-expanded={showFilters}>☰ Filtres</button>
          <form onSubmit={geoSearch} className="geo">
            <input type="search" value={geo} onChange={(e) => setGeo(e.target.value)}
              placeholder="Aller à : wilaya, code site ou « 36.75, 3.06 »" aria-label="Recherche géographique" />
            <button type="submit" className="btn">Aller</button>
            {geoMsg && <span className="muted small">{geoMsg}</span>}
          </form>
          <div className="spacer" />
          <span className="muted small" title="Rafraîchissement automatique">
            {points ? `Mis à jour ${fmtDate(points.generated_at)}` : ''}
          </span>
          <button type="button" className="btn btn-ghost" onClick={() => setTick((x) => x + 1)}>↻</button>
          <button type="button" className={`btn btn-ghost${showTable ? ' on' : ''}`} onClick={() => setShowTable((x) => !x)}>
            {showTable ? 'Masquer le tableau' : 'Tableau'}
          </button>
        </div>
        <KpiStrip totals={summary?.totals} active={filters.status}
          onPick={(st) => setFilters((f) => ({ ...f, status: st }))} />
        {failing.length > 0 && (
          <div className="alert alert-warn">
            Collecte en défaut : {failing.map((o) => `${o.code} (${o.health === 'FAILED' ? 'échec' : 'en retard'})`).join(', ')}.
            Les états de ces sources peuvent être obsolètes ; ils passeront à « inconnu » à l'expiration du délai de fraîcheur.
          </div>
        )}
        {collectorDown && (
          <div className="alert alert-error">
            Le service de collecte ne répond plus : aucune donnée OMC n'est mise à jour. Les sites passeront
            à l'état « inconnu » à l'expiration du délai de fraîcheur. Prévenir l'administrateur.
          </div>
        )}
        {points?.truncated && <div className="alert alert-warn">Affichage limité : affinez les filtres.</div>}
        {points?.without_coordinates > 0 && (
          <div className="alert alert-info">{points.without_coordinates} site(s) sans coordonnées GPS ne sont pas affichés sur la carte (visibles dans le tableau).</div>
        )}
        <ErrorBox error={err} onRetry={() => setTick((x) => x + 1)} />
        <div className="map-area">
          <MapView rows={points?.rows} onSelect={select} focus={focus} fitKey={points?.q}
            reference={ref} selectedId={selectedId} />
        </div>
        {showTable && (
          <SitesTable filters={filters} onRowClick={onRow} selectedId={selectedId} refreshKey={tick} />
        )}
      </div>
      {selectedId && (
        <SiteDetail siteId={selectedId} refreshKey={tick} onClose={() => select(null)}
          onCenter={(s) => setFocus({ lat: s.latitude, lon: s.longitude, zoom: 15, t: Date.now() })} />
      )}
    </div>
  );
}
