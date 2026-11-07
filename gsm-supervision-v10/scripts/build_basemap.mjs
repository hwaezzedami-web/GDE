// Génère le fond de carte hors ligne des pays voisins (frontend/public/geo/voisins.geojson)
// à partir de Natural Earth 1:50m (domaine public), distribué par le paquet npm world-atlas.
//
//   npm pack world-atlas@2 topojson-client@3 && tar -xzf … (voir docs/09_CARTOGRAPHIE.md)
//   node scripts/build_basemap.mjs <countries-50m.json> <topojson-client.js> <sortie.geojson>
import fs from 'node:fs';
import { createRequire } from 'node:module';

const [, , topoPath, clientPath, outPath] = process.argv;
const require = createRequire(import.meta.url);
const topojson = require(clientPath);
const topo = JSON.parse(fs.readFileSync(topoPath, 'utf8'));
const all = topojson.feature(topo, topo.objects.countries).features;

const BOX = [-20, 10, 22, 46];                  // emprise utile autour de l'Algérie
const ALGERIA_ID = '012';                        // ISO 3166-1 numérique (dessinée par les wilayas)
const round = (c) => [Math.round(c[0] * 1000) / 1000, Math.round(c[1] * 1000) / 1000];
const bboxOf = (ring) => ring.reduce((b, [x, y]) => [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)], [180, 90, -180, -90]);
const inBox = (b) => !(b[2] < BOX[0] || b[0] > BOX[2] || b[3] < BOX[1] || b[1] > BOX[3]);

const out = [];
for (const f of all) {
  if (f.id === ALGERIA_ID || !f.geometry) continue;
  const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
  const kept = polys.filter((p) => inBox(bboxOf(p[0]))).map((p) => p.map((r) => r.map(round)));
  if (!kept.length) continue;
  out.push({ type: 'Feature', properties: { name: f.properties.name },
    geometry: { type: 'MultiPolygon', coordinates: kept } });
}
fs.writeFileSync(outPath, JSON.stringify({ type: 'FeatureCollection',
  attribution: 'Natural Earth 1:50m (domaine public) via world-atlas', features: out }));
console.log(`${out.length} pays écrits dans ${outPath} (${(fs.statSync(outPath).size / 1024).toFixed(0)} Ko)`);
