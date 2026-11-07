import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

// Les filtres vivent dans l'URL : partageables, conservés entre la carte,
// le tableau de bord et les alarmes, et restaurés au rechargement.
export const FILTER_KEYS = ['wilaya', 'region', 'commune', 'q', 'vendor', 'tech', 'status', 'omc',
  'outage_from', 'outage_to', 'stale', 'dr', 'ref'];
const LIST_KEYS = new Set(['wilaya', 'region', 'vendor', 'tech', 'status', 'omc', 'dr', 'ref']);

export function useFilters() {
  const [params, setParams] = useSearchParams();

  const filters = useMemo(() => {
    const f = {};
    for (const k of FILTER_KEYS) {
      const v = params.get(k);
      if (v == null || v === '') continue;
      f[k] = LIST_KEYS.has(k) ? v.split(',').filter(Boolean) : v;
    }
    return f;
  }, [params]);

  const setFilters = useCallback((next) => {
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      const merged = typeof next === 'function' ? next(filtersFrom(prev)) : next;
      for (const k of FILTER_KEYS) p.delete(k);
      for (const [k, v] of Object.entries(merged)) {
        if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue;
        p.set(k, Array.isArray(v) ? v.join(',') : v);
      }
      return p;
    }, { replace: true });
  }, [setParams]);

  const query = useMemo(() => toQuery(filters), [filters]);
  const activeCount = Object.keys(filters).length;
  return { filters, setFilters, query, activeCount };
}

function filtersFrom(params) {
  const f = {};
  for (const k of FILTER_KEYS) {
    const v = params.get(k);
    if (v) f[k] = LIST_KEYS.has(k) ? v.split(',') : v;
  }
  return f;
}

export function toQuery(filters, extra = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...filters, ...extra })) {
    if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue;
    if ((k === 'outage_from' || k === 'outage_to') && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v)) {
      p.set(k, new Date(v).toISOString());        // datetime-local (heure locale) -> ISO UTC
    } else {
      p.set(k, Array.isArray(v) ? v.join(',') : v);
    }
  }
  return p.toString();
}
