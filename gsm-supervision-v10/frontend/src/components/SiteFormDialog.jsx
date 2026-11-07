import { useEffect, useMemo, useRef, useState } from 'react';
import Dialog from './Dialog';
import { ErrorBox } from './ui';
import L from './leaflet-setup';
import { api } from '../lib/api';
import { BASEMAP, REF_STATUS, TECHS, TILE_ATTRIBUTION, TILE_URL } from '../lib/constants';
import { useReference } from '../lib/reference';

const ALGERIA = [[18.9, -8.7], [37.2, 12.0]];
let boundariesCache = null;
// Repère déplaçable (dessiné en CSS : pas d'image externe à charger)
const PIN = L.divIcon({ className: 'pos-pin', html: '<span></span>', iconSize: [26, 32], iconAnchor: [13, 29] });

// Petite carte de positionnement : clic pour placer le site, marqueur déplaçable
function PositionPicker({ lat, lon, onChange, code }) {
  const el = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const cb = useRef(onChange);
  cb.current = onChange;
  cb.code = code;

  useEffect(() => {
    const map = L.map(el.current, { zoomControl: true, attributionControl: false, minZoom: 4, maxZoom: 18 });
    let tilesOk = BASEMAP !== 'offline';
    try { if (sessionStorage.getItem('gsm.tiles') === 'ko') tilesOk = false; } catch { /* ignore */ }
    if (tilesOk) {
      L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 18, referrerPolicy: 'strict-origin-when-cross-origin' }).addTo(map);
    }
    const drawBoundaries = (gj) => L.geoJSON(gj, { interactive: false,
      style: { color: '#5b6b80', weight: 1, dashArray: '4 3', fillColor: '#fbf8f0', fillOpacity: tilesOk ? 0 : 1 } }).addTo(map);
    if (boundariesCache) drawBoundaries(boundariesCache);
    else api.get('/api/reference/wilaya-boundaries').then((gj) => { boundariesCache = gj; if (mapRef.current) drawBoundaries(gj); }).catch(() => {});
    map.on('click', (e) => cb.current(+e.latlng.lat.toFixed(6), +e.latlng.lng.toFixed(6)));
    // Sites voisins (référentiel et OMC) pour éviter les doublons et situer le site
    const near = L.layerGroup().addTo(map);
    let seq = 0;
    const loadNear = () => {
      if (map.getZoom() < 11) { near.clearLayers(); return; }
      const b = map.getBounds();
      const n = ++seq;
      api.get(`/api/sites/map?ref=ALL&bbox=${[b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((x) => x.toFixed(5)).join(',')}`)
        .then((r) => {
          if (n !== seq || !mapRef.current) return;
          near.clearLayers();
          const f = r.fields;
          for (const row of r.rows.slice(0, 1500)) {
            const o = Object.fromEntries(f.map((k, i) => [k, row[i]]));
            if (o.external_id === cb.code) continue;
            L.circleMarker([o.lat, o.lon], { radius: 4, weight: 1.5, color: '#475569', fillColor: '#fff', fillOpacity: 1 })
              .bindTooltip(`${o.external_id} · ${o.name}`, { direction: 'top' }).addTo(near);
          }
        }).catch(() => {});
    };
    map.on('moveend', loadNear);
    mapRef.current = map;
    // La fenêtre vient de s'ouvrir : la taille du conteneur n'est connue qu'après la mise en page
    const t = setTimeout(() => { map.invalidateSize(); if (!markerRef.current) map.fitBounds(ALGERIA); }, 60);
    return () => { clearTimeout(t); map.remove(); mapRef.current = null; markerRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const valid = Number.isFinite(lat) && Number.isFinite(lon);
    if (!valid) {
      if (markerRef.current) { markerRef.current.remove(); markerRef.current = null; }
      if (!map._loaded) map.fitBounds(ALGERIA);
      return;
    }
    if (!markerRef.current) {
      markerRef.current = L.marker([lat, lon], { icon: PIN, draggable: true, keyboard: true, title: 'Position du site', zIndexOffset: 1000 }).addTo(map);
      markerRef.current.on('dragend', (e) => { const p = e.target.getLatLng(); cb.current(+p.lat.toFixed(6), +p.lng.toFixed(6)); });
      map.setView([lat, lon], Math.max(map._loaded ? map.getZoom() : 0, 14));
    } else {
      markerRef.current.setLatLng([lat, lon]);
      if (!map.getBounds().contains([lat, lon])) map.panTo([lat, lon]);
    }
  }, [lat, lon]);

  return <div ref={el} className="picker-map" aria-label="Carte : cliquer pour placer le site" />;
}

const EMPTY = { code: '', name: '', latitude: '', longitude: '', wilaya_code: '', commune: '', address: '', dr: '', lifecycle: 'en_air', technologies: [] };

// mode : 'create' (nouveau site), 'edit' (site du référentiel), 'adopt' (site inconnu remonté par un OMC)
export default function SiteFormDialog({ open, mode = 'create', site, options, onClose, onSaved }) {
  const ref = useReference();
  const [f, setF] = useState(EMPTY);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setErr(null);
    if (!site) { setF(EMPTY); return; }
    setF({
      code: site.external_id || '', name: (mode === 'adopt' ? site.name : site.name) || '',
      latitude: site.latitude ?? '', longitude: site.longitude ?? '',
      wilaya_code: site.wilaya_code ?? '', commune: site.commune || '', address: site.address || '', dr: site.dr || '',
      lifecycle: site.lifecycle || (mode === 'adopt' ? 'en_air' : ''),
      technologies: [...(mode === 'adopt' ? site.technologies : site.ref_technologies) || []],
    });
  }, [open, site, mode]);

  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const lat = f.latitude === '' ? NaN : Number(String(f.latitude).replace(',', '.'));
  const lon = f.longitude === '' ? NaN : Number(String(f.longitude).replace(',', '.'));
  const category = useMemo(() => {
    const lc = (f.lifecycle || '').trim().toLowerCase();
    if (!lc) return options?.lifecycle_missing;
    return options?.lifecycles.find((o) => o.value === lc)?.category || 'OTHER';
  }, [f.lifecycle, options]);

  const submit = async (e) => {
    e.preventDefault();
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) { setErr(new Error('Indiquer la position : saisir latitude et longitude, ou cliquer sur la carte.')); return; }
    const body = {
      name: f.name.trim(), latitude: lat, longitude: lon,
      wilaya_code: f.wilaya_code === '' ? null : Number(f.wilaya_code),
      commune: f.commune || null, address: f.address || null, dr: f.dr || null,
      lifecycle: f.lifecycle || null, technologies: f.technologies,
    };
    setBusy(true); setErr(null);
    try {
      const res = mode === 'edit'
        ? await api.put(`/api/site-reference/sites/${site.id}`, body)
        : await api.post('/api/site-reference/sites', { ...body, code: f.code.trim() });
      onSaved?.(res);
    } catch (ex) { setErr(ex); }
    setBusy(false);
  };

  const title = mode === 'edit' ? `Modifier le site ${site?.external_id || ''}`
    : mode === 'adopt' ? `Ajouter au référentiel le site ${site?.external_id || ''}` : 'Nouveau site';
  return (
    <Dialog open={open} onClose={onClose} title={title} wide
      footer={(
        <>
          {mode === 'edit' && site?.ref_source === 'IMPORT' && (
            <span className="small muted foot-note">Les valeurs saisies seront remplacées au prochain import d'un fichier contenant ce site.</span>
          )}
          <button type="button" className="btn btn-ghost" onClick={onClose}>Annuler</button>
          <button type="submit" form="site-form" className="btn" disabled={busy}>{busy ? 'Enregistrement…' : mode === 'edit' ? 'Enregistrer' : 'Ajouter au référentiel'}</button>
        </>
      )}>
      <form id="site-form" className="site-form" onSubmit={submit}>
        <div className="site-form-fields">
          {mode === 'adopt' && (
            <div className="alert alert-info">
              Site remonté par {site?.sources || 'un OMC'} sous le nom « {site?.name} ». Ses équipements, alarmes et son
              historique sont conservés. {Number.isFinite(lat) ? '' : 'L\'OMC ne fournit pas de position : cliquer sur la carte pour la placer.'}
            </div>
          )}
          <div className="form-grid2">
            <label className="field"><span>Code site *</span>
              <input value={f.code} onChange={set('code')} required readOnly={mode !== 'create'} maxLength={60}
                pattern="[A-Za-z0-9][A-Za-z0-9_.\/\-]*" title="Lettres, chiffres, _ . - /" autoFocus={mode === 'create'} className="mono" /></label>
            <label className="field"><span>Nom du site *</span>
              <input value={f.name} onChange={set('name')} required maxLength={200} autoFocus={mode !== 'create'} /></label>
            <label className="field"><span>Latitude *</span>
              <input value={f.latitude} onChange={set('latitude')} inputMode="decimal" placeholder="36.7525" required /></label>
            <label className="field"><span>Longitude *</span>
              <input value={f.longitude} onChange={set('longitude')} inputMode="decimal" placeholder="3.0420" required /></label>
            <label className="field"><span>Wilaya</span>
              <select value={f.wilaya_code} onChange={set('wilaya_code')}>
                <option value="">Déduite de la position</option>
                {(ref?.wilayas || []).map((w) => <option key={w.code} value={w.code}>{String(w.code).padStart(2, '0')} · {w.name}</option>)}
              </select></label>
            <label className="field"><span>Commune</span><input value={f.commune} onChange={set('commune')} maxLength={120} /></label>
            <label className="field span2"><span>Adresse</span><input value={f.address} onChange={set('address')} maxLength={300} /></label>
            <label className="field"><span>Direction régionale</span>
              <input value={f.dr} onChange={set('dr')} list="dr-list" maxLength={100} placeholder="ex. DR Alger" />
              <datalist id="dr-list">{(options?.drs || []).map((d) => <option key={d} value={d} />)}</datalist></label>
            <label className="field"><span>Cycle de vie {category && <em>→ {REF_STATUS[category]?.label}</em>}</span>
              <input value={f.lifecycle} onChange={set('lifecycle')} list="lc-list" maxLength={80} />
              <datalist id="lc-list">{(options?.lifecycles || []).map((o) => <option key={o.value} value={o.value}>{REF_STATUS[o.category]?.label}</option>)}</datalist></label>
          </div>
          <fieldset className="field techs-field">
            <legend>Technologies</legend>
            <div className="chips">
              {TECHS.map((t) => (
                <label key={t} className={`chip${f.technologies.includes(t) ? ' on' : ''}`}>
                  <input type="checkbox" className="sr-only" checked={f.technologies.includes(t)}
                    onChange={() => setF((x) => ({ ...x, technologies: x.technologies.includes(t) ? x.technologies.filter((y) => y !== t) : [...x.technologies, t].sort() }))} />
                  <span className={`tech tech-${t}`}>{t}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <ErrorBox error={err} />
        </div>
        <div className="site-form-map">
          <PositionPicker lat={lat} lon={lon} code={site?.external_id} onChange={(a, b) => setF((x) => ({ ...x, latitude: a, longitude: b }))} />
          <p className="small muted">Cliquer sur la carte ou déplacer le repère pour ajuster la position. Les cercles sont les sites voisins déjà connus (à partir du zoom 11).</p>
        </div>
      </form>
    </Dialog>
  );
}
