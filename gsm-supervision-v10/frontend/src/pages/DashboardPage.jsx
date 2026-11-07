import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import FiltersPanel from '../components/FiltersPanel';
import KpiStrip from '../components/KpiStrip';
import { ErrorBox, Spinner, StatusBadge } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { ANOMALY, REFRESH_MS, STATUS, VENDOR_LABEL, fmtDate, fmtDuration, fmtInt, since } from '../lib/constants';
import { toQuery, useFilters } from '../lib/filters';

const STACK = ['DOWN', 'DEGRADED', 'UNKNOWN', 'UP'];
const PROBLEMS = ['DOWN', 'DEGRADED', 'UNKNOWN'];
const key = (s) => s.toLowerCase();
const HEALTH = {
  OK: ['OK', '#16a34a'], FAILED: ['Échec', '#dc2626'], LATE: ['En retard', '#ea8a0c'],
  DISABLED: ['Désactivée', '#8a94a6'], MANUAL: ['Import manuel', '#2563eb'],
};

function Card({ title, children, actions, className = '' }) {
  return (
    <section className={`card ${className}`}>
      <header><h3>{title}</h3>{actions}</header>
      {children}
    </section>
  );
}

function Seg({ value, options, onChange }) {
  return (
    <div className="seg">
      {options.map(([v, l]) => <button key={v} type="button" className={value === v ? 'on' : ''} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}

function StackedBars({ data, labelKey = 'key', fmt = (x) => x, height = 220 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      {/* Sites supervisés uniquement : les sites du référentiel non remontés par un OMC ne sont pas des anomalies d'exploitation */}
      <BarChart data={data.filter((d) => d.total > (d.unsupervised || 0))
        .map((d) => ({ ...d, label: `${fmt(d[labelKey])} (${fmtInt(d.total - (d.unsupervised || 0))})` }))} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="label" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} width={48} />
        <Tooltip formatter={(v, n) => [fmtInt(v), STATUS[n.toUpperCase()]?.long || n]} />
        {PROBLEMS.map((s) => <Bar key={s} dataKey={key(s)} stackId="a" fill={STATUS[s].color} name={key(s)} />)}
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function DashboardPage() {
  const { filters, setFilters, query } = useFilters();
  const { canExport } = useAuth();
  const nav = useNavigate();
  const [sum, setSum] = useState(null);
  const [trend, setTrend] = useState(null);
  const [outages, setOutages] = useState(null);
  const [avail, setAvail] = useState(null);
  const [days, setDays] = useState(7);
  const [availDays, setAvailDays] = useState(7);
  const [availGroup, setAvailGroup] = useState('wilaya');
  const [hours, setHours] = useState(24);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), REFRESH_MS); return () => clearInterval(t); }, []);
  useEffect(() => {
    api.get(`/api/dashboard/summary?${toQuery(filters, { recent_hours: hours })}`).then((s) => { setSum(s); setErr(null); }).catch(setErr);
  }, [query, hours, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const v = filters.vendor?.length === 1 ? `&vendor=${filters.vendor[0]}` : '';
    const w = filters.wilaya?.length === 1 ? `&wilaya=${filters.wilaya[0]}` : '';
    api.get(`/api/dashboard/trend?days=${days}${v}${w}`).then(setTrend).catch(setErr);
  }, [days, filters.vendor, filters.wilaya, tick]);
  useEffect(() => {
    api.get(`/api/dashboard/outages?${toQuery(filters, { hours, limit: 200 })}`).then(setOutages).catch(setErr);
  }, [query, hours, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.get(`/api/dashboard/availability?${toQuery(filters, { days: availDays, group: availGroup, limit: 30 })}`)
      .then(setAvail).catch(setErr);
  }, [query, availDays, availGroup]); // eslint-disable-line react-hooks/exhaustive-deps

  const toMap = (extra) => nav(`/?${toQuery({ ...filters, ...extra })}`);
  const exportOutages = (format) => api.download(`/api/export/outages?${toQuery(filters, { hours, format })}`).catch(setErr);

  if (!sum && !err) return <Spinner />;
  return (
    <div className={`dash-page${showFilters ? ' with-filters' : ''}`}>
      {showFilters && <FiltersPanel filters={filters} setFilters={setFilters} compact />}
      <div className="dash">
        <div className="toolbar">
          <button type="button" className="btn btn-ghost" onClick={() => setShowFilters((x) => !x)}>☰ Filtres</button>
          <h1>Tableau de bord</h1>
          <div className="spacer" />
          <span className="muted small">Calculé le {fmtDate(sum?.generated_at)}</span>
          <button type="button" className="btn btn-ghost" onClick={() => setTick((x) => x + 1)}>↻</button>
        </div>
        <ErrorBox error={err} />
        {sum && (
          <>
            <KpiStrip totals={sum.totals} active={filters.status} onPick={(st) => toMap({ status: st })} />
            <div className="grid">
              <Card title={`Pannes détectées (${hours} h)`} className="span-1 stat-card">
                <div className="big">{fmtInt(sum.recent_outages.outages)}</div>
                <div className="muted">sur {fmtInt(sum.recent_outages.sites)} site(s)</div>
                <Seg value={hours} onChange={setHours} options={[[1, '1 h'], [24, '24 h'], [168, '7 j']]} />
              </Card>
              <Card title="Sites en anomalie par équipementier" className="span-1">
                <StackedBars data={sum.by_vendor} fmt={(v) => VENDOR_LABEL[v] || v} height={180} />
              </Card>
              <Card title="Sites en anomalie par technologie" className="span-1">
                <StackedBars data={sum.by_technology} height={180} />
              </Card>
              {sum.reference?.sites > 0 && (
                <Card title="Sites en anomalie par direction régionale" className="span-2">
                  <StackedBars data={sum.by_dr} height={200} />
                </Card>
              )}
              {sum.reference?.sites > 0 && (
                <Card title="Référentiel des sites" className="span-1"
                  actions={<Link to="/referentiel" className="small">Détails ›</Link>}>
                  <div className="muted small">{fmtInt(sum.reference.supervised)} / {fmtInt(sum.reference.sites)} sites du référentiel remontés par un OMC</div>
                  <ul className="anom-list">
                    {Object.entries(ANOMALY).map(([k, v]) => (
                      <li key={k}><span className="anom" style={{ '--c': v.color }}>{v.short}</span>
                        <b>{fmtInt(sum.anomalies.by_type[k] || 0)}</b></li>
                    ))}
                  </ul>
                </Card>
              )}
              <Card title="Évolution des états" className="span-2"
                actions={<Seg value={days} onChange={setDays} options={[[1, '24 h'], [7, '7 j'], [30, '30 j']]} />}>
                {trend?.points.length ? (
                  <ResponsiveContainer width="100%" height={240}>
                    <AreaChart data={trend.points.map((p) => ({ ...p, label: fmtDate(p.t) }))} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={40} />
                      <YAxis tick={{ fontSize: 12 }} width={48} />
                      <Tooltip formatter={(v, n) => [fmtInt(v), STATUS[n.toUpperCase()]?.long || n]} />
                      <Legend formatter={(n) => STATUS[n.toUpperCase()]?.long || n} />
                      {['down', 'degraded', 'unknown'].map((k) => (
                        <Area key={k} type="monotone" dataKey={k} stackId="1" stroke={STATUS[k.toUpperCase()].color}
                          fill={STATUS[k.toUpperCase()].color} fillOpacity={0.35} />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                ) : <p className="muted">Pas encore d'instantané : la courbe se remplit au fil des collectes (toutes les 15 min par défaut).</p>}
              </Card>
              <Card title="Sites en anomalie par région" className="span-1">
                <StackedBars data={sum.by_region} height={240} />
              </Card>
              <Card title="Répartition par wilaya" className="span-2 scroll">
                <table className="tbl tbl-compact">
                  <thead><tr><th>Wilaya</th><th>Total</th>{STACK.map((s) => <th key={s}><StatusBadge status={s} small /></th>)}<th>% UP</th></tr></thead>
                  <tbody>
                    {sum.by_wilaya.map((w) => (
                      <tr key={w.code ?? 'none'} className="clickable" onClick={() => w.code && toMap({ wilaya: [String(w.code)] })}>
                        <td>{w.code ? `${String(w.code).padStart(2, '0')} · ` : ''}{w.name}</td>
                        <td>{fmtInt(w.total)}</td>
                        {STACK.map((s) => <td key={s} className={w[key(s)] && s !== 'UP' ? `num-${s}` : ''}>{fmtInt(w[key(s)])}</td>)}
                        <td>{w.total ? ((100 * w.up) / w.total).toFixed(1) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
              <Card title="Sources OMC — dernière synchronisation" className="span-1 scroll">
                <ul className="omc-list">
                  {sum.omc_sources.map((o) => (
                    <li key={o.code}>
                      <span className="health" style={{ background: HEALTH[o.health][1] }} title={HEALTH[o.health][0]} />
                      <div>
                        <b>{o.code}</b> <span className="muted small">{VENDOR_LABEL[o.vendor]} · {o.connector_type}</span>
                        {o.is_demo && <span className="tag-warn">fictif</span>}
                        {!o.integration_validated && !o.is_demo && <span className="tag">non validée</span>}
                        <div className="small">{HEALTH[o.health][0]} · dernier succès {o.last_success_at ? `il y a ${since(o.last_success_at)}` : 'jamais'}</div>
                        {o.last_error && <div className="small err">{o.last_error}</div>}
                      </div>
                    </li>
                  ))}
                  {!sum.omc_sources.length && <li className="muted">Aucune source configurée.</li>}
                </ul>
                <div className="small muted">
                  Service de collecte : {sum.services.length
                    ? sum.services.map((s) => `${s.host} ${s.alive ? 'actif' : `silencieux depuis ${fmtDuration(s.age_s)}`}`).join(', ')
                    : 'jamais démarré'}
                </div>
              </Card>
              <Card title={`Dernières pannes (${hours} h)`} className="span-2 scroll"
                actions={canExport && <div className="actions">
                  <button type="button" className="btn btn-ghost" onClick={() => exportOutages('xlsx')}>Excel</button>
                  <button type="button" className="btn btn-ghost" onClick={() => exportOutages('csv')}>CSV</button></div>}>
                <table className="tbl tbl-compact">
                  <thead><tr><th>Début</th><th>Site</th><th>Wilaya</th><th>Équip.</th><th>Durée</th><th>Actuel</th></tr></thead>
                  <tbody>
                    {outages?.items.map((o) => (
                      <tr key={`${o.site_id}-${o.started_at}`} className="clickable" onClick={() => nav(`/?site=${o.site_id}`)}>
                        <td>{fmtDate(o.started_at)}</td>
                        <td><b>{o.external_id}</b> {o.name}</td>
                        <td>{o.wilaya_name || '—'}</td>
                        <td>{VENDOR_LABEL[o.vendor]}</td>
                        <td>{fmtDuration(o.duration_s)}{!o.ended_at && <span className="tag-down">en cours</span>}</td>
                        <td><StatusBadge status={o.current_status} small /></td>
                      </tr>
                    ))}
                    {outages && !outages.items.length && <tr><td colSpan={6} className="empty">Aucune panne sur la période.</td></tr>}
                  </tbody>
                </table>
              </Card>
              <Card title="Disponibilité" className="span-1 scroll"
                actions={<Seg value={availDays} onChange={setAvailDays} options={[[1, '24 h'], [7, '7 j'], [30, '30 j']]} />}>
                <Seg value={availGroup} onChange={setAvailGroup}
                  options={[['wilaya', 'Wilaya'], ['vendor', 'Équip.'], ['region', 'Région'], ['site', 'Site']]} />
                <table className="tbl tbl-compact">
                  <thead><tr><th>{availGroup === 'site' ? 'Site' : 'Groupe'}</th><th>Dispo.</th><th>h DOWN</th></tr></thead>
                  <tbody>
                    {avail?.items.map((a) => (
                      <tr key={a.key}>
                        <td>{VENDOR_LABEL[a.key] || a.key}</td>
                        <td className={a.availability_pct < 99 ? 'num-DOWN' : ''}>{a.availability_pct != null ? `${Number(a.availability_pct).toFixed(2)} %` : '—'}</td>
                        <td>{Number(a.down_hours).toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="small muted">Disponibilité = 1 − temps DOWN / temps observé (périodes « inconnu » exclues).</p>
              </Card>
            </div>
            <p className="small muted">Les compteurs utilisent exactement les mêmes filtres que la carte. <Link to={`/?${query}`}>Voir sur la carte →</Link></p>
          </>
        )}
      </div>
    </div>
  );
}
