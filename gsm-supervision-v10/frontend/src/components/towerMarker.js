// Marqueur « pylône 3D » des sites : tour en treillis vue en perspective (deux faces ombrées),
// ombre portée au sol, panneaux d'antennes colorés par technologie et balise d'état au sommet.
//
// Dessin sur le canevas Leaflet (preferCanvas) à partir d'images pré-calculées (sprites mis en
// cache par état / technologies / zoom) : des dizaines de milliers de sites restent fluides.
import L from './leaflet-setup';
import { STATUS, TECH } from '../lib/constants';

const W = 24;            // largeur du dessin de référence (px CSS, échelle 1)
const H = 34;            // hauteur
const BASE = [12, 29];   // point d'ancrage = pied du pylône (position GPS du site)
const DPR = Math.min(3, Math.ceil(window.devicePixelRatio || 1));
const cache = new Map();

function rgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
// t > 0 éclaircit (vers le blanc), t < 0 assombrit (vers le noir)
function shade(hex, t) {
  const c = rgb(hex).map((v) => Math.round(t >= 0 ? v + (255 - v) * t : v * (1 + t)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function poly(ctx, pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (const p of pts.slice(1)) ctx.lineTo(p[0], p[1]);
  ctx.closePath();
}

function drawTower(ctx, { status, techs, stale }) {
  const unsup = status === 'UNSUPERVISED';
  const body = unsup ? '#e3e7ed' : (STATUS[status] || STATUS.UNKNOWN).color;
  const edge = unsup ? '#8a94a6' : shade(body, -0.55);
  ctx.globalAlpha = stale ? 0.5 : 1;

  // Halo au sol pour les sites en panne (repérables même partiellement masqués)
  if (status === 'DOWN') {
    const g = ctx.createRadialGradient(12, 29, 1, 12, 29, 11);
    g.addColorStop(0, 'rgba(220,38,38,.55)');
    g.addColorStop(1, 'rgba(220,38,38,0)');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.ellipse(12, 29, 11, 4.5, 0, 0, Math.PI * 2); ctx.fill();
  }
  // Ombre portée
  const sh = ctx.createRadialGradient(13.5, 29.3, 0.5, 13.5, 29.3, 8);
  sh.addColorStop(0, 'rgba(15,23,42,.38)');
  sh.addColorStop(1, 'rgba(15,23,42,0)');
  ctx.fillStyle = sh;
  ctx.beginPath(); ctx.ellipse(13.5, 29.3, 8.5, 2.8, 0, 0, Math.PI * 2); ctx.fill();

  // Tour : tronc de pyramide vu de trois quarts (face gauche éclairée, face droite dans l'ombre)
  const bl = [5, 27.6]; const bc = [12, 29.3]; const br = [19, 27.6];
  const tl = [10, 8.6]; const tc = [12, 9.2]; const tr = [14, 8.6];
  const left = [bl, bc, tc, tl];
  const right = [bc, br, tr, tc];
  poly(ctx, left); ctx.fillStyle = unsup ? '#f6f8fa' : shade(body, 0.12); ctx.fill();
  poly(ctx, right); ctx.fillStyle = unsup ? '#cfd5dd' : shade(body, -0.28); ctx.fill();

  // Treillis (croisillons) sur les deux faces
  ctx.lineWidth = 0.7;
  ctx.strokeStyle = unsup ? 'rgba(110,120,138,.55)' : 'rgba(255,255,255,.6)';
  const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  for (const [a0, a1, b0, b1] of [[bl, tl, bc, tc], [bc, tc, br, tr]]) {
    const levels = [0, 0.36, 0.66, 1];
    ctx.beginPath();
    for (let i = 0; i < levels.length - 1; i += 1) {
      const p = lerp(a0, a1, levels[i]); const q = lerp(b0, b1, levels[i + 1]);
      const r = lerp(b0, b1, levels[i]); const s = lerp(a0, a1, levels[i + 1]);
      ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]);
      ctx.moveTo(r[0], r[1]); ctx.lineTo(s[0], s[1]);
      if (i) { ctx.moveTo(p[0], p[1]); ctx.lineTo(r[0], r[1]); }
    }
    ctx.stroke();
  }
  // Arêtes
  ctx.lineWidth = 0.9;
  ctx.strokeStyle = edge;
  if (status === 'UNKNOWN') ctx.setLineDash([2.2, 1.4]);
  ctx.beginPath();
  ctx.moveTo(...bl); ctx.lineTo(...tl); ctx.moveTo(...bc); ctx.lineTo(...tc); ctx.moveTo(...br); ctx.lineTo(...tr);
  ctx.moveTo(...bl); ctx.lineTo(...bc); ctx.lineTo(...br);
  ctx.stroke();
  ctx.setLineDash([]);

  // Mât et plateforme
  ctx.fillStyle = edge;
  ctx.fillRect(11.5, 3.2, 1, 6);
  poly(ctx, [[8.6, 8.4], [12, 9.6], [15.4, 8.4], [12, 7.4]]);
  ctx.fillStyle = unsup ? '#c2c9d3' : shade(body, -0.45); ctx.fill();

  // Antennes sectorielles : une couleur par technologie (jusqu'à trois panneaux)
  const list = (techs || []).length ? [...techs].sort().slice(-3) : ['2G'];
  const cols = [list[0], list[Math.min(1, list.length - 1)], list[list.length - 1]];
  const panels = [[8.2, 4.1, 2.3, 5.6, 0.18], [10.85, 3.6, 2.3, 5.9, 0], [13.5, 4.1, 2.3, 5.6, -0.3]];
  panels.forEach(([x, y, w, h, t], i) => {
    const c = unsup ? '#9aa3b2' : (TECH[cols[i]] || TECH['2G']).color;
    ctx.fillStyle = shade(c, t);
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(x, y, w, h, 0.8) : ctx.rect(x, y, w, h);
    ctx.fill();
    ctx.lineWidth = 0.5; ctx.strokeStyle = 'rgba(255,255,255,.7)'; ctx.stroke();
  });

  // Balise d'état au sommet
  if (!unsup) {
    if (status === 'DOWN' || status === 'DEGRADED') {
      const g = ctx.createRadialGradient(12, 2.4, 0.5, 12, 2.4, 4.2);
      g.addColorStop(0, shade(body, 0.1));
      g.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(12, 2.4, 4.2, 0, Math.PI * 2); ctx.fill();
    }
    ctx.beginPath(); ctx.arc(12, 2.4, 1.9, 0, Math.PI * 2);
    ctx.fillStyle = body; ctx.fill();
    ctx.lineWidth = 0.8; ctx.strokeStyle = '#fff'; ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

// Taille selon le zoom : discret vu de loin, détaillé de près
export function zoomScale(z) {
  if (z <= 6) return 0.6;
  if (z <= 8) return 0.75;
  if (z <= 11) return 1;
  if (z <= 13) return 1.25;
  if (z <= 15) return 1.5;
  return 1.8;
}

export function towerSprite(style, scale) {
  const s = Math.round(scale * (style.status === 'DOWN' ? 1.15 : style.status === 'UNSUPERVISED' ? 0.8 : 1) * 100) / 100;
  const key = `${style.status}|${(style.techs || []).join(',')}|${style.stale ? 1 : 0}|${s}`;
  let sp = cache.get(key);
  if (!sp) {
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(W * s * DPR);
    canvas.height = Math.ceil(H * s * DPR);
    const ctx = canvas.getContext('2d');
    ctx.scale(s * DPR, s * DPR);
    drawTower(ctx, style);
    sp = { canvas, w: W * s, h: H * s, ax: BASE[0] * s, ay: BASE[1] * s };
    cache.set(key, sp);
  }
  return sp;
}

// Image du pylône pour la légende
export function towerDataUrl(status, techs = ['2G', '3G', '4G']) {
  return towerSprite({ status, techs, stale: false }, 1).canvas.toDataURL();
}

// Marqueur Leaflet (rendu canevas) : hérite de CircleMarker pour rester compatible avec le
// regroupement (markercluster) ; seuls le dessin, l'emprise et la détection du survol changent.
export const TowerMarker = L.CircleMarker.extend({
  _sprite() {
    return towerSprite(this.options.tower, zoomScale(this._map ? this._map.getZoom() : 10));
  },
  _updateBounds() {
    const s = this._sprite();
    this._spr = s;
    this._pxBounds = L.bounds(this._point.subtract([s.ax, s.ay]), this._point.add([s.w - s.ax, s.h - s.ay]));
  },
  _updatePath() {
    const r = this._renderer;
    if (!r._drawing || this._empty() || !this._spr) return;
    const s = this._spr; const p = this._point;
    r._ctx.drawImage(s.canvas, p.x - s.ax, p.y - s.ay, s.w, s.h);
  },
  _empty() {
    return !this._pxBounds || !this._renderer._bounds.intersects(this._pxBounds);
  },
  // Survol / clic : silhouette du pylône (pas le rectangle entier)
  _containsPoint(p) {
    const b = this._pxBounds;
    if (!b || !b.contains(p)) return false;
    const h = b.max.y - b.min.y;
    const rel = (p.y - b.min.y) / h;                       // 0 = sommet, 1 = pied
    const half = ((b.max.x - b.min.x) / 2) * (0.35 + 0.65 * rel) + 2;
    return Math.abs(p.x - (b.min.x + b.max.x) / 2) <= half;
  },
  tooltipOffsetY() {
    return this._spr ? -this._spr.ay + 2 : -20;
  },
});

export const towerMarker = (latlng, tower, options = {}) => new TowerMarker(latlng, { ...options, tower });
