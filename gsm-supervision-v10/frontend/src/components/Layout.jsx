import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { REFRESH_MS } from '../lib/constants';

// Badge « anomalies à traiter » (sites inconnus du référentiel, démontés encore actifs…)
function useAnomalyCount(path) {
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = () => api.get('/api/site-reference/anomalies/count').then((r) => alive && setN(r.open)).catch(() => {});
    load();
    const t = setInterval(load, Math.max(REFRESH_MS, 60000));
    return () => { alive = false; clearInterval(t); };
  }, [path]);
  return n;
}

const ROLE = { ADMIN: 'Administrateur', SUPERVISOR: 'Superviseur', VIEWER: 'Consultation' };

export default function Layout() {
  const { user, logout, isSupervisor } = useAuth();
  const loc = useLocation();
  const anomalies = useAnomalyCount(loc.pathname);
  // Conserve les filtres (paramètres d'URL) d'une page à l'autre
  const keep = (path) => {
    const p = new URLSearchParams(loc.search);
    p.delete('site'); p.delete('table');
    const s = p.toString();
    return s ? `${path}?${s}` : path;
  };
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="logo" aria-hidden>◉</span><span className="brand-text">Supervision GSM <span className="muted">Algérie</span></span></div>
        <nav className="nav">
          <NavLink to={keep('/')} end>Carte</NavLink>
          <NavLink to={keep('/dashboard')}>Tableau de bord</NavLink>
          <NavLink to={keep('/alarms')}>Alarmes</NavLink>
          <NavLink to="/referentiel" title={anomalies ? `${anomalies} anomalie(s) de référentiel à traiter` : undefined}>
            Référentiel{anomalies > 0 && <span className="nav-badge">{anomalies > 999 ? '999+' : anomalies}</span>}
          </NavLink>
          {isSupervisor && <NavLink to="/admin">Administration</NavLink>}
        </nav>
        <div className="user">
          <NavLink to="/password" className="user-name" title="Changer le mot de passe">
            {user.full_name || user.username}<small>{ROLE[user.role]}</small>
          </NavLink>
          <button type="button" className="btn btn-ghost" onClick={() => logout()} aria-label="Déconnexion" title="Déconnexion">⏻<span className="logout-text">Déconnexion</span></button>
        </div>
      </header>
      <main className="content"><div key={loc.pathname} className="page-enter"><Outlet /></div></main>
    </div>
  );
}
