import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ConfirmDialog } from '../components/Dialog';
import SiteFormDialog from '../components/SiteFormDialog';
import { ErrorBox, Pagination, StatusBadge, TechChips } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { REF_STATUS, fmtDate, fmtInt, since } from '../lib/constants';
import { useReference } from '../lib/reference';

const COLS = [
  ['code', 'Code'], ['name', 'Nom'], ['wilaya', 'Wilaya / commune'], ['dr', 'DR'], ['lifecycle', 'Cycle de vie'],
  [null, 'Technos'], ['status', 'État'], ['supervised', 'Supervision'], ['updated', 'Dernière modification'],
];

export function useSiteOptions() {
  const [opts, setOpts] = useState(null);
  const reload = useCallback(() => api.get('/api/site-reference/options').then(setOpts).catch(() => {}), []);
  useEffect(() => { reload(); }, [reload]);
  return [opts, reload];
}

export default function SitesManager({ onChanged, goImport }) {
  const { isAdmin, canExport } = useAuth();
  const ref = useReference();
  const [options, reloadOptions] = useSiteOptions();
  const [q, setQ] = useState('');
  const [qq, setQq] = useState('');
  const [flt, setFlt] = useState({ wilaya: '', dr: '', ref: '', supervised: '', source: '', anomalies: false });
  const [sort, setSort] = useState('code');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [form, setForm] = useState(null);           // { mode, site }
  const [confirm, setConfirm] = useState(null);     // { mode, ids, codes }
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => { const t = setTimeout(() => { setQq(q.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [q]);
  const params = useMemo(() => {
    const p = new URLSearchParams({ sort, page, page_size: pageSize });
    if (qq) p.set('q', qq);
    for (const k of ['wilaya', 'dr', 'ref', 'supervised', 'source']) if (flt[k] !== '') p.set(k, flt[k]);
    if (flt.anomalies) p.set('anomalies', 'true');
    return p;
  }, [qq, flt, sort, page, pageSize]);
  const load = useCallback(() => {
    api.get(`/api/site-reference/sites?${params}`).then((d) => { setData(d); setErr(null); }).catch(setErr);
  }, [params]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setSel(new Set()); }, [params]);

  const setF = (k) => (e) => { setFlt((x) => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })); setPage(1); };
  const sortBy = (k) => setSort((s) => (s === k ? `-${k}` : k));
  const items = data?.items || [];
  const allOnPage = items.length > 0 && items.every((i) => sel.has(i.id));
  const toggleAll = () => setSel((s) => { const n = new Set(s); items.forEach((i) => (allOnPage ? n.delete(i.id) : n.add(i.id))); return n; });
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const done = (text) => { setMsg(text); load(); reloadOptions(); onChanged?.(); };

  const askDelete = (mode, rows) => setConfirm({ mode, ids: rows.map((r) => r.id), codes: rows.map((r) => r.external_id),
    supervised: rows.filter((r) => r.is_supervised).length });
  const doDelete = async () => {
    setBusy(true);
    try {
      const r = await api.post('/api/site-reference/sites/delete', { ids: confirm.ids, mode: confirm.mode });
      const verb = confirm.mode === 'purge' ? 'supprimé(s) définitivement' : 'retiré(s) du référentiel';
      done(`${r.done.length} site(s) ${verb}.${r.skipped.length ? ` ${r.skipped.length} ignoré(s) : ${r.skipped.slice(0, 3).map((x) => `${x.code} (${x.reason})`).join(', ')}` : ''}`);
      setSel(new Set());
      setConfirm(null);
    } catch (ex) { setErr(ex); setConfirm(null); }
    setBusy(false);
  };
  const exportXlsx = () => {
    const p = new URLSearchParams(params); p.delete('page'); p.delete('page_size'); p.delete('sort'); p.set('format', 'xlsx');
    api.download(`/api/site-reference/sites/export?${p}`).catch(setErr);
  };
  const selectedRows = items.filter((i) => sel.has(i.id));

  return (
    <div className="card mgr">
      <div className="mgr-head">
        <div>
          <h3>Sites du référentiel</h3>
          <p className="small muted">{data ? `${fmtInt(data.total)} site(s)` : '…'} · recherche par code, nom, commune, adresse ou code OMC rattaché</p>
        </div>
        <div className="actions">
          {canExport && <button type="button" className="btn btn-ghost" onClick={exportXlsx}>Exporter (Excel)</button>}
          {isAdmin && goImport && <button type="button" className="btn btn-ghost" onClick={goImport}>Importer un fichier</button>}
          {isAdmin && <button type="button" className="btn" onClick={() => setForm({ mode: 'create', site: null })}>+ Nouveau site</button>}
        </div>
      </div>

      <div className="mgr-filters">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher…" aria-label="Rechercher un site" maxLength={80} />
        <select value={flt.wilaya} onChange={setF('wilaya')} aria-label="Wilaya">
          <option value="">Toutes les wilayas</option>
          {(ref?.wilayas || []).map((w) => <option key={w.code} value={w.code}>{String(w.code).padStart(2, '0')} · {w.name}</option>)}
        </select>
        <select value={flt.dr} onChange={setF('dr')} aria-label="Direction régionale">
          <option value="">Toutes les DR</option>
          {(options?.drs || []).map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={flt.ref} onChange={setF('ref')} aria-label="Catégorie">
          <option value="">Toutes catégories</option>
          {Object.entries(REF_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select value={flt.supervised} onChange={setF('supervised')} aria-label="Supervision">
          <option value="">Supervisés ou non</option>
          <option value="true">Remontés par un OMC</option>
          <option value="false">Non supervisés</option>
        </select>
        <select value={flt.source} onChange={setF('source')} aria-label="Origine">
          <option value="">Import et saisie</option>
          <option value="IMPORT">Importés d'un fichier</option>
          <option value="MANUAL">Saisis / modifiés à la main</option>
        </select>
        <label className="check-inline"><input type="checkbox" checked={flt.anomalies} onChange={setF('anomalies')} /> Avec anomalie</label>
      </div>

      {msg && <div className="alert alert-info" role="status">{msg}<button type="button" className="btn btn-icon" aria-label="Masquer" onClick={() => setMsg('')}>✕</button></div>}
      <ErrorBox error={err} onRetry={load} />

      {isAdmin && sel.size > 0 && (
        <div className="bulk-bar" role="region" aria-label="Actions sur la sélection">
          <b>{sel.size} sélectionné(s)</b>
          <button type="button" className="btn btn-ghost" onClick={() => askDelete('remove', selectedRows)}>Retirer du référentiel</button>
          <button type="button" className="btn btn-ghost danger" onClick={() => askDelete('purge', selectedRows)}>Supprimer définitivement</button>
          <button type="button" className="btn btn-ghost" onClick={() => setSel(new Set())}>Désélectionner</button>
        </div>
      )}

      <div className="table-scroll">
        <table className="tbl tbl-compact mgr-table">
          <thead>
            <tr>
              {isAdmin && <th className="col-check"><input type="checkbox" checked={allOnPage} onChange={toggleAll} aria-label="Tout sélectionner sur la page" /></th>}
              {COLS.map(([k, l]) => (
                <th key={l} className={k ? 'sortable' : ''} onClick={k ? () => sortBy(k) : undefined}
                  aria-sort={sort === k ? 'ascending' : sort === `-${k}` ? 'descending' : undefined}>
                  {l}{sort === k ? ' ▲' : sort === `-${k}` ? ' ▼' : ''}
                </th>
              ))}
              <th className="col-actions"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} className={sel.has(s.id) ? 'selected' : ''}>
                {isAdmin && <td className="col-check"><input type="checkbox" checked={sel.has(s.id)} onChange={() => toggle(s.id)} aria-label={`Sélectionner ${s.external_id}`} /></td>}
                <td className="mono"><b>{s.external_id}</b>
                  {s.aliases?.length > 0 && <div className="aliases" title="Codes remontés par les OMC et rattachés à ce site">{s.aliases.map((a) => <span key={a} className="alias">OMC {a}</span>)}</div>}</td>
                <td>{s.name}{s.anomalies > 0 && <span className="tag-warn" title="Anomalie de rapprochement en cours">anomalie</span>}</td>
                <td>{s.wilaya_name || '—'}<div className="small muted">{s.commune}</div></td>
                <td>{s.dr || '—'}</td>
                <td><span className="refcat" style={{ '--c': REF_STATUS[s.ref_status]?.color }}>{REF_STATUS[s.ref_status]?.label || s.ref_status}</span>
                  <div className="small muted mono">{s.lifecycle}</div></td>
                <td><TechChips techs={s.ref_technologies?.length ? s.ref_technologies : s.technologies} /></td>
                <td><StatusBadge status={s.status} small /></td>
                <td className="small">{s.is_supervised ? <>OMC · {since(s.last_supervised_at)}</> : <span className="muted">{s.last_supervised_at ? `perdue · ${since(s.last_supervised_at)}` : 'jamais'}</span>}</td>
                <td className="small">{s.ref_source === 'MANUAL' ? <span className="src-manual">Manuel</span> : 'Import'} · {s.ref_updated_by || '—'}
                  <div className="muted">{fmtDate(s.ref_updated_at)}</div></td>
                <td className="col-actions">
                  <Link className="btn btn-icon" to={`/?site=${s.id}&ref=ALL`} title="Voir sur la carte" aria-label={`Voir ${s.external_id} sur la carte`}>⌖</Link>
                  {isAdmin && <>
                    <button type="button" className="btn btn-icon" title="Modifier" aria-label={`Modifier ${s.external_id}`} onClick={() => setForm({ mode: 'edit', site: s })}>✎</button>
                    <button type="button" className="btn btn-icon danger" title="Retirer du référentiel" aria-label={`Retirer ${s.external_id}`} onClick={() => askDelete('remove', [s])}>🗑</button>
                  </>}
                </td>
              </tr>
            ))}
            {data && !items.length && <tr><td colSpan={COLS.length + 2} className="empty">Aucun site ne correspond.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="mgr-foot">
        {data && <Pagination page={page} pageSize={pageSize} total={data.total} onPage={setPage} />}
        <label className="small">Par page{' '}
          <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
            {[25, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
          </select></label>
      </div>

      <SiteFormDialog open={!!form} mode={form?.mode} site={form?.site} options={options} onClose={() => setForm(null)}
        onSaved={(r) => {
          const what = form.mode === 'edit' ? `Site ${r.code} modifié` : `Site ${r.code} ajouté au référentiel${r.adopted_from_omc ? ' (déjà remonté par un OMC : équipements conservés)' : ''}`;
          setForm(null); done(`${what}.`);
        }} />
      <ConfirmDialog open={!!confirm} danger={confirm?.mode === 'purge'} busy={busy} onClose={() => setConfirm(null)} onConfirm={doDelete}
        title={confirm?.mode === 'purge' ? 'Supprimer définitivement ?' : 'Retirer du référentiel ?'}
        confirmLabel={confirm?.mode === 'purge' ? 'Supprimer' : 'Retirer'}>
        {confirm && (
          <>
            <p><b>{confirm.codes.length} site(s)</b> : {confirm.codes.slice(0, 8).join(', ')}{confirm.codes.length > 8 ? '…' : ''}</p>
            {confirm.mode === 'remove'
              ? <p className="small">Les sites sortent du référentiel. {confirm.supervised > 0 && <b>{confirm.supervised} site(s) encore remonté(s) par un OMC resteront visibles et seront signalés comme « inconnus du référentiel ». </b>}L'historique est conservé.</p>
              : <p className="small">Le site et tout son historique sont effacés. Impossible pour un site encore remonté par un OMC (utiliser « Retirer »). <b>Action irréversible.</b></p>}
          </>
        )}
      </ConfirmDialog>
    </div>
  );
}
