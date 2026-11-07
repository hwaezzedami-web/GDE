import { useEffect, useRef } from 'react';
import L from './leaflet-setup';
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import { BASEMAP, REF_STATUS, STATUS, TECH, TILE_ATTRIBUTION, TILE_URL } from '../lib/constants';
import { api } from '../lib/api';
import { towerDataUrl, towerMarker } from './towerMarker';

const ALGERIA_BOUNDS = [[18.9, -8.7], [37.2, 12.0]];
// Teintes très claires par région (fond hors ligne), pour se repérer sans gêner la lecture des états
const REGION_FILL = { Centre: '#fbf8f0', Est: '#f6f8f1', Ouest: '#f8f5f2', Sud: '#fbf6ea' };
const RANK = { DOWN: 3, DEGRADED: 2, UNKNOWN: 1, UP: 0, UNSUPERVISED: -1 };

const OFFLINE_ATTRIBUTION = 'Limites des wilayas : &copy; contributeurs OpenStreetMap (ODbL) · Pays voisins : Natural Earth';
const BASE_KEY = 'gsm.basemap';
const readBase = () => { try { return localStorage.getItem(BASE_KEY); } catch { return null; } };
const saveBase = (v) => { try { localStorage.setItem(BASE_KEY, v); } catch { /* ignore */ } };

function clusterIcon(cluster) {
  const kids = cluster.getAllChildMarkers();
  const c = { DOWN: 0, DEGRADED: 0, UNKNOWN: 0, UP: 0, UNSUPERVISED: 0 };
  let worst = 'UNSUPERVISED';
  for (const m of kids) {
    const s = m.options.status;
    c[s] += 1;
    if (RANK[s] > RANK[worst]) worst = s;
  }
  const n = kids.length;
  const size = n < 50 ? 34 : n < 500 ? 42 : 52;
  const badge = c.DOWN ? `<b class="cl-down" title="${c.DOWN} DOWN">${c.DOWN}</b>` : '';
  return L.divIcon({
    html: `<div class="cl cl-${worst}" style="width:${size}px;height:${size}px"><span>${n}</span>${badge}</div>`,
    className: 'cl-wrap',
    iconSize: [size, size],
  });
}

export default function MapView({ rows, onSelect, focus, fitKey, reference, selectedId }) {
  const el = useRef(null);
  const mapRef = useRef(null);
  const clusterRef = useRef(null);
  const markersRef = useRef(new Map());
  const highlightRef = useRef(null);
  const lastFit = useRef(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Initialisation unique de la carte
  useEffect(() => {
    const map = L.map(el.current, { preferCanvas: true, zoomControl: true, worldCopyJump: false, minZoom: 4, maxZoom: 18 });
    map.fitBounds(ALGERIA_BOUNDS);
    // Fonds de carte : tuiles en ligne, ou carte de l'Algérie embarquée (fonctionne sans Internet)
    map.createPane('basemap').style.zIndex = 150;
    map.createPane('borders').style.zIndex = 380;
    map.getPane('borders').style.pointerEvents = 'none';
    // Les serveurs OpenStreetMap refusent les tuiles sans en-tête Referer (« Access blocked »)
    const online = L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 18,
      referrerPolicy: 'strict-origin-when-cross-origin' });
    const offline = L.layerGroup([], { attribution: OFFLINE_ATTRIBUTION });
    offline.getAttribution = () => OFFLINE_ATTRIBUTION;
    const bases = { 'Plan OpenStreetMap': online, 'Algérie (hors ligne)': offline };
    const setOfflineClass = () => el.current?.classList.toggle('offline-base', map.hasLayer(offline));
    map.on('baselayerchange', (e) => {
      setOfflineClass();
      if (!autoSwitch) saveBase(e.layer === offline ? 'offline' : 'osm');
    });
    let autoSwitch = false;   // une bascule automatique n'est pas un choix de l'utilisateur
    const pref = readBase() || (BASEMAP === 'offline' ? 'offline' : 'osm');
    (pref === 'offline' ? offline : online).addTo(map);
    setOfflineClass();
    const switchOffline = () => {
      if (!mapRef.current || !map.hasLayer(online)) return;
      autoSwitch = true;
      map.removeLayer(online);
      offline.addTo(map);
      autoSwitch = false;
      setOfflineClass();
      try { sessionStorage.setItem('gsm.tiles', 'ko'); } catch { /* ignore */ }
      map.fire('gsm:offline-fallback');
    };
    if (pref !== 'offline' && BASEMAP !== 'osm') {
      // Bascule automatique si les tuiles ne se chargent pas (réseau sans accès Internet) ;
      // le résultat est mémorisé pour la session afin de ne pas réafficher un fond vide.
      let known = null;
      try { known = sessionStorage.getItem('gsm.tiles'); } catch { /* ignore */ }
      if (known === 'ko') {
        autoSwitch = true; map.removeLayer(online); offline.addTo(map); autoSwitch = false; setOfflineClass();
      } else {
        let ok = 0; let ko = 0;
        online.on('tileload', () => { ok += 1; try { sessionStorage.setItem('gsm.tiles', 'ok'); } catch { /* ignore */ } });
        online.on('tileerror', () => { ko += 1; if (ok === 0 && ko >= 3) switchOffline(); });
        setTimeout(() => { if (ok === 0) switchOffline(); }, 6000);
      }
    }
    const cluster = L.markerClusterGroup({
      chunkedLoading: true,
      chunkInterval: 120,
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      disableClusteringAtZoom: 13,
      maxClusterRadius: (z) => (z < 7 ? 60 : z < 10 ? 45 : 30),
      iconCreateFunction: clusterIcon,
    });
    map.addLayer(cluster);
    const labels = L.layerGroup();
    const borders = L.layerGroup();
    L.control.layers(bases, { 'Limites des wilayas': borders, 'Noms des wilayas': labels },
      { collapsed: true, position: 'topright' }).addTo(map);
    const notice = L.control({ position: 'topright' });
    notice.onAdd = () => {
      const d = L.DomUtil.create('div', 'map-notice');
      d.textContent = 'Fond en ligne inaccessible : carte de l’Algérie hors ligne affichée.';
      setTimeout(() => d.remove(), 10000);
      return d;
    };
    map.on('gsm:offline-fallback', () => notice.addTo(map));
    L.control.scale({ imperial: false }).addTo(map);

    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = () => {
      const d = L.DomUtil.create('div', 'legend');
      const open = window.innerWidth > 900 ? ' open' : '';
      d.innerHTML = `<details${open}><summary>Légende</summary><strong>Couleur du pylône = état</strong>${Object.entries(STATUS).map(([k, s]) =>
        `<div class="legend-row"><img class="legend-tower" alt="" src="${towerDataUrl(k)}">${s.long}</div>`).join('')}
        <strong>Antennes = technologies du site</strong><div class="legend-tech">${Object.entries(TECH).map(([t, v]) =>
        `<span><i class="ant" style="background:${v.color}"></i>${t}</span>`).join('')}</div></details>`;
      L.DomEvent.disableClickPropagation(d);
      return d;
    };
    legend.addTo(map);

    const zoomClass = () => el.current?.classList.toggle('z-low', map.getZoom() < 7);
    map.on('zoomend', zoomClass);
    zoomClass();
    mapRef.current = map;
    clusterRef.current = cluster;
    highlightRef.renderer = L.svg({ padding: 0.2 });
    map._gsm = { labels, borders, offline };
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(el.current);
    return () => { ro.disconnect(); map.remove(); mapRef.current = null; };
  }, []);

  // Couches de référence : noms et limites des wilayas
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !reference) return;
    const { labels, borders, offline } = map._gsm;
    labels.clearLayers();
    for (const w of reference.wilayas || []) {
      if (w.center_lat == null) continue;
      L.marker([w.center_lat, w.center_lon], {
        interactive: false, keyboard: false,
        icon: L.divIcon({ className: 'wl-label', html: `<span>${w.name}</span>`, iconSize: [120, 16] }),
      }).addTo(labels);
    }
    if (!map.hasLayer(labels)) labels.addTo(map);
    const baseRenderer = L.svg({ pane: 'basemap', padding: 0.5 });
    const borderRenderer = L.svg({ pane: 'borders', padding: 0.5 });
    offline.clearLayers();
    fetch('/geo/voisins.geojson').then((r) => (r.ok ? r.json() : null)).then((gj) => {
      if (!gj) return;
      L.geoJSON(gj, { pane: 'basemap', renderer: baseRenderer, interactive: false,
        style: { color: '#b9b3a6', weight: 0.8, fillColor: '#e4e0d6', fillOpacity: 1 } }).addTo(offline);
    }).catch(() => {});
    if ((reference.wilayas || []).some((w) => w.has_boundary)) {
      api.get('/api/reference/wilaya-boundaries').then((gj) => {
        L.geoJSON(gj, { pane: 'basemap', renderer: baseRenderer, interactive: false,
          style: (f) => ({ stroke: false, fillColor: REGION_FILL[f.properties.region] || '#fbfaf6', fillOpacity: 1 }),
        }).addTo(offline);
        borders.clearLayers();
        L.geoJSON(gj, { pane: 'borders', renderer: borderRenderer, interactive: false,
          style: { color: '#5b6b80', weight: 1, fill: false, opacity: 0.75, dashArray: '5 3' } }).addTo(borders);
        borders.addTo(map);
      }).catch(() => {});
    }
  }, [reference]);

  // Marqueurs (reconstruits à chaque nouveau jeu de données)
  useEffect(() => {
    const cluster = clusterRef.current;
    if (!cluster || !rows) return;
    cluster.clearLayers();
    const markers = new Map();
    const layers = rows.map(([id, lat, lon, status, vendor, techs, name, ext, , stale, dr, refSt]) => {
      // Pylône 3D : couleur = état, antennes = technologies, balise au sommet ; creux et gris si non supervisé
      const m = towerMarker([lat, lon], {
        status, techs: (techs || '').split(',').filter(Boolean).sort(), stale: !!stale,
      }, { status });
      m.on('mouseover', () => {
        if (!m.getTooltip()) {
          const esc = (v) => String(v ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
          const ref = refSt ? `<br><span style="color:#64748b">${esc(dr || '')}${dr ? ' · ' : ''}${esc(REF_STATUS[refSt]?.label || refSt)}</span>` : '';
          m.bindTooltip(`<b>${esc(name)}</b><br>${esc(ext)}${vendor && vendor !== 'UNKNOWN' ? ` · ${esc(vendor)}` : ''}<br>${
            esc((techs || '').replaceAll(',', ' · '))} — ${STATUS[status]?.label || status}${
            stale ? ' (données périmées)' : ''}${ref}`, { direction: 'top', offset: [0, -20] });
        }
        m.getTooltip().options.offset = L.point(0, m.tooltipOffsetY());   // au-dessus du pylône (taille selon le zoom)
        m.openTooltip();
      });
      m.on('click', () => onSelectRef.current?.(id));
      markers.set(id, m);
      return m;
    });
    cluster.addLayers(layers);
    markersRef.current = markers;
  }, [rows]);

  // Recentrage quand les filtres changent (pas lors des rafraîchissements)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !rows || fitKey === lastFit.current) return;
    lastFit.current = fitKey;
    if (!fitKey) { map.fitBounds(ALGERIA_BOUNDS); return; }
    if (rows.length) {
      const b = L.latLngBounds(rows.map((r) => [r[1], r[2]]));
      map.fitBounds(b.pad(0.15), { maxZoom: 13 });
    }
  }, [rows, fitKey]);

  // Centrage sur un site (clic dans le tableau, recherche)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    if (focus.bounds) { map.flyToBounds(focus.bounds, { maxZoom: 11 }); return; }
    if (focus.lat == null) return;
    map.flyTo([focus.lat, focus.lon], Math.max(map.getZoom(), focus.zoom || 14), { duration: 0.8 });
  }, [focus]);

  // Mise en évidence du site sélectionné
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (highlightRef.current) { highlightRef.current.remove(); highlightRef.current = null; }
    const m = selectedId != null ? markersRef.current.get(selectedId) : null;
    if (m) {
      highlightRef.current = L.circleMarker(m.getLatLng(), {
        radius: 16, color: '#0f172a', weight: 2.5, fill: false, interactive: false, className: 'pulse',
        renderer: highlightRef.renderer,
      }).addTo(map);
    }
  }, [selectedId, rows]);

  return <div ref={el} className="map" role="application" aria-label="Carte des sites GSM" />;
}
