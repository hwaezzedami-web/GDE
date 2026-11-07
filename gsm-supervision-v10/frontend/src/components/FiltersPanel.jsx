import { useEffect, useMemo, useState } from 'react';
import { REF_STATUS, STATUS, STATUS_ORDER, TECHS, VENDORS, VENDOR_LABEL } from '../lib/constants';
import { useReference } from '../lib/reference';

function toggle(list = [], v) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

function Chips({ values, selected = [], onChange, render, className = '' }) {
  return (
    <div className={`chips ${className}`}>
      {values.map((v) => (
        <button key={v} type="button" aria-pressed={selected.includes(v)}
          className={`chip${selected.includes(v) ? ' on' : ''}`} onClick={() => onChange(toggle(selected, v))}>
          {render ? render(v) : v}
        </button>
      ))}
    </div>
  );
}

export default function FiltersPanel({ filters, setFilters, showOutage = true, compact = false }) {
  const ref = useReference();
  const [wq, setWq] = useState('');
  const [q, setQ] = useState(filters.q || '');
  const [commune, setCommune] = useState(filters.commune || '');

  useEffect(() => { setQ(filters.q || ''); }, [filters.q]);
  useEffect(() => { setCommune(filters.commune || ''); }, [filters.commune]);

  // Saisie libre : application différée pour ne pas surcharger l'API
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.q || '') !== q || (filters.commune || '') !== commune) {
        setFilters((f) => ({ ...f, q: q.trim(), commune: commune.trim() }));
      }
    }, 400);
    return () => clearTimeout(t);
  }, [q, commune]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const wilayas = useMemo(() => {
    const all = ref?.wilayas || [];
    const sel = new Set((filters.wilaya || []).map(Number));
    const needle = wq.trim().toLowerCase();
    return all
      .filter((w) => !needle || w.name.toLowerCase().includes(needle) || String(w.code).startsWith(needle))
      .filter((w) => !filters.region?.length || filters.region.includes(w.region) || sel.has(w.code))
      .sort((a, b) => (sel.has(b.code) - sel.has(a.code)) || a.code - b.code);
  }, [ref, wq, filters.wilaya, filters.region]);
  const downOnly = filters.status?.length === 1 && filters.status[0] === 'DOWN';

  return (
    <aside className={`filters${compact ? ' compact' : ''}`} aria-label="Filtres">
      <div className="filters-head">
        <button type="button" className={`btn btn-down${downOnly ? ' on' : ''}`}
          onClick={() => set('status', downOnly ? [] : ['DOWN'])}>
          <i className="dot" style={{ background: STATUS.DOWN.color }} />
          {downOnly ? 'Tous les sites' : 'Sites DOWN uniquement'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => setFilters({})} title="Réinitialiser tous les filtres">Effacer</button>
      </div>

      <label className="field">
        <span>Site (nom ou code)</span>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ex. ALG_0123" maxLength={100} />
      </label>

      <div className="field">
        <span>État</span>
        <Chips values={STATUS_ORDER} selected={filters.status} onChange={(v) => set('status', v)}
          render={(s) => <><i className="dot" style={{ background: STATUS[s].color }} />{STATUS[s].label}</>} />
      </div>

      <div className="field">
        <span>Technologie</span>
        <Chips values={TECHS} selected={filters.tech} onChange={(v) => set('tech', v)}
          render={(t) => <span className={`tech tech-${t}`}>{t}</span>} className="chips-tech" />
      </div>

      <div className="field">
        <span>Équipementier</span>
        <Chips values={VENDORS} selected={filters.vendor} onChange={(v) => set('vendor', v)}
          render={(v) => VENDOR_LABEL[v]} />
      </div>

      <label className="field">
        <span>Référentiel</span>
        <select value={(filters.ref || []).join(',')} onChange={(e) => set('ref', e.target.value ? e.target.value.split(',') : [])}>
          <option value="">En service, arrêts temporaires et sites supervisés</option>
          <option value="ALL">Tous les sites (y compris en projet et démontés)</option>
          {Object.entries(REF_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label} uniquement</option>)}
          <option value="NONE">Hors référentiel (remontés par un OMC seulement)</option>
        </select>
      </label>

      {ref?.drs?.length > 0 && (
        <div className="field">
          <span>Direction régionale</span>
          <Chips values={ref.drs} selected={filters.dr} onChange={(v) => set('dr', v)} />
        </div>
      )}

      <div className="field">
        <span>Région</span>
        <Chips values={ref?.regions || []} selected={filters.region} onChange={(v) => set('region', v)} />
      </div>

      <div className="field">
        <span>Wilaya {filters.wilaya?.length ? <em>({filters.wilaya.length})</em> : null}</span>
        <input type="search" value={wq} onChange={(e) => setWq(e.target.value)} placeholder="Filtrer la liste…" />
        <div className="checklist">
          {wilayas.map((w) => {
            const on = (filters.wilaya || []).map(Number).includes(w.code);
            return (
              <label key={w.code} className={on ? 'on' : ''}>
                <input type="checkbox" checked={on}
                  onChange={() => set('wilaya', toggle((filters.wilaya || []).map(Number), w.code))} />
                <span className="code">{String(w.code).padStart(2, '0')}</span>{w.name}
              </label>
            );
          })}
        </div>
      </div>

      <label className="field">
        <span>Commune</span>
        <input type="search" value={commune} onChange={(e) => setCommune(e.target.value)} maxLength={100} />
      </label>

      <label className="field">
        <span>OMC source</span>
        <select value={filters.omc?.[0] || ''} onChange={(e) => set('omc', e.target.value ? [e.target.value] : [])}>
          <option value="">Toutes</option>
          {(ref?.omc_sources || []).map((o) => (
            <option key={o.code} value={o.code}>{o.code}{o.is_demo ? ' (fictif)' : ''}</option>
          ))}
        </select>
      </label>

      {showOutage && (
        <div className="field">
          <span>Panne détectée entre</span>
          <div className="row2">
            <input type="datetime-local" value={filters.outage_from || ''} aria-label="Début de période"
              onChange={(e) => set('outage_from', e.target.value)} />
            <input type="datetime-local" value={filters.outage_to || ''} aria-label="Fin de période"
              onChange={(e) => set('outage_to', e.target.value)} />
          </div>
        </div>
      )}

      <label className="field check">
        <input type="checkbox" checked={filters.stale === 'true'}
          onChange={(e) => set('stale', e.target.checked ? 'true' : '')} />
        <span>Données périmées uniquement</span>
      </label>
    </aside>
  );
}
