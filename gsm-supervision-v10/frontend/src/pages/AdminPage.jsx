import { useCallback, useEffect, useState } from 'react';
import { ErrorBox, Pagination, StatusBadge } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { VENDORS, VENDOR_LABEL, fmtDate } from '../lib/constants';
import { loadReference } from '../lib/reference';

const CONNECTORS = [
  ['prometheus', 'Prometheus / Alertmanager'],
  ['ericsson', 'Ericsson (profil)'], ['huawei', 'Huawei (profil)'], ['zte', 'ZTE (profil)'],
  ['file_export', "Fichiers d'export génériques"], ['sql_readonly', 'SQL lecture seule'],
  ['manual_csv', 'Import CSV manuel'], ['demo', 'Démonstration (fictif)'],
];

function useLoad(fn, deps) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const reload = useCallback(() => { fn().then((d) => { setData(d); setErr(null); }).catch(setErr); }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(reload, [reload]);
  return [data, err, reload, setErr];
}

// ------------------------------------------------------------------ Sources OMC
// Configurations proposées à la sélection d'un type (sans aucun secret)
const TEMPLATES = {
  prometheus: { url: 'http://prometheus:9090', alarms: { source: 'alertmanager', url: 'http://alertmanager:9093' } },
  file_export: { interface: 'file_export' },
};
const DEFAULT_STALE = { prometheus: 900 };

function SourceForm({ initial, onDone, onCancel }) {
  const [f, setF] = useState(() => ({
    code: '', name: '', vendor: 'HUAWEI', connector_type: 'huawei', enabled: false, poll_interval_s: 300,
    stale_after_s: 1800, integration_validated: false, ...initial,
    config: JSON.stringify(initial?.config || { interface: 'file_export' }, null, 2),
  }));
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  const setType = (e) => {
    const t = e.target.value;
    const untouched = Object.values(TEMPLATES).some((x) => JSON.stringify(x, null, 2) === f.config) || !f.config.trim();
    setF({ ...f, connector_type: t,
      config: untouched && TEMPLATES[t] ? JSON.stringify(TEMPLATES[t], null, 2) : f.config,
      stale_after_s: DEFAULT_STALE[t] ?? f.stale_after_s });
  };
  const submit = async (e) => {
    e.preventDefault();
    let config;
    try { config = JSON.parse(f.config || '{}'); } catch { setErr(new Error('Configuration : JSON invalide')); return; }
    const body = { ...f, config, poll_interval_s: Number(f.poll_interval_s),
      stale_after_s: f.stale_after_s === '' || f.stale_after_s == null ? null : Number(f.stale_after_s) };
    for (const k of ['id', 'is_demo', 'sync_requested_at', 'last_attempt_at', 'last_success_at', 'last_status',
      'last_error', 'consecutive_failures', 'created_at', 'updated_at']) delete body[k];
    try {
      if (initial?.id) await api.put(`/api/admin/omc-sources/${initial.id}`, body);
      else await api.post('/api/admin/omc-sources', body);
      loadReference(true);
      onDone();
    } catch (ex) { setErr(ex); }
  };
  return (
    <form className="card form" onSubmit={submit}>
      <h3>{initial?.id ? `Modifier ${initial.code}` : 'Nouvelle source OMC'}</h3>
      <ErrorBox error={err} />
      <div className="form-grid">
        <label className="field"><span>Code</span><input value={f.code} onChange={set('code')} disabled={!!initial?.id} required pattern="[A-Z0-9_\-]{2,40}" placeholder="HUAWEI-OMC-CENTRE" /></label>
        <label className="field"><span>Nom</span><input value={f.name} onChange={set('name')} required /></label>
        <label className="field"><span>Équipementier</span><select value={f.vendor} onChange={set('vendor')}>{VENDORS.map((v) => <option key={v} value={v}>{VENDOR_LABEL[v]}</option>)}</select></label>
        <label className="field"><span>Connecteur</span><select value={f.connector_type} onChange={setType}>{CONNECTORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="field"><span>Fréquence de collecte (s)</span><input type="number" min="30" max="86400" value={f.poll_interval_s} onChange={set('poll_interval_s')} /></label>
        <label className="field"><span>Données périmées après (s)</span><input type="number" min="60" value={f.stale_after_s ?? ''} onChange={set('stale_after_s')} placeholder="défaut global" /></label>
        <label className="field check"><input type="checkbox" checked={f.enabled} onChange={set('enabled')} /><span>Collecte activée</span></label>
        <label className="field check"><input type="checkbox" checked={f.integration_validated} onChange={set('integration_validated')} /><span>Intégration validée sur données réelles</span></label>
      </div>
      <label className="field"><span>Configuration (JSON, sans aucun secret — voir docs/04_CONNECTEURS_OMC.md)</span>
        <textarea rows={12} className="mono" value={f.config} onChange={set('config')} spellCheck={false} /></label>
      {f.connector_type === 'prometheus' && (
        <p className="small muted">Prometheus : par défaut, les métriques du contrat <code>gsm_ne_oper_status</code> / <code>gsm_ne_info</code> filtrées sur <code>vendor="{(f.vendor || '').toLowerCase()}"</code>. Requêtes PromQL, labels et alarmes personnalisables : voir docs/10_PROMETHEUS.md. Péremption conseillée : fréquence + 5 min (délai de rétention des échantillons de Prometheus) + marge.</p>
      )}
      <p className="small muted">Identifiants : variables d'environnement du service de collecte <code>OMC_{(f.code || '<CODE>').replace(/[^A-Z0-9]/g, '_')}_USERNAME</code>, <code>…_PASSWORD</code>, <code>…_BEARER_TOKEN</code>, <code>…_DSN</code>.</p>
      <div className="actions"><button type="submit" className="btn">Enregistrer</button><button type="button" className="btn btn-ghost" onClick={onCancel}>Annuler</button></div>
    </form>
  );
}

function Sources() {
  const { isAdmin, isSupervisor } = useAuth();
  const [data, err, reload, setErr] = useLoad(() => api.get('/api/admin/omc-sources'), []);
  const [edit, setEdit] = useState(null);
  const sync = async (s) => { try { await api.post(`/api/admin/omc-sources/${s.id}/sync`); reload(); } catch (e) { setErr(e); } };
  if (edit) return <SourceForm initial={edit === 'new' ? null : edit} onCancel={() => setEdit(null)} onDone={() => { setEdit(null); reload(); }} />;
  return (
    <div className="card">
      <div className="table-tools"><ErrorBox error={err} />{isAdmin && <button type="button" className="btn" onClick={() => setEdit('new')}>+ Ajouter une source</button>}
        {data?.some((s) => s.connector_type === 'prometheus') && (
          <span className="actions" style={{ marginLeft: 'auto' }}>
            <a className="btn btn-ghost" href="/prometheus/" target="_blank" rel="noopener noreferrer">Prometheus ↗</a>
            <a className="btn btn-ghost" href="/alertmanager/" target="_blank" rel="noopener noreferrer">Alertmanager ↗</a>
          </span>
        )}
      </div>
      <table className="tbl">
        <thead><tr><th>Code</th><th>Équip.</th><th>Connecteur</th><th>Activée</th><th>Validée</th><th>Fréquence</th><th>Dernier essai</th><th>Dernier succès</th><th>Statut</th><th /></tr></thead>
        <tbody>
          {data?.map((s) => (
            <tr key={s.id}>
              <td><b>{s.code}</b><div className="small muted">{s.name}</div>{s.is_demo && <span className="tag-warn">fictif</span>}</td>
              <td>{VENDOR_LABEL[s.vendor]}</td><td>{s.connector_type}</td>
              <td>{s.enabled ? 'Oui' : 'Non'}</td>
              <td>{s.integration_validated ? 'Oui' : <span className="tag">non</span>}</td>
              <td>{s.poll_interval_s} s</td>
              <td>{fmtDate(s.last_attempt_at)}</td><td>{fmtDate(s.last_success_at)}</td>
              <td>{s.last_status || '—'}{s.consecutive_failures > 0 && <div className="small err">{s.consecutive_failures} échec(s) consécutif(s)</div>}
                {s.last_error && <div className="small err" title={s.last_error}>{s.last_error.slice(0, 120)}</div>}
                {s.sync_requested_at && <div className="small muted">synchro demandée</div>}</td>
              <td className="actions">
                {isSupervisor && s.enabled && s.connector_type !== 'manual_csv' && <button type="button" className="btn btn-ghost" onClick={() => sync(s)}>Synchroniser</button>}
                {isAdmin && <button type="button" className="btn btn-ghost" onClick={() => setEdit(s)}>Modifier</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Runs() {
  const [page, setPage] = useState(1);
  const [data, err] = useLoad(() => api.get(`/api/admin/collection-runs?page=${page}&page_size=50`), [page]);
  return (
    <div className="card">
      <ErrorBox error={err} />
      {data && <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />}
      <table className="tbl tbl-compact">
        <thead><tr><th>Début</th><th>Source</th><th>Statut</th><th>Durée</th><th>Essais</th><th>Sites</th><th>Équip.</th><th>Alarmes</th><th>Rejets</th><th>Erreur / détails</th></tr></thead>
        <tbody>
          {data?.items.map((r) => (
            <tr key={r.id}>
              <td>{fmtDate(r.started_at)}</td><td>{r.omc_code}</td>
              <td className={r.status === 'FAILED' ? 'num-DOWN' : r.status === 'PARTIAL' ? 'num-DEGRADED' : ''}>{r.status}</td>
              <td>{r.duration_s} s</td><td>{r.attempts}</td><td>{r.sites_processed}</td><td>{r.elements_processed}</td>
              <td>{r.alarms_processed}</td><td>{r.records_rejected}</td>
              <td className="small">{r.error_message || (r.details?.messages || []).slice(0, 3).join(' · ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ Règles d'états
const RULE_FIELDS = [
  ['default_stale_after_s', 'Données périmées après (s) — défaut si la source n\'a pas de seuil', 'number'],
  ['down_confirm_s', 'Délai de confirmation d\'une panne DOWN (s)', 'number'],
  ['up_confirm_s', 'Délai de confirmation d\'un retour UP (s)', 'number'],
  ['unknown_elements_policy', 'Équipement à l\'état inconnu sur un site UP', 'select', [['ignore', 'Ignorer (état calculé sur les équipements connus)'], ['degrade', 'Passer le site en DÉGRADÉ']]],
  ['partial_down_is_degraded', 'Panne partielle (une partie des technologies) = DÉGRADÉ', 'bool'],
  ['major_alarm_degrades', 'Alarme critique/majeure active sur un site UP = DÉGRADÉ', 'bool'],
];

function Rules() {
  const { isAdmin } = useAuth();
  const [settings, err, reload, setErr] = useLoad(() => api.get('/api/admin/settings'), []);
  const [rules, rerr, reloadRules] = useLoad(() => api.get('/api/admin/alarm-rules'), []);
  const [draft, setDraft] = useState(null);
  const [msg, setMsg] = useState('');
  const [nr, setNr] = useState({ vendor: 'HUAWEI', alarm_code: '', text_pattern: '', effect: 'DOWN', scope: 'ELEMENT', note: '' });
  useEffect(() => { if (settings) setDraft(settings.status_rules); }, [settings]);

  const save = async (e) => {
    e.preventDefault();
    try { await api.put('/api/admin/settings/status_rules', draft); setMsg('Règles enregistrées et appliquées.'); reload(); } catch (ex) { setErr(ex); }
  };
  const addRule = async (e) => {
    e.preventDefault();
    try {
      await api.post('/api/admin/alarm-rules', { ...nr, alarm_code: nr.alarm_code || null, text_pattern: nr.text_pattern || null });
      setNr({ ...nr, alarm_code: '', text_pattern: '', note: '' }); reloadRules();
    } catch (ex) { setErr(ex); }
  };
  const act = async (fn) => { try { await fn(); reloadRules(); } catch (ex) { setErr(ex); } };

  return (
    <div className="stack">
      <ErrorBox error={err || rerr} />
      {draft && (
        <form className="card form" onSubmit={save}>
          <h3>Règles de calcul des états</h3>
          <p className="small muted">Une perte de connexion avec un OMC ne met jamais un site DOWN : ses données vieillissent et passent « inconnu » après le délai de péremption.</p>
          <div className="form-grid">
            {RULE_FIELDS.map(([k, label, type, opts]) => (
              <label key={k} className={`field${type === 'bool' ? ' check' : ''}`}>
                {type === 'bool' && <input type="checkbox" disabled={!isAdmin} checked={!!draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.checked })} />}
                <span>{label}</span>
                {type === 'number' && <input type="number" min="0" disabled={!isAdmin} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: Number(e.target.value) })} />}
                {type === 'select' && <select disabled={!isAdmin} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}>{opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}
              </label>
            ))}
          </div>
          {isAdmin && <div className="actions"><button type="submit" className="btn">Enregistrer</button>{msg && <span className="small">{msg}</span>}</div>}
        </form>
      )}
      <div className="card">
        <h3>Règles de déduction à partir des alarmes</h3>
        <p className="small muted">Une règle n'a d'effet qu'après validation explicite par un administrateur. Toute modification annule la validation.</p>
        <table className="tbl tbl-compact">
          <thead><tr><th>Équip.</th><th>Code alarme</th><th>Motif (regex)</th><th>Effet</th><th>Portée</th><th>Active</th><th>Validation</th><th>Note</th><th /></tr></thead>
          <tbody>
            {rules?.map((r) => (
              <tr key={r.id}>
                <td>{VENDOR_LABEL[r.vendor]}</td><td className="mono">{r.alarm_code || '—'}</td><td className="mono">{r.text_pattern || '—'}</td>
                <td><StatusBadge status={r.effect} small /></td><td>{r.scope === 'SITE' ? 'Site' : 'Équipement'}</td>
                <td>{r.enabled ? 'Oui' : 'Non'}</td>
                <td>{r.validated_at ? <span className="small">{r.validated_by}, {fmtDate(r.validated_at)}</span> : <span className="tag-warn">non validée</span>}</td>
                <td className="small">{r.note}</td>
                <td className="actions">{isAdmin && <>
                  {!r.validated_at && <button type="button" className="btn btn-ghost" onClick={() => act(() => api.post(`/api/admin/alarm-rules/${r.id}/validate`))}>Valider</button>}
                  <button type="button" className="btn btn-ghost" onClick={() => act(() => api.put(`/api/admin/alarm-rules/${r.id}`, { ...r, enabled: !r.enabled }))}>{r.enabled ? 'Désactiver' : 'Activer'}</button>
                  <button type="button" className="btn btn-ghost danger" onClick={() => window.confirm('Supprimer cette règle ?') && act(() => api.del(`/api/admin/alarm-rules/${r.id}`))}>Supprimer</button>
                </>}</td>
              </tr>
            ))}
            {rules && !rules.length && <tr><td colSpan={9} className="empty">Aucune règle : seuls les états fournis par les OMC sont utilisés.</td></tr>}
          </tbody>
        </table>
        {isAdmin && (
          <form className="inline-form" onSubmit={addRule}>
            <select value={nr.vendor} onChange={(e) => setNr({ ...nr, vendor: e.target.value })}>{VENDORS.map((v) => <option key={v} value={v}>{VENDOR_LABEL[v]}</option>)}</select>
            <input placeholder="Code alarme" value={nr.alarm_code} onChange={(e) => setNr({ ...nr, alarm_code: e.target.value })} maxLength={100} />
            <input placeholder="ou motif de texte (regex)" value={nr.text_pattern} onChange={(e) => setNr({ ...nr, text_pattern: e.target.value })} maxLength={300} />
            <select value={nr.effect} onChange={(e) => setNr({ ...nr, effect: e.target.value })}><option value="DOWN">DOWN</option><option value="DEGRADED">DÉGRADÉ</option></select>
            <select value={nr.scope} onChange={(e) => setNr({ ...nr, scope: e.target.value })}><option value="ELEMENT">Équipement</option><option value="SITE">Site</option></select>
            <input placeholder="Note / justification" value={nr.note} onChange={(e) => setNr({ ...nr, note: e.target.value })} maxLength={500} />
            <button type="submit" className="btn">Ajouter</button>
          </form>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Utilisateurs
function Users() {
  const { user: me } = useAuth();
  const [data, err, reload, setErr] = useLoad(() => api.get('/api/admin/users'), []);
  const [nu, setNu] = useState({ username: '', full_name: '', role: 'VIEWER', can_export: false, password: '' });
  const [msg, setMsg] = useState('');
  const create = async (e) => {
    e.preventDefault();
    try { await api.post('/api/admin/users', nu); setNu({ username: '', full_name: '', role: 'VIEWER', can_export: false, password: '' }); setMsg('Utilisateur créé (changement de mot de passe imposé à la 1re connexion).'); reload(); } catch (ex) { setErr(ex); }
  };
  const patch = async (u, body) => { try { await api.patch(`/api/admin/users/${u.id}`, body); reload(); } catch (ex) { setErr(ex); } };
  const resetPwd = (u) => {
    const p = window.prompt(`Nouveau mot de passe provisoire pour ${u.username} (10 caractères min., 3 types) :`);
    if (p) patch(u, { password: p });
  };
  return (
    <div className="card">
      <ErrorBox error={err} />{msg && <div className="alert alert-info">{msg}</div>}
      <table className="tbl tbl-compact">
        <thead><tr><th>Utilisateur</th><th>Rôle</th><th>Export</th><th>Actif</th><th>Dernière connexion</th><th>Verrouillé</th><th /></tr></thead>
        <tbody>
          {data?.map((u) => (
            <tr key={u.id}>
              <td><b>{u.username}</b><div className="small muted">{u.full_name}</div></td>
              <td><select value={u.role} disabled={u.id === me.id} onChange={(e) => patch(u, { role: e.target.value })}>
                <option value="ADMIN">Administrateur</option><option value="SUPERVISOR">Superviseur</option><option value="VIEWER">Consultation</option></select></td>
              <td><input type="checkbox" checked={u.can_export} disabled={u.role !== 'VIEWER'} onChange={(e) => patch(u, { can_export: e.target.checked })} aria-label="Droit d'export" /></td>
              <td><input type="checkbox" checked={u.is_active} disabled={u.id === me.id} onChange={(e) => patch(u, { is_active: e.target.checked })} aria-label="Compte actif" /></td>
              <td>{fmtDate(u.last_login_at)}</td>
              <td>{u.locked_until && new Date(u.locked_until) > new Date() ? fmtDate(u.locked_until) : '—'}</td>
              <td><button type="button" className="btn btn-ghost" onClick={() => resetPwd(u)}>Réinitialiser le mot de passe</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="inline-form" onSubmit={create}>
        <input placeholder="Identifiant" required value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} pattern="[a-zA-Z0-9._\-]{3,64}" />
        <input placeholder="Nom complet" value={nu.full_name} onChange={(e) => setNu({ ...nu, full_name: e.target.value })} />
        <select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}><option value="VIEWER">Consultation</option><option value="SUPERVISOR">Superviseur</option><option value="ADMIN">Administrateur</option></select>
        <label className="check"><input type="checkbox" checked={nu.can_export} onChange={(e) => setNu({ ...nu, can_export: e.target.checked })} /> export</label>
        <input type="password" placeholder="Mot de passe provisoire" required value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} autoComplete="new-password" />
        <button type="submit" className="btn">Créer</button>
      </form>
      <p className="small muted">Rôles : Consultation (lecture, export si autorisé) · Superviseur (lecture, export, synchronisation à la demande) · Administrateur (tout).</p>
    </div>
  );
}

function ImportCsv() {
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const send = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { setRes(await api.upload('/api/admin/import/sites-csv', file)); loadReference(true); } catch (ex) { setErr(ex); }
    setBusy(false);
  };
  return (
    <form className="card form" onSubmit={send}>
      <h3>Importer des sites depuis un fichier CSV</h3>
      <p className="small">Colonnes obligatoires : <code>site_code, site_name, latitude, longitude, vendor, technologies</code>. Optionnelles : <code>wilaya_code, wilaya, commune, address, status, tech_status, omc_source, last_update, alarm_code, alarm_text, alarm_severity</code>. Séparateur <code>;</code> ou <code>,</code>, UTF-8. Les lignes commençant par <code>#</code> sont ignorées. Réimporter un fichier met à jour les sites existants sans créer de doublon.</p>
      <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files[0])} required />
      <div className="actions"><button type="submit" className="btn" disabled={!file || busy}>{busy ? 'Import en cours…' : 'Importer'}</button></div>
      <ErrorBox error={err} />
      {res && (
        <div className="alert alert-info">
          {res.accepted} / {res.rows} ligne(s) importée(s). Sources : {Object.keys(res.sources).join(', ') || '—'}.
          {res.rejected.length > 0 && <ul className="small">{res.rejected.slice(0, 30).map((r) => <li key={r}>{r}</li>)}</ul>}
        </div>
      )}
    </form>
  );
}

function Audit() {
  const [page, setPage] = useState(1);
  const [data, err] = useLoad(() => api.get(`/api/admin/audit?page=${page}&page_size=50`), [page]);
  return (
    <div className="card">
      <ErrorBox error={err} />
      {data && <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />}
      <table className="tbl tbl-compact">
        <thead><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Cible</th><th>Détails</th><th>IP</th></tr></thead>
        <tbody>{data?.items.map((a) => (
          <tr key={a.id}><td>{fmtDate(a.at)}</td><td>{a.username || '—'}</td><td className="mono">{a.action}</td><td>{a.target}</td>
            <td className="small mono">{JSON.stringify(a.details).slice(0, 200)}</td><td className="small">{a.ip}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function AdminPage() {
  const { isAdmin } = useAuth();
  const tabs = [['sources', 'Sources OMC', Sources], ['runs', 'Collectes', Runs], ['rules', "Règles d'états", Rules],
    ...(isAdmin ? [['users', 'Utilisateurs', Users], ['import', 'Import CSV', ImportCsv], ['audit', "Journal d'audit", Audit]] : [])];
  const [tab, setTab] = useState('sources');
  const Comp = tabs.find((t) => t[0] === tab)?.[2] || Sources;
  return (
    <div className="dash admin">
      <div className="toolbar"><h1>Administration</h1></div>
      <nav className="tabs" role="tablist">
        {tabs.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </nav>
      <Comp />
    </div>
  );
}
