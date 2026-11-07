// Client HTTP de l'API. Le jeton de session est conservé en sessionStorage
// (supprimé à la fermeture de l'onglet) et jamais dans localStorage.
const TOKEN_KEY = 'gsm.token';

let onAuthError = () => {};
export const setAuthErrorHandler = (fn) => { onAuthError = fn; };

export const getToken = () => {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
};
export const setToken = (t) => {
  try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
};

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function request(method, path, { body, form, raw } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, 'Serveur injoignable. Vérifiez votre connexion réseau.');
  }
  if (res.status === 401 && !path.startsWith('/api/auth/login')) {
    let detail = 'Session expirée, veuillez vous reconnecter.';
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    onAuthError(401, detail);
    throw new ApiError(401, detail);
  }
  if (res.status === 403) {
    let detail = 'Droits insuffisants.';
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    if (detail.startsWith('Changement de mot de passe')) onAuthError(403, detail);
    throw new ApiError(403, detail);
  }
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const j = await res.json();
      detail = typeof j.detail === 'string' ? j.detail
        : Array.isArray(j.detail) ? j.detail.map((d) => d.msg).join(' ; ') : detail;
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, body) => request('POST', p, { body }),
  put: (p, body) => request('PUT', p, { body }),
  patch: (p, body) => request('PATCH', p, { body }),
  del: (p) => request('DELETE', p),
  form: (p, fields) => {
    const f = new FormData();
    for (const [k, v] of Object.entries(fields)) if (v != null && v !== '') f.append(k, v);
    return request('POST', p, { form: f });
  },
  upload: (p, file) => { const f = new FormData(); f.append('file', file); return request('POST', p, { form: f }); },
  download: async (p) => {
    const res = await request('GET', p, { raw: true });
    const cd = res.headers.get('Content-Disposition') || '';
    const name = (cd.match(/filename="([^"]+)"/) || [])[1] || 'export';
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
};
