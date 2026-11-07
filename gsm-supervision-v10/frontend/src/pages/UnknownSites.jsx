import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Dialog, { ConfirmDialog } from '../components/Dialog';
import SiteFormDialog from '../components/SiteFormDialog';
import { Empty, ErrorBox, Pagination, StatusBadge, TechChips } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { VENDOR_LABEL, fmtDate, fmtInt, since } from '../lib/constants';
import { useSiteOptions } from './SitesManager';

const fmtDist = (m) => (m == null ? '' : m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`);

// Rattacher un code OMC à un site du référentiel (recherche + suggestion)
function LinkDialog({ open, site, onClose, onDone }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [target, setTarget] = useState(null);
  const [note, setNote] = useState('');
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setErr(null); setNote(''); setResults([]);
    setQ(site?.suggestion || '');
    setTarget(site?.suggestion ? { external_id: site.suggestion, name: site.suggestion_name, wilaya_name: site.suggestion_wilaya } : null);
  }, [open, site]);
  useEffect(() => {
    if (!open || q.trim().length < 2) { setResults([]); return undefined; }
    const t = setTimeout(() => {
      api.get(`/api/site-reference/sites?q=${encodeURIComponent(q.trim())}&page_size=8`).then((r) => setResults(r.items)).catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [q, open]);
  const submit = async (e) => {
    e.preventDefault();
    if (!target) return;
    setBusy(true); setErr(null);
    try { onDone(await api.post(`/api/site-reference/unknown-sites/${site.site_id}/link`, { target_code: target.external_id, note: note || null })); } catch (ex) { setErr(ex); }
    setBusy(false);
  };
  return (
    <Dialog open={open} onClose={onClose} title={`Rattacher le code OMC ${site?.external_id || ''}`}
      footer={(<>
        <button type="button" className="btn btn-ghost" onClick={onClose}>Annuler</button>
        <button type="submit" form="link-form" className="btn" disabled={!target || busy}>{busy ? 'Rattachement…' : `Rattacher à ${target?.external_id || '…'}`}</button>
      </>)}>
      <form id="link-form" onSubmit={submit}>
        <p className="small">Le code <b className="mono">{site?.external_id}</b> remonté par {site?.sources} sera traité comme le site choisi :
          équipements, alarmes et historique transférés, et rattachement automatique aux prochaines collectes
          (faute de frappe, ancien code, nommage propre à l'équipementier).</p>
        <label className="field"><span>Site du référentiel</span>
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); setTarget(null); }} placeholder="Code ou nom du site" autoFocus /></label>
        {target && (
          <div className="pick on">
            <b className="mono">{target.external_id}</b> {target.name} <span className="muted">· {target.wilaya_name || '—'}</span>
            {site?.suggestion === target.external_id && site?.suggestion_distance_m != null && <span className="muted"> · à {fmtDist(site.suggestion_distance_m)} de la position OMC</span>}
          </div>
        )}
        {!target && results.length > 0 && (
          <ul className="pick-list" role="listbox" aria-label="Sites trouvés">
            {results.map((r) => (
              <li key={r.id}><button type="button" className="pick" onClick={() => setTarget(r)}>
                <b className="mono">{r.external_id}</b> {r.name} <span className="muted">· {r.wilaya_name || '—'} · {r.is_supervised ? 'supervisé' : 'non supervisé'}</span>
              </button></li>
            ))}
          </ul>
        )}
        {!target && q.trim().length >= 2 && !results.length && <p className="small muted">Aucun site du référentiel ne correspond.</p>}
        <label className="field"><span>Commentaire</span><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="ex. erreur de saisie dans l'OMC Huawei" /></label>
        <ErrorBox error={err} />
      </form>
    </Dialog>
  );
}

function AckDialog({ open, count, onClose, onDone }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setNote(''); }, [open]);
  return (
    <ConfirmDialog open={open} title={`Ignorer ${count} site(s) inconnu(s)`} confirmLabel="Ignorer" busy={busy} onClose={onClose}
      onConfirm={async () => { setBusy(true); await onDone(note); setBusy(false); }}>
      <p className="small">Les sites restent listés (onglet « Pris en compte ») mais ne sont plus comptés dans les anomalies à traiter.
        Ils disparaissent d'eux-mêmes s'ils sont ajoutés au référentiel ou ne sont plus remontés.</p>
      <label className="field"><span>Motif</span><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="ex. site de test constructeur, ticket n°…" /></label>
    </ConfirmDialog>
  );
}

function Aliases({ refreshKey, onChanged }) {
  const { isAdmin } = useAuth();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [del, setDel] = useState(null);
  const load = useCallback(() => api.get('/api/site-reference/aliases').then(setData).catch(setErr), []);
  useEffect(() => { load(); }, [load, refreshKey]);
  if (!data) return null;
  return (
    <section className="card">
      <header><h3>Correspondances de codes ({fmtInt(data.items.length)})</h3></header>
      <p className="small muted">Codes remontés par les OMC rattachés à un site du référentiel ; appliqués à chaque collecte.</p>
      <ErrorBox error={err} />
      {data.items.length ? (
        <div className="table-scroll"><table className="tbl tbl-compact">
          <thead><tr><th>Code OMC</th><th>Site du référentiel</th><th>Commentaire</th><th>Créé par</th><th /></tr></thead>
          <tbody>{data.items.map((a) => (
            <tr key={a.omc_code}>
              <td className="mono">{a.omc_code}</td>
              <td><Link to={`/?site=${a.site_id}&ref=ALL`} className="mono">{a.site_external_id}</Link> {a.site_name}</td>
              <td className="small">{a.note}</td>
              <td className="small">{a.created_by} · {fmtDate(a.created_at)}</td>
              <td className="col-actions">{isAdmin && <button type="button" className="btn btn-ghost danger" onClick={() => setDel(a)}>Supprimer</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <Empty>Aucune correspondance.</Empty>}
      <ConfirmDialog open={!!del} danger title="Supprimer la correspondance ?" confirmLabel="Supprimer" onClose={() => setDel(null)}
        onConfirm={async () => {
          try { await api.del(`/api/site-reference/aliases/${encodeURIComponent(del.omc_code)}`); setDel(null); load(); onChanged?.(); } catch (ex) { setErr(ex); setDel(null); }
        }}>
        <p className="small">Le code <b className="mono">{del?.omc_code}</b> ne sera plus rattaché à <b className="mono">{del?.site_external_id}</b> :
          à la prochaine collecte, il réapparaîtra comme site inconnu. Les équipements déjà transférés restent sur le site jusqu'à la prochaine collecte.</p>
      </ConfirmDialog>
    </section>
  );
}

export default function UnknownSites({ onChanged }) {
  const { isAdmin, isSupervisor, canExport } = useAuth();
  const [options, reloadOptions] = useSiteOptions();
  const [state, setState] = useState('OPEN');
  const [source, setSource] = useState('');
  const [q, setQ] = useState('');
  const [qq, setQq] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [linkSite, setLinkSite] = useState(null);
  const [adoptSite, setAdoptSite] = useState(null);
  const [ackIds, setAckIds] = useState(null);
  const [msg, setMsg] = useState('');
  const [tick, setTick] = useState(0);

  useEffect(() => { const t = setTimeout(() => { setQq(q.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [q]);
  const params = useMemo(() => {
    const p = new URLSearchParams({ state, page, page_size: 50 });
    if (qq) p.set('q', qq);
    if (source) p.set('source', source);
    return p.toString();
  }, [state, page, qq, source]);
  const load = useCallback(() => {
    api.get(`/api/site-reference/unknown-sites?${params}`).then((d) => { setData(d); setErr(null); }).catch(setErr);
  }, [params]);
  useEffect(() => { load(); }, [load, tick]);
  useEffect(() => { setSel(new Set()); }, [params]);
  const done = (text) => { setMsg(text); setTick((x) => x + 1); reloadOptions(); onChanged?.(); };

  const items = data?.items || [];
  const allOnPage = items.length > 0 && items.every((i) => sel.has(i.anomaly_id));
  const toggleAll = () => setSel((s) => { const n = new Set(s); items.forEach((i) => (allOnPage ? n.delete(i.anomaly_id) : n.add(i.anomaly_id))); return n; });
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const doAck = async (note) => {
    try {
      const r = await api.post('/api/site-reference/unknown-sites/ack', { anomaly_ids: ackIds, note: note || null });
      setAckIds(null); setSel(new Set()); done(`${r.acknowledged} site(s) ignoré(s).`);
    } catch (ex) { setErr(ex); setAckIds(null); }
  };

  return (
    <div className="stack">
      <section className="card mgr">
        <div className="mgr-head">
          <div>
            <h3>Sites remontés par les OMC, absents du référentiel</h3>
            <p className="small muted">Détectés à chaque collecte. Pour chacun : le rattacher au bon site (code erroné ou différent dans l'OMC),
              l'ajouter au référentiel (nouveau site), ou l'ignorer (site de test…).</p>
          </div>
          <div className="actions">
            {canExport && <button type="button" className="btn btn-ghost" onClick={() => api.download(`/api/site-reference/unknown-sites/export?format=xlsx&state=${state === 'OPEN' ? 'OPEN' : state}`).catch(setErr)}>Exporter (Excel)</button>}
          </div>
        </div>
        {data && !data.reference_loaded && (
          <div className="alert alert-warn">Aucun référentiel importé : la détection des sites inconnus démarre dès le premier import (onglet « Importer »).</div>
        )}
        <div className="mgr-filters">
          <div className="seg" role="group" aria-label="Traitement">
            {[['OPEN', `À traiter (${fmtInt(data?.counts.open ?? 0)})`], ['ACKNOWLEDGED', `Ignorés (${fmtInt(data?.counts.acknowledged ?? 0)})`], ['CURRENT', 'Tous']].map(([v, l]) => (
              <button key={v} type="button" className={state === v ? 'on' : ''} aria-pressed={state === v} onClick={() => { setState(v); setPage(1); }}>{l}</button>
            ))}
          </div>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Code, nom OMC ou code suggéré" aria-label="Rechercher" maxLength={80} />
          <select value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }} aria-label="OMC">
            <option value="">Tous les OMC</option>
            {(options?.omc_sources || []).map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        {msg && <div className="alert alert-info" role="status">{msg}<button type="button" className="btn btn-icon" aria-label="Masquer" onClick={() => setMsg('')}>✕</button></div>}
        <ErrorBox error={err} onRetry={load} />
        {isSupervisor && sel.size > 0 && (
          <div className="bulk-bar" role="region" aria-label="Actions sur la sélection">
            <b>{sel.size} sélectionné(s)</b>
            <button type="button" className="btn btn-ghost" onClick={() => setAckIds([...sel])}>Ignorer la sélection</button>
            <button type="button" className="btn btn-ghost" onClick={() => setSel(new Set())}>Désélectionner</button>
          </div>
        )}
        <div className="table-scroll">
          <table className="tbl tbl-compact mgr-table">
            <thead><tr>
              {isSupervisor && <th className="col-check"><input type="checkbox" checked={allOnPage} onChange={toggleAll} aria-label="Tout sélectionner sur la page" /></th>}
              <th>Code OMC</th><th>Remonté par</th><th>Technos</th><th>État</th><th>Position</th><th>Depuis</th><th>Site proche au référentiel</th>
              <th className="col-actions"><span className="sr-only">Actions</span></th>
            </tr></thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.anomaly_id} className={sel.has(u.anomaly_id) ? 'selected' : ''}>
                  {isSupervisor && <td className="col-check"><input type="checkbox" checked={sel.has(u.anomaly_id)} onChange={() => toggle(u.anomaly_id)} aria-label={`Sélectionner ${u.external_id}`} /></td>}
                  <td><Link to={`/?site=${u.site_id}&ref=ALL`} className="mono"><b>{u.external_id}</b></Link><div className="small">{u.name !== u.external_id ? u.name : ''}</div>
                    {u.state === 'ACKNOWLEDGED' && <div className="small muted">ignoré par {u.acknowledged_by}{u.note ? ` : « ${u.note} »` : ''}</div>}</td>
                  <td className="small">{u.sources || '—'}<div className="muted">{VENDOR_LABEL[u.vendor] || u.vendor} · {u.elements} équip.</div></td>
                  <td><TechChips techs={u.technologies} /></td>
                  <td><StatusBadge status={u.status} small />{u.active_alarms > 0 && <div className="small muted">{u.active_alarms} alarme(s)</div>}</td>
                  <td className="small">{u.latitude != null ? <>{u.latitude.toFixed(4)}, {u.longitude.toFixed(4)}<div className="muted">{u.wilaya_name}</div></> : <span className="muted">non fournie</span>}</td>
                  <td className="small" title={fmtDate(u.first_detected_at)}>{since(u.first_detected_at)}<div className="muted">vu {since(u.last_observed_at)}</div></td>
                  <td className="small">{u.suggestion ? (
                    <><b className="mono">{u.suggestion}</b> {u.suggestion_name}<div className="muted">{u.suggestion_wilaya}{u.suggestion_distance_m != null && ` · à ${fmtDist(u.suggestion_distance_m)}`}</div></>
                  ) : <span className="muted">aucun code proche</span>}</td>
                  <td className="col-actions"><div className="row-actions">
                    {isAdmin && <button type="button" className="btn btn-ghost" onClick={() => setLinkSite(u)}>{u.suggestion ? `Rattacher à ${u.suggestion}` : 'Rattacher…'}</button>}
                    {isAdmin && <button type="button" className="btn btn-ghost" onClick={() => setAdoptSite({ ...u, id: u.site_id })}>Ajouter</button>}
                    {isSupervisor && u.state === 'OPEN' && <button type="button" className="btn btn-ghost" onClick={() => setAckIds([u.anomaly_id])}>Ignorer</button>}
                  </div></td>
                </tr>
              ))}
              {data && !items.length && <tr><td colSpan={9} className="empty">{state === 'OPEN' ? 'Aucun site inconnu à traiter : tous les sites remontés par les OMC sont au référentiel.' : 'Aucun site.'}</td></tr>}
            </tbody>
          </table>
        </div>
        {data && <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />}
      </section>
      <Aliases refreshKey={tick} onChanged={() => { setTick((x) => x + 1); onChanged?.(); }} />

      <LinkDialog open={!!linkSite} site={linkSite} onClose={() => setLinkSite(null)}
        onDone={(r) => { setLinkSite(null); done(`Code ${r.omc_code} rattaché au site ${r.site} (${r.elements_moved} équipement(s) transféré(s)).`); }} />
      <SiteFormDialog open={!!adoptSite} mode="adopt" site={adoptSite} options={options} onClose={() => setAdoptSite(null)}
        onSaved={(r) => { setAdoptSite(null); done(`Site ${r.code} ajouté au référentiel.`); }} />
      <AckDialog open={!!ackIds} count={ackIds?.length || 0} onClose={() => setAckIds(null)} onDone={doAck} />
    </div>
  );
}
