import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, getToken, setAuthErrorHandler, setToken } from './api';

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState(null);

  const logout = useCallback(async (msg) => {
    if (!msg && getToken()) { try { await api.post('/api/auth/logout'); } catch { /* ignore */ } }
    setToken(null);
    setUser(null);
    setNotice(msg || null);
  }, []);

  useEffect(() => {
    setAuthErrorHandler((status, detail) => {
      if (status === 401) { setToken(null); setUser(null); setNotice(detail); }
      if (status === 403) setUser((u) => (u ? { ...u, must_change_password: true } : u));
    });
    if (!getToken()) { setReady(true); return; }
    api.get('/api/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  // Expiration du jeton : déconnexion propre à l'échéance
  useEffect(() => {
    if (!user?.expires_at) return undefined;
    const ms = new Date(user.expires_at).getTime() - Date.now();
    const t = setTimeout(() => logout('Session expirée, veuillez vous reconnecter.'), Math.max(ms, 0));
    return () => clearTimeout(t);
  }, [user?.expires_at, logout]);

  const login = useCallback(async (username, password) => {
    const r = await api.post('/api/auth/login', { username, password });
    setToken(r.access_token);
    setNotice(null);
    setUser({ ...r.user, expires_at: r.expires_at });
    return r.user;
  }, []);

  const changePassword = useCallback(async (current_password, new_password) => {
    const r = await api.post('/api/auth/change-password', { current_password, new_password });
    setToken(r.access_token);
    setUser({ ...r.user, expires_at: r.expires_at });
  }, []);

  const value = useMemo(() => ({
    user, ready, notice, login, logout, changePassword,
    isAdmin: user?.role === 'ADMIN',
    isSupervisor: user?.role === 'ADMIN' || user?.role === 'SUPERVISOR',
    canExport: !!user?.can_export,
  }), [user, ready, notice, login, logout, changePassword]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
