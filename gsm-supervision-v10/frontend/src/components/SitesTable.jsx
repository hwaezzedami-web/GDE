import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { REF_STATUS, VENDOR_LABEL, fmtDate, since } from '../lib/constants';
import { toQuery } from '../lib/filters';
import { ErrorBox, Pagination, StatusBadge, TechChips } from './ui';

const COLS = [
  ['status', 'État'], ['external_id', 'Code site'], ['name', 'Nom'], ['wilaya', 'Wilaya'], [null, 'Commune'],
  ['dr', 'DR'], ['lifecycle', 'Référentiel'],
  ['vendor', 'Équip.'], [null, 'Technos'], ['status_since', 'Depuis'], [null, 'Motif'],
];

export default function SitesTable({ filters, onRowClick, selectedId, refreshKey }) {
  const { canExport } = useAuth();
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('status');
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const q = toQuery(filters);

  useEffect(() => { setPage(1); }, [q]);
  useEffect(() => {
    let alive = true;
    api.get(`/api/sites?${toQuery(filters, { page, page_size: 50, sort })}`)
      .then((r) => { if (alive) { setData(r); setErr(null); } }).catch((e) => alive && setErr(e));
    return () => { alive = false; };
  }, [q, page, sort, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const doExport = async (format) => {
    setBusy(true);
    try { await api.download(`/api/export/sites?${toQuery(filters, { format })}`); } catch (e) { setErr(e); }
    setBusy(false);
  };
  const sortBy = (k) => setSort((s) => (s === k ? `-${k}` : k));

  return (
    <div className="table-wrap">
      <div className="table-tools">
        <ErrorBox error={err} />
        {data && <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />}
        {canExport && (
          <div className="actions">
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => doExport('xlsx')}>Export Excel</button>
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => doExport('csv')}>Export CSV</button>
          </div>
        )}
      </div>
      <div className="table-scroll">
        <table className="tbl">
          <thead>
            <tr>
              {COLS.map(([k, l]) => (
                <th key={l} className={k ? 'sortable' : ''} onClick={k ? () => sortBy(k) : undefined}
                  aria-sort={sort === k ? 'ascending' : sort === `-${k}` ? 'descending' : undefined}>
                  {l}{sort === k ? ' ▲' : sort === `-${k}` ? ' ▼' : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.items.map((s) => (
              <tr key={s.id} className={`clickable${s.id === selectedId ? ' selected' : ''}`} tabIndex={0}
                onClick={() => onRowClick(s)} onKeyDown={(e) => e.key === 'Enter' && onRowClick(s)}>
                <td><StatusBadge status={s.status} small />{s.is_stale && <span className="tag-warn" title="Données périmées">!</span>}</td>
                <td className="mono">{s.external_id}</td>
                <td>{s.name}</td>
                <td>{s.wilaya_name || '—'}</td>
                <td>{s.commune || '—'}</td>
                <td>{s.dr || '—'}</td>
                <td title={s.lifecycle || ''}>{s.in_reference ? (REF_STATUS[s.ref_status]?.label || s.ref_status) : <span className="muted">hors réf.</span>}</td>
                <td>{VENDOR_LABEL[s.vendor] || s.vendor}</td>
                <td><TechChips techs={s.technologies} /></td>
                <td title={fmtDate(s.status_since)}>{since(s.status_since)}</td>
                <td className="reason">{s.status_reason}</td>
              </tr>
            ))}
            {data && !data.items.length && <tr><td colSpan={COLS.length} className="empty">Aucun site ne correspond aux filtres.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
