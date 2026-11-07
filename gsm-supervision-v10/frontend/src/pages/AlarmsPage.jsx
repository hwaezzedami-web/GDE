import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import FiltersPanel from '../components/FiltersPanel';
import { ErrorBox, Pagination, SeverityBadge, StatusBadge } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { REFRESH_MS, SEVERITY, fmtDate, since } from '../lib/constants';
import { toQuery, useFilters } from '../lib/filters';

export default function AlarmsPage() {
  const { filters, setFilters, query } = useFilters();
  const { canExport } = useAuth();
  const nav = useNavigate();
  const [state, setState] = useState('ACTIVE');
  const [sev, setSev] = useState([]);
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0);
  const [showFilters, setShowFilters] = useState(window.innerWidth > 900);

  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), REFRESH_MS); return () => clearInterval(t); }, []);
  useEffect(() => { setPage(1); }, [query, state, sev]);
  useEffect(() => {
    api.get(`/api/alarms?${toQuery(filters, { state, severity: sev, page, page_size: 50 })}`)
      .then((r) => { setData(r); setErr(null); }).catch(setErr);
  }, [query, state, sev, page, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const exp = (format) => api.download(`/api/export/alarms?${toQuery(filters, { state, severity: sev, format })}`).catch(setErr);
  return (
    <div className={`dash-page${showFilters ? ' with-filters' : ''}`}>
      {showFilters && <FiltersPanel filters={filters} setFilters={setFilters} compact showOutage={false} />}
      <div className="dash">
        <div className="toolbar">
          <button type="button" className="btn btn-ghost" onClick={() => setShowFilters((x) => !x)}>☰ Filtres</button>
          <h1>Alarmes</h1>
          <div className="seg">
            {[['ACTIVE', 'Actives'], ['CLEARED', 'Terminées'], ['ALL', 'Toutes']].map(([v, l]) => (
              <button key={v} type="button" className={state === v ? 'on' : ''} onClick={() => setState(v)}>{l}</button>
            ))}
          </div>
          <div className="chips">
            {Object.entries(SEVERITY).map(([k, s]) => (
              <button key={k} type="button" className={`chip${sev.includes(k) ? ' on' : ''}`} aria-pressed={sev.includes(k)}
                onClick={() => setSev((x) => (x.includes(k) ? x.filter((y) => y !== k) : [...x, k]))}>
                <i className="dot" style={{ background: s.color }} />{s.label}
                {data?.by_severity?.[k] != null && <em> {data.by_severity[k]}</em>}
              </button>
            ))}
          </div>
          <div className="spacer" />
          {canExport && <>
            <button type="button" className="btn btn-ghost" onClick={() => exp('xlsx')}>Excel</button>
            <button type="button" className="btn btn-ghost" onClick={() => exp('csv')}>CSV</button>
          </>}
        </div>
        <ErrorBox error={err} />
        <div className="card">
          {data && <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />}
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>Gravité</th><th>Début</th><th>Site</th><th>Wilaya</th><th>Techno</th><th>Code</th><th>Description</th><th>OMC</th><th>État site</th></tr></thead>
              <tbody>
                {data?.items.map((a) => (
                  <tr key={a.id} className={a.site_id ? 'clickable' : ''} onClick={() => a.site_id && nav(`/?site=${a.site_id}`)}>
                    <td><SeverityBadge severity={a.severity} /></td>
                    <td title={fmtDate(a.raised_at)}>{fmtDate(a.raised_at)}<div className="muted small">{a.state === 'ACTIVE' ? `depuis ${since(a.raised_at)}` : `fin ${fmtDate(a.cleared_at)}`}</div></td>
                    <td><b className="mono">{a.site_external_id || '—'}</b><div className="small">{a.site_name}</div></td>
                    <td>{a.wilaya_name || '—'}</td>
                    <td>{a.technology || '—'}</td>
                    <td className="mono">{a.alarm_code}</td>
                    <td>{a.description}</td>
                    <td>{a.omc_code}</td>
                    <td>{a.site_status ? <StatusBadge status={a.site_status} small /> : '—'}</td>
                  </tr>
                ))}
                {data && !data.items.length && <tr><td colSpan={9} className="empty">Aucune alarme.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
