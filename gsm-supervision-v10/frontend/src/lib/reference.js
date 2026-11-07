import { useEffect, useState } from 'react';
import { api } from './api';

let cache = null;
let pending = null;

export function loadReference(force = false) {
  if (cache && !force) return Promise.resolve(cache);
  if (!pending || force) {
    pending = api.get('/api/reference').then((r) => { cache = r; return r; }).finally(() => { pending = null; });
  }
  return pending;
}

export function useReference() {
  const [ref, setRef] = useState(cache);
  useEffect(() => { if (!cache) loadReference().then(setRef).catch(() => {}); }, []);
  return ref;
}

export function wilayaName(ref, code) {
  if (code == null) return 'Non renseignée';
  const w = ref?.wilayas?.find((x) => x.code === code);
  return w ? `${String(code).padStart(2, '0')} · ${w.name}` : String(code);
}
