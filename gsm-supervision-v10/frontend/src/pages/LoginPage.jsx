import { useState } from 'react';
import { useAuth } from '../lib/auth';

export function LoginPage() {
  const { login, notice } = useAuth();
  const [u, setU] = useState('');
  const [p, setP] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    try { await login(u, p); } catch (ex) { setErr(ex.message); setBusy(false); }
  };
  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="brand-lg"><span className="logo" aria-hidden>◉</span>Supervision GSM<small>Sites radio 2G · 3G · 4G · 5G — Algérie</small></div>
        {notice && <div className="alert alert-warn">{notice}</div>}
        {err && <div className="alert alert-error" role="alert">{err}</div>}
        <label className="field"><span>Identifiant</span>
          <input value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" required autoFocus maxLength={64} /></label>
        <label className="field"><span>Mot de passe</span>
          <input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required maxLength={128} /></label>
        <button type="submit" className="btn btn-block" disabled={busy}>{busy ? 'Connexion…' : 'Se connecter'}</button>
        <p className="small muted">Accès réservé au personnel autorisé. Les connexions sont journalisées.</p>
      </form>
    </div>
  );
}

export function ChangePasswordPage({ forced }) {
  const { changePassword, logout } = useAuth();
  const [cur, setCur] = useState('');
  const [n1, setN1] = useState('');
  const [n2, setN2] = useState('');
  const [err, setErr] = useState('');
  const [ok, setOk] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    if (n1 !== n2) { setErr('Les deux saisies du nouveau mot de passe diffèrent.'); return; }
    try { await changePassword(cur, n1); setOk(true); } catch (ex) { setErr(ex.message); }
  };
  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <h2>Changer le mot de passe</h2>
        {forced && <div className="alert alert-warn">Vous devez définir un nouveau mot de passe avant de continuer.</div>}
        {err && <div className="alert alert-error" role="alert">{err}</div>}
        {ok && <div className="alert alert-info">Mot de passe modifié.</div>}
        <label className="field"><span>Mot de passe actuel</span><input type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" required /></label>
        <label className="field"><span>Nouveau mot de passe</span><input type="password" value={n1} onChange={(e) => setN1(e.target.value)} autoComplete="new-password" required minLength={10} /></label>
        <label className="field"><span>Confirmation</span><input type="password" value={n2} onChange={(e) => setN2(e.target.value)} autoComplete="new-password" required minLength={10} /></label>
        <p className="small muted">10 caractères minimum, combinant au moins 3 types : minuscules, majuscules, chiffres, symboles.</p>
        <button type="submit" className="btn btn-block">Valider</button>
        {forced && <button type="button" className="btn btn-ghost btn-block" onClick={() => logout()}>Se déconnecter</button>}
      </form>
    </div>
  );
}
