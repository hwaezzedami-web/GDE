import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Empty, ErrorBox, Pagination, Spinner, StatusBadge, TechChips } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { ANOMALY, REF_STATUS, VENDOR_LABEL, fmtDate, fmtInt } from '../lib/constants';
import { loadReference } from '../lib/reference';
import SitesManager from './SitesManager';
import UnknownSites from './UnknownSites';

function useLoad(fn, deps) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const reload = useCallback(() => { fn().then((d) => { setData(d); setErr(null); }).catch(setErr); }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(reload, [reload]);
  return [data, err, reload, setErr];
}

function Kpi({ v, label, color, onClick, title }) {
  return (
    <button type="button" className="kpi" style={{ '--c': color }} onClick={onClick} title={title} disabled={!onClick}>
      <span className="kpi-v">{fmtInt(v)}</span><span className="kpi-l">{label}</span>
    </button>
  );
}

// ------------------------------------------------------------------ Synthèse
function Summary({ data, goAnomalies }) {
  const { canExport } = useAuth();
  const [err, setErr] = useState(null);
  if (!data) return <Spinner />;
  const s = data.sites;
  const dl = (p) => api.download(p).catch(setErr);
  return (
    <div className="stack">
      <ErrorBox error={err} />
      <div className="kpis">
        <Kpi v={s.reference} label="Sites au référentiel" color="#0f2a3f" />
        <Kpi v={s.reference_supervised} label="dont remontés par un OMC" color="#16a34a" />
        <Kpi v={s.in_service_unsupervised} label="En service, non supervisés" color="#8a94a6"
          title="En service au référentiel mais aucun OMC raccordé ne les remonte" />
        <Kpi v={s.supervised_not_in_reference} label="Remontés par un OMC, hors référentiel" color="#dc2626"
          onClick={() => goAnomalies('UNKNOWN_SITE')} />
        <Kpi v={data.anomalies.total} label="Anomalies à traiter" color="#ea8a0c" onClick={() => goAnomalies('')} />
      </div>
      {!s.reference && (
        <div className="alert alert-info">
          Aucun référentiel importé : seuls les sites remontés par les OMC sont connus. Importez la liste des sites
          (KMZ, KML, Excel, CSV ou GeoJSON) dans l'onglet « Importer » pour détecter les sites manquants.
        </div>
      )}
      <div className="grid">
        <div className="card">
          <header><h3>Catégories</h3></header>
          <table className="tbl tbl-compact">
            <tbody>
              {Object.entries(REF_STATUS).map(([k, v]) => (
                <tr key={k}><td><i className="dot" style={{ background: v.color }} /> {v.label}</td>
                  <td className="num">{fmtInt(data.by_status[k] || 0)}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="small muted">Les sites en projet ou démontés non supervisés sont masqués de la carte par défaut
            (filtre « Référentiel »).</p>
        </div>
        <div className="card scroll">
          <header><h3>Par direction régionale</h3></header>
          <table className="tbl tbl-compact">
            <thead><tr><th>DR</th><th className="num">Sites</th><th className="num">Supervisés</th></tr></thead>
            <tbody>{data.by_dr.map((r) => (
              <tr key={r.dr}><td>{r.dr}</td><td className="num">{fmtInt(r.sites)}</td>
                <td className="num">{fmtInt(r.supervised)} <span className="muted small">({r.sites ? Math.round((100 * r.supervised) / r.sites) : 0} %)</span></td></tr>
            ))}</tbody>
          </table>
        </div>
        <div className="card">
          <header><h3>Dernier import</h3></header>
          {data.last_import ? (
            <dl className="kvs">
              <div className="kv"><dt>Fichier</dt><dd>{data.last_import.file_name}</dd></div>
              <div className="kv"><dt>Date</dt><dd>{fmtDate(data.last_import.finished_at)}</dd></div>
              <div className="kv"><dt>Par</dt><dd>{data.last_import.username || (data.last_import.origin === 'WATCH' ? 'dossier surveillé' : data.last_import.origin)}</dd></div>
              <div className="kv"><dt>Mode</dt><dd>{data.last_import.mode === 'sync' ? 'synchronisation complète' : 'mise à jour'}</dd></div>
              <div className="kv"><dt>Résultat</dt><dd>{fmtInt(data.last_import.counts?.new)} nouveaux · {fmtInt(data.last_import.counts?.updated)} modifiés · {fmtInt(data.last_import.counts?.removed_applied || 0)} retirés</dd></div>
            </dl>
          ) : <p className="muted">Aucun import.</p>}
          {s.wilaya_mismatch > 0 && (
            <p className="small muted">{fmtInt(s.wilaya_mismatch)} site(s) ont des coordonnées hors de la wilaya indiquée dans le fichier
              (découpage à 58 wilayas du fichier, sites frontaliers ou erreurs de saisie). Paramètre « Wilaya » pour utiliser les coordonnées.</p>
          )}
          <div className="actions">
            {canExport && <button type="button" className="btn btn-ghost" onClick={() => dl('/api/site-reference/export?format=xlsx')}>Exporter le référentiel</button>}
            <button type="button" className="btn btn-ghost" onClick={() => dl('/api/site-reference/template')}>Modèle Excel</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Anomalies
function Anomalies({ initialType, onChange }) {
  const { isSupervisor, canExport } = useAuth();
  const [type, setType] = useState(initialType || '');
  const [state, setState] = useState('CURRENT');
  const [q, setQ] = useState('');
  const [qq, setQq] = useState('');
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  useEffect(() => { const t = setTimeout(() => { setQq(q.trim()); setPage(1); }, 350); return () => clearTimeout(t); }, [q]);
  const qs = new URLSearchParams({ state, page, page_size: 50, ...(type ? { type } : {}), ...(qq ? { q: qq } : {}) });
  const [data, err, reload, setErr] = useLoad(() => api.get(`/api/site-reference/anomalies?${qs}`), [qs.toString()]);
  const act = async (fn) => { try { await fn(); reload(); onChange?.(); } catch (ex) { setErr(ex); } };
  const ack = (a) => {
    const note = window.prompt('Commentaire (facultatif) : action prévue, ticket, raison…', a.note || '');
    if (note !== null) act(() => api.post(`/api/site-reference/anomalies/${a.id}/ack`, { note: note || null }));
  };
  const reconcile = async () => {
    setBusy(true);
    try { const r = await api.post('/api/site-reference/reconcile'); setMsg(`${r.new} nouvelle(s), ${r.resolved} résolue(s).`); reload(); onChange?.(); } catch (ex) { setErr(ex); }
    setBusy(false);
  };
  const counts = data?.counts || {};
  return (
    <div className="card">
      <div className="chips" style={{ marginBottom: 8 }}>
        <button type="button" className={`chip${!type ? ' on' : ''}`} onClick={() => { setType(''); setPage(1); }}>Toutes</button>
        {Object.entries(ANOMALY).map(([k, v]) => (
          <button key={k} type="button" className={`chip${type === k ? ' on' : ''}`} title={v.help}
            onClick={() => { setType(type === k ? '' : k); setPage(1); }}>
            <i className="dot" style={{ background: v.color }} />{v.short}
            <em>{fmtInt((counts[k]?.open || 0) + (counts[k]?.acknowledged || 0))}</em>
          </button>
        ))}
      </div>
      <div className="table-tools">
        <select value={state} onChange={(e) => { setState(e.target.value); setPage(1); }} aria-label="Traitement">
          <option value="CURRENT">En cours (à traiter + pris en compte)</option>
          <option value="OPEN">À traiter</option>
          <option value="ACKNOWLEDGED">Pris en compte</option>
          <option value="RESOLVED">Résolues</option>
          <option value="ALL">Toutes</option>
        </select>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Code ou nom de site" maxLength={60} />
        {msg && <span className="small">{msg}</span>}
        <div className="actions">
          {isSupervisor && <button type="button" className="btn btn-ghost" disabled={busy} onClick={reconcile}>Rapprocher maintenant</button>}
          {canExport && <button type="button" className="btn btn-ghost"
            onClick={() => api.download(`/api/site-reference/anomalies/export?format=xlsx&state=${state}${type ? `&type=${type}` : ''}`).catch(setErr)}>Export Excel</button>}
        </div>
      </div>
      <ErrorBox error={err} />
      {type && <p className="small muted">{ANOMALY[type].help}</p>}
      <div className="table-scroll">
        <table className="tbl tbl-compact">
          <thead><tr><th>Anomalie</th><th>Site</th><th>Wilaya / DR</th><th>Référentiel</th><th>État OMC</th><th>OMC</th><th>Détectée</th><th>Traitement</th><th /></tr></thead>
          <tbody>
            {data?.items.map((a) => {
              const d = a.details || {};
              return (
                <tr key={a.id} className={a.resolved_at ? 'inactive' : ''}>
                  <td><span className="anom" style={{ '--c': ANOMALY[a.anomaly_type]?.color }}>{ANOMALY[a.anomaly_type]?.short || a.anomaly_type}</span></td>
                  <td>{a.site_id ? <Link to={`/?site=${a.site_id}&ref=ALL`} className="mono">{a.site_external_id}</Link> : <span className="mono">{a.site_external_id}</span>}
                    <div className="small">{a.site_name}</div>
                    {d.suggestion && <div className="small muted">code proche au référentiel : <b>{d.suggestion}</b></div>}</td>
                  <td>{a.wilaya_name || '—'}<div className="small muted">{a.dr}</div></td>
                  <td>{a.lifecycle || <span className="muted">absent</span>}
                    {d.last_supervised_at && <div className="small muted">vu le {fmtDate(d.last_supervised_at)}</div>}</td>
                  <td><StatusBadge status={a.status} small /><div className="small muted">{VENDOR_LABEL[a.vendor] || a.vendor}</div></td>
                  <td className="small">{d.sources || "—"}{d.technologies && <div><TechChips techs={d.technologies} /></div>}</td>
                  <td className="small">{fmtDate(a.first_detected_at)}{a.resolved_at && <div>résolue {fmtDate(a.resolved_at)}</div>}</td>
                  <td className="small">{a.state === 'ACKNOWLEDGED' ? <>pris en compte · {a.acknowledged_by}{a.note && <div className="muted">« {a.note} »</div>}</>
                    : a.state === 'RESOLVED' ? 'résolue' : <span className="tag-warn">à traiter</span>}</td>
                  <td className="actions">{isSupervisor && !a.resolved_at && (a.state === 'OPEN'
                    ? <button type="button" className="btn btn-ghost" onClick={() => ack(a)}>Prendre en compte</button>
                    : <button type="button" className="btn btn-ghost" onClick={() => act(() => api.post(`/api/site-reference/anomalies/${a.id}/reopen`))}>Rouvrir</button>)}</td>
                </tr>
              );
            })}
            {data && !data.items.length && <tr><td colSpan={9} className="empty">Aucune anomalie.</td></tr>}
          </tbody>
        </table>
      </div>
      {data && <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />}
      <p className="small muted">Les anomalies sont recalculées après chaque collecte OMC et chaque import ; elles se résolvent
        d'elles-mêmes quand le référentiel ou l'OMC est corrigé. « Prendre en compte » ne fait que masquer l'alerte du compteur.</p>
    </div>
  );
}

// ------------------------------------------------------------------ Import
const TARGET_HELP = {
  code: 'obligatoire', latitude: 'obligatoire', longitude: 'obligatoire',
  lifecycle: 'classé selon les paramètres',
};

function Diff({ title, rows, render, total }) {
  if (!total) return null;
  return (
    <details className="card">
      <summary><b>{title}</b> : {fmtInt(total)}{rows.length < total ? ` (${rows.length} premiers affichés)` : ''}</summary>
      <ul className="small diff-list">{rows.map(render)}</ul>
    </details>
  );
}

function ImportWizard({ onDone }) {
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState('update');
  const [digits, setDigits] = useState('');
  const [mapping, setMapping] = useState(null);
  const [sheet, setSheet] = useState('');
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmRemoval, setConfirmRemoval] = useState(false);

  const fields = (extra = {}) => ({
    file, mode, code_digits: digits || null, sheet: sheet || null,
    mapping: mapping ? JSON.stringify(mapping) : null, ...extra,
  });
  const runPreview = async (e) => {
    e?.preventDefault();
    if (!file) return;
    setBusy(true); setErr(null); setResult(null);
    try { const p = await api.form('/api/site-reference/import/preview', fields()); setPreview(p); setMapping(p.mapping); setConfirmRemoval(false); } catch (ex) { setErr(ex); setPreview(null); }
    setBusy(false);
  };
  const apply = async () => {
    const c = preview.counts;
    const text = `Appliquer l'import ?\n\n${c.new} nouveaux sites, ${c.updated} modifiés${mode === 'sync' ? `, ${c.removed} retirés du référentiel` : ''}.`;
    if (!window.confirm(text)) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.form('/api/site-reference/import/apply', fields({ expected_sha256: preview.sha256, confirm_large_removal: confirmRemoval ? 'true' : null }));
      setResult(r);
      if (r.status === 'APPLIED') { setPreview(null); loadReference(true); onDone?.(); }
    } catch (ex) { setErr(ex); }
    setBusy(false);
  };
  const options = useMemo(() => {
    if (!preview) return [];
    return [...(preview.has_geometry ? [['__geometry__', 'Position du repère (KML / GeoJSON)']] : []),
      ...(['kml', 'kmz'].includes(preview.format) ? [['__placemark__', 'Nom du repère (KML)']] : []),
      ...preview.columns.map((c) => [c, c])];
  }, [preview]);
  const setTarget = (t, v) => {
    const m = { ...mapping, [t]: v || null };
    if ((t === 'latitude' || t === 'longitude') && v === '__geometry__') { m.latitude = '__geometry__'; m.longitude = '__geometry__'; }
    setMapping(m);
  };
  const c = preview?.counts;
  const blocked = preview && mode === 'sync' && !preview.safe_to_apply && !confirmRemoval;

  return (
    <div className="stack">
      <form className="card form" onSubmit={runPreview}>
        <h3>1. Fichier du référentiel</h3>
        <p className="small">Formats : <b>KMZ / KML</b> (Google Earth), <b>Excel .xlsx</b>, <b>CSV</b> (séparateur ; ou ,) ou <b>GeoJSON</b>.
          Les colonnes sont reconnues automatiquement (code site, nom, latitude/longitude ou position du repère, wilaya,
          commune, région/DR, cycle de vie, technologies) et peuvent être ajustées. Les autres colonnes sont conservées
          et affichées dans la fiche du site. Rien n'est écrit avant l'étape 3.</p>
        <div className="form-grid">
          <label className="field"><span>Fichier (50 Mo max.)</span>
            <input type="file" accept=".kmz,.kml,.xlsx,.xlsm,.csv,.txt,.geojson,.json"
              onChange={(e) => { setFile(e.target.files[0]); setPreview(null); setMapping(null); setResult(null); setSheet(''); }} required /></label>
          <label className="field"><span>Mode</span>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="update">Mise à jour : ajoute et modifie (aucun site retiré)</option>
              <option value="sync">Synchronisation complète : les sites absents du fichier sortent du référentiel</option>
            </select></label>
          <label className="field"><span>Compléter les codes numériques à N chiffres (zéros de tête perdus par Excel)</span>
            <input type="number" min="1" max="20" value={digits} placeholder="ex. 5 : 5474 → 05474" onChange={(e) => setDigits(e.target.value)} /></label>
          {preview?.format === 'xlsx' && <label className="field"><span>Feuille</span>
            <input value={sheet} placeholder={preview.sheet} onChange={(e) => setSheet(e.target.value)} /></label>}
        </div>
        <div className="actions"><button type="submit" className="btn" disabled={!file || busy}>{busy ? 'Analyse…' : preview ? 'Relancer l\'analyse' : 'Analyser le fichier'}</button></div>
      </form>
      <ErrorBox error={err} />
      {result && (
        <div className={`alert ${result.status === 'APPLIED' ? 'alert-info' : 'alert-warn'}`}>
          {result.status === 'APPLIED'
            ? <>Import appliqué : {fmtInt(result.counts.applied)} sites écrits, {fmtInt(result.counts.removed_applied)} retirés.
              {result.counts.omc_codes_adopted > 0 && <> {result.counts.omc_codes_adopted} site(s) OMC rapprochés de leur code.</>}
              {' '}Anomalies ouvertes : {Object.entries(result.anomalies?.open || {}).map(([k, v]) => `${ANOMALY[k]?.short || k} ${v}`).join(', ') || 'aucune'}.</>
            : result.message}
        </div>
      )}
      {preview && (
        <>
          <div className="card">
            <h3>2. Correspondance des colonnes</h3>
            <p className="small muted">Format détecté : {preview.format.toUpperCase()}{preview.sheet ? ` · feuille « ${preview.sheet} »` : ''} · {fmtInt(c.rows)} lignes.
              Modifier une correspondance puis « Relancer l'analyse ».</p>
            <div className="form-grid">
              {Object.keys(preview.mapping).map((t) => (
                <label key={t} className="field"><span>{preview.labels?.[t] || t} {TARGET_HELP[t] && <em className="muted">({TARGET_HELP[t]})</em>}</span>
                  <select value={mapping?.[t] || ''} onChange={(e) => setTarget(t, e.target.value)}>
                    <option value="">— non utilisé —</option>
                    {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select></label>
              ))}
            </div>
            <div className="table-scroll">
              <table className="tbl tbl-compact">
                <thead><tr><th>Code</th><th>Nom</th><th>Lat.</th><th>Long.</th><th>Wilaya</th><th>DR</th><th>Cycle de vie</th><th>Catégorie</th><th>Technos</th></tr></thead>
                <tbody>{preview.preview_rows.map((r) => (
                  <tr key={r.code}><td className="mono">{r.code}</td><td>{r.name}</td><td>{r.lat}</td><td>{r.lon}</td>
                    <td>{r.wilaya ?? '—'}</td><td>{r.dr}</td><td>{r.lifecycle}</td><td>{REF_STATUS[r.ref_status]?.label}</td><td><TechChips techs={r.techs} /></td></tr>
                ))}</tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <h3>3. Différentiel et application</h3>
            <div className="kpis">
              <Kpi v={c.valid} label="Sites valides" color="#0f2a3f" />
              <Kpi v={c.new} label="Nouveaux" color="#16a34a" />
              <Kpi v={c.updated} label="Modifiés" color="#2563eb" />
              <Kpi v={c.unchanged} label="Inchangés" color="#8a94a6" />
              {mode === 'sync' && <Kpi v={c.removed} label={`Retirés (${c.removal_pct} %)`} color="#dc2626" />}
              <Kpi v={c.invalid} label="Lignes rejetées" color="#ea8a0c" />
            </div>
            <p className="small">Catégories : {Object.entries(c.by_status).map(([k, v]) => `${REF_STATUS[k]?.label || k} ${fmtInt(v)}`).join(' · ')}
              {c.new_already_in_omc > 0 && <> · {fmtInt(c.new_already_in_omc)} nouveau(x) déjà remonté(s) par un OMC</>}
              {mode === 'update' && c.supervised_not_in_file > 0 && <> · {fmtInt(c.supervised_not_in_file)} site(s) supervisé(s) absent(s) du fichier (resteront signalés)</>}</p>
            {preview.warnings.map((w) => <div key={w} className="alert alert-warn">{w}</div>)}
            {mode === 'sync' && !preview.safe_to_apply && (
              <div className="alert alert-error">
                Cette synchronisation retirerait {fmtInt(c.removed)} sites ({c.removal_pct} %), au-delà du seuil de {preview.max_removal_pct} % :
                fichier incomplet, mauvaise feuille ou mauvais filtre ?
                <label className="check"><input type="checkbox" checked={confirmRemoval} onChange={(e) => setConfirmRemoval(e.target.checked)} /> Je confirme le retrait</label>
              </div>
            )}
            <Diff title="Nouveaux sites" total={c.new} rows={preview.sample_new}
              render={(r) => <li key={r.code}><span className="mono">{r.code}</span> {r.name} · {r.wilaya || '—'} · {REF_STATUS[r.ref_status]?.label}{r.omc && ' · déjà remonté par un OMC'}</li>} />
            <Diff title="Sites modifiés" total={c.updated} rows={preview.sample_updated}
              render={(r) => <li key={r.code}><span className="mono">{r.code}</span> {r.name} : {r.changes.join(' ; ')}</li>} />
            <Diff title="Sites retirés du référentiel" total={mode === 'sync' ? c.removed : 0} rows={preview.sample_removed}
              render={(r) => <li key={r.code}><span className="mono">{r.code}</span> {r.name}{r.omc && ' · encore remonté par un OMC (restera visible et signalé)'}</li>} />
            <Diff title="Lignes rejetées" total={c.invalid} rows={preview.invalid}
              render={(r) => <li key={`${r.line}-${r.code}`}>ligne {r.line} {r.code ? <span className="mono">{r.code}</span> : ''} : {r.reason}</li>} />
            <Diff title="Corrections automatiques" total={c.fixed} rows={preview.fixes}
              render={(r) => <li key={`${r.line}-${r.code}`}>ligne {r.line} <span className="mono">{r.code}</span> : {r.fix}</li>} />
            <div className="actions">
              <button type="button" className="btn" disabled={busy || blocked || !c.valid} onClick={apply}>{busy ? 'Application…' : 'Appliquer l\'import'}</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Historique
function Imports() {
  const [data, err] = useLoad(() => api.get('/api/site-reference/imports'), []);
  const ORIGIN = { UI: 'Interface', WATCH: 'Dossier surveillé', CLI: 'Ligne de commande' };
  return (
    <div className="card">
      <ErrorBox error={err} />
      <div className="table-scroll">
        <table className="tbl tbl-compact">
          <thead><tr><th>Date</th><th>Origine</th><th>Fichier</th><th>Mode</th><th>Résultat</th><th className="num">Nouveaux</th><th className="num">Modifiés</th><th className="num">Retirés</th><th className="num">Rejets</th><th>Messages</th></tr></thead>
          <tbody>
            {data?.items.map((i) => (
              <tr key={i.id}>
                <td>{fmtDate(i.started_at)}</td><td>{ORIGIN[i.origin] || i.origin}{i.username && <div className="small muted">{i.username}</div>}</td>
                <td className="small">{i.file_name}<div className="muted mono" title={i.file_sha256}>{(i.file_sha256 || '').slice(0, 12)}</div></td>
                <td>{i.mode === 'sync' ? 'synchro.' : 'mise à jour'}</td>
                <td>{i.status === 'APPLIED' ? 'appliqué' : <span className="tag-warn">{i.status === 'REFUSED' ? 'refusé' : 'échec'}</span>}</td>
                <td className="num">{fmtInt(i.counts?.new)}</td><td className="num">{fmtInt(i.counts?.updated)}</td>
                <td className="num">{fmtInt(i.counts?.removed_applied ?? 0)}</td><td className="num">{fmtInt(i.counts?.invalid)}</td>
                <td className="small">{(i.messages || []).slice(0, 4).join(' · ')}</td>
              </tr>
            ))}
            {data && !data.items.length && <tr><td colSpan={10} className="empty">Aucun import.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Paramètres
function Settings({ summary, onSaved }) {
  const { isAdmin } = useAuth();
  const [draft, setDraft] = useState(null);
  const [newKey, setNewKey] = useState('');
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState('');
  useEffect(() => { if (summary) setDraft(summary.settings); }, [summary]);
  if (!draft) return <Spinner />;
  const seen = Object.fromEntries((summary.lifecycles || []).map((l) => [l.lifecycle, l.sites]));
  const keys = [...new Set([...Object.keys(draft.lifecycle_map), ...Object.keys(seen).filter((k) => k && k !== 'null')])].sort();
  const setMap = (k, v) => setDraft({ ...draft, lifecycle_map: { ...draft.lifecycle_map, [k]: v } });
  const save = async (e) => {
    e.preventDefault();
    const map = Object.fromEntries(Object.entries(draft.lifecycle_map).filter(([, v]) => v));
    try { await api.put('/api/admin/settings/reference', { ...draft, lifecycle_map: map }); setMsg('Paramètres enregistrés, sites reclassés.'); onSaved(); } catch (ex) { setErr(ex); }
  };
  const num = (k) => (e) => setDraft({ ...draft, [k]: Number(e.target.value) });
  const bool = (k) => (e) => setDraft({ ...draft, [k]: e.target.checked });
  const cat = (k, v) => (
    <select disabled={!isAdmin} value={v || ''} onChange={(e) => setMap(k, e.target.value)}>
      <option value="">— {REF_STATUS[draft.lifecycle_unknown]?.label} (valeur non classée) —</option>
      {Object.entries(REF_STATUS).map(([c, l]) => <option key={c} value={c}>{l.label}</option>)}
    </select>
  );
  return (
    <form className="stack" onSubmit={save}>
      <ErrorBox error={err} />
      <div className="card form">
        <h3>Classement du cycle de vie</h3>
        <p className="small muted">Chaque valeur brute du fichier est rangée dans une catégorie. À valider avec l'exploitant
          (le sens de « halte », « construit », « not_on_air »… est propre à l'opérateur).</p>
        <table className="tbl tbl-compact">
          <thead><tr><th>Valeur dans le fichier</th><th className="num">Sites</th><th>Catégorie</th></tr></thead>
          <tbody>{keys.map((k) => (
            <tr key={k}><td className="mono">{k}</td><td className="num">{fmtInt(seen[k] || 0)}</td><td>{cat(k, draft.lifecycle_map[k])}</td></tr>
          ))}</tbody>
        </table>
        {isAdmin && (
          <div className="inline-form">
            <input placeholder="Autre valeur (ex. en_maintenance)" value={newKey} onChange={(e) => setNewKey(e.target.value)} maxLength={80} />
            <button type="button" className="btn btn-ghost" onClick={() => { if (newKey.trim()) { setMap(newKey.trim().toLowerCase(), 'OTHER'); setNewKey(''); } }}>Ajouter</button>
          </div>
        )}
        <div className="form-grid">
          <label className="field"><span>Valeur non classée</span>
            <select disabled={!isAdmin} value={draft.lifecycle_unknown} onChange={(e) => setDraft({ ...draft, lifecycle_unknown: e.target.value })}>
              {Object.entries(REF_STATUS).map(([c, l]) => <option key={c} value={c}>{l.label}</option>)}</select></label>
          <label className="field"><span>Fichier sans cycle de vie</span>
            <select disabled={!isAdmin} value={draft.lifecycle_missing} onChange={(e) => setDraft({ ...draft, lifecycle_missing: e.target.value })}>
              {Object.entries(REF_STATUS).map(([c, l]) => <option key={c} value={c}>{l.label}</option>)}</select></label>
        </div>
      </div>
      <div className="card form">
        <h3>Import et rapprochement</h3>
        <div className="form-grid">
          <label className="field"><span>Wilaya des sites</span>
            <select disabled={!isAdmin} value={draft.wilaya_from} onChange={(e) => setDraft({ ...draft, wilaya_from: e.target.value })}>
              <option value="file">Celle du fichier (référentiel de l'opérateur)</option>
              <option value="coordinates">Déduite des coordonnées (69 wilayas)</option></select></label>
          <label className="field"><span>Seuil de sites retirés par une synchronisation (%)</span>
            <input type="number" min="0" max="100" disabled={!isAdmin} value={draft.max_removal_pct} onChange={num('max_removal_pct')} /></label>
          <label className="field"><span>Supervision perdue après (jours sans remontée)</span>
            <input type="number" min="1" max="365" disabled={!isAdmin} value={draft.supervision_lost_days} onChange={num('supervision_lost_days')} /></label>
          <label className="field check"><input type="checkbox" disabled={!isAdmin} checked={draft.match_leading_zeros} onChange={bool('match_leading_zeros')} />
            <span>Rapprocher « 5474 » (OMC) et « 05474 » (référentiel)</span></label>
          <label className="field check"><input type="checkbox" disabled={!isAdmin} checked={draft.detect_never_supervised} onChange={bool('detect_never_supervised')} />
            <span>Signaler les sites en service jamais remontés (à activer quand tous les OMC sont raccordés)</span></label>
        </div>
      </div>
      <div className="card form">
        <h3>Dossier surveillé</h3>
        <p className="small muted">Le service de collecte importe automatiquement le fichier le plus récent déposé dans le dossier
          <code> referentiel-depot/</code> du serveur (une seule fois par fichier), avec la correspondance de colonnes du dernier import
          réussi du même format. Le seuil de retrait s'applique : un import refusé apparaît dans l'historique.</p>
        <div className="form-grid">
          <label className="field check"><input type="checkbox" disabled={!isAdmin} checked={draft.watch_enabled} onChange={bool('watch_enabled')} /><span>Activer l'import automatique</span></label>
          <label className="field"><span>Mode</span>
            <select disabled={!isAdmin} value={draft.watch_mode} onChange={(e) => setDraft({ ...draft, watch_mode: e.target.value })}>
              <option value="update">Mise à jour</option><option value="sync">Synchronisation complète</option></select></label>
          <label className="field"><span>Vérification toutes les (s) — pris en compte au redémarrage du collecteur</span>
            <input type="number" min="60" max="86400" disabled={!isAdmin} value={draft.watch_interval_s} onChange={num('watch_interval_s')} /></label>
        </div>
      </div>
      {isAdmin && <div className="actions"><button type="submit" className="btn">Enregistrer</button>{msg && <span className="small">{msg}</span>}</div>}
    </form>
  );
}

// ------------------------------------------------------------------ Page
export default function ReferencePage() {
  const { isAdmin } = useAuth();
  const [summary, sErr, reloadSummary] = useLoad(() => api.get('/api/site-reference/summary'), []);
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') || 'summary';
  const setTab = (t) => setParams((p) => { const n = new URLSearchParams(p); n.set('tab', t); return n; }, { replace: true });
  const [anomType, setAnomType] = useState('');
  const goAnomalies = (t) => {
    if (t === 'UNKNOWN_SITE') { setTab('unknown'); return; }
    setAnomType(t); setTab('anomalies');
  };
  const unknown = summary?.anomalies.by_type?.UNKNOWN_SITE || 0;
  const tabs = [['summary', 'Synthèse'], ['sites', `Sites${summary ? ` (${fmtInt(summary.sites.reference)})` : ''}`],
    ['unknown', <>Sites inconnus (OMC){unknown > 0 && <span className="tab-badge">{fmtInt(unknown)}</span>}</>],
    ['anomalies', `Anomalies${summary?.anomalies.total ? ` (${fmtInt(summary.anomalies.total)})` : ''}`],
    ...(isAdmin ? [['import', 'Importer']] : []), ['imports', 'Historique des imports'], ['settings', 'Paramètres']];
  return (
    <div className="dash admin">
      <div className="toolbar"><h1>Référentiel des sites</h1></div>
      <nav className="tabs" role="tablist">
        {tabs.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </nav>
      <ErrorBox error={sErr} onRetry={reloadSummary} />
      {tab === 'summary' && <Summary data={summary} goAnomalies={goAnomalies} />}
      {tab === 'sites' && <SitesManager onChanged={reloadSummary} goImport={() => setTab('import')} />}
      {tab === 'unknown' && <UnknownSites onChanged={reloadSummary} />}
      {tab === 'anomalies' && <Anomalies key={anomType} initialType={anomType} onChange={reloadSummary} />}
      {tab === 'import' && <ImportWizard onDone={reloadSummary} />}
      {tab === 'imports' && <Imports />}
      {tab === 'settings' && (summary ? <Settings summary={summary} onSaved={reloadSummary} /> : <Empty>Chargement…</Empty>)}
    </div>
  );
}
