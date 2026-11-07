import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import { ANOMALY, REF_STATUS, STATUS, VENDOR_LABEL, fmtDate, fmtDuration, since } from '../lib/constants';
import { ErrorBox, Pagination, SeverityBadge, Spinner, StatusBadge, TechChips } from './ui';

function KV({ label, children }) {
  return <div className="kv"><dt>{label}</dt><dd>{children ?? '—'}</dd></div>;
}

function Extra({ data }) {
  const entries = Object.entries(data || {}).filter(([k]) => k !== 'import_line' && k !== 'reference');
  if (!entries.length) return <p className="muted">Aucune information complémentaire.</p>;
  return <dl className="kvs">{entries.map(([k, v]) => <KV key={k} label={k}>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</KV>)}</dl>;
}

function History({ siteId, initial }) {
  const [page, setPage] = useState(1);
  const [level, setLevel] = useState('');
  const [data, setData] = useState(initial);
  useEffect(() => {
    if (page === 1 && !level) { setData(initial); return; }
    api.get(`/api/sites/${siteId}/history?page=${page}&page_size=30${level ? `&level=${level}` : ''}`).then(setData);
  }, [siteId, page, level, initial]);
  if (!data) return null;
  return (
    <>
      <div className="seg">
        {[['', 'Tout'], ['SITE', 'Site'], ['ELEMENT', 'Équipements']].map(([v, l]) => (
          <button key={v} type="button" className={level === v ? 'on' : ''} onClick={() => { setLevel(v); setPage(1); }}>{l}</button>
        ))}
      </div>
      {!data.items.length ? <p className="muted">Aucun changement d'état enregistré.</p> : (
        <ol className="timeline">
          {data.items.map((h) => (
            <li key={h.id} style={{ '--c': STATUS[h.new_status]?.color }}>
              <div className="tl-head">
                <span>{fmtDate(h.changed_at)}</span>
                <span className="muted">{h.entity_type === 'SITE' ? 'Site' : `${h.technology} · ${h.element_external_id}`}</span>
              </div>
              <div className="tl-body">
                <StatusBadge status={h.old_status} small /> → <StatusBadge status={h.new_status} small />
                <span className="muted"> durée : {h.ended_at ? fmtDuration((new Date(h.ended_at) - new Date(h.changed_at)) / 1000) : `${since(h.changed_at)} (en cours)`}</span>
              </div>
              {h.reason && <div className="tl-reason">{h.reason}</div>}
              <div className="muted small">Source : {h.source}</div>
            </li>
          ))}
        </ol>
      )}
      <Pagination page={page} pageSize={30} total={data.total} onPage={setPage} />
    </>
  );
}

export default function SiteDetail({ siteId, onClose, onCenter, refreshKey }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTab] = useState('info');
  const load = useCallback(() => {
    setErr(null);
    api.get(`/api/sites/${siteId}`).then(setD).catch(setErr);
  }, [siteId]);
  useEffect(() => { setD(null); setTab('info'); load(); }, [siteId, load]);
  useEffect(() => { if (refreshKey) load(); }, [refreshKey, load]);

  const s = d?.site;
  return (
    <section className="panel detail" aria-label="Fiche du site">
      <header className="panel-head">
        <div>
          <div className="eyebrow">{s ? s.external_id : 'Site'}</div>
          <h2>{s ? s.name : '…'}</h2>
        </div>
        <div className="actions">
          {s?.latitude != null && <button type="button" className="btn btn-ghost" onClick={() => onCenter(s)}>Centrer</button>}
          <button type="button" className="btn btn-icon" onClick={onClose} aria-label="Fermer la fiche">✕</button>
        </div>
      </header>
      <ErrorBox error={err} onRetry={load} />
      {!d && !err && <Spinner />}
      {s && (
        <>
          <div className="status-hero" style={{ '--c': STATUS[s.status]?.color }}>
            <StatusBadge status={s.status} />
            <span>depuis {fmtDate(s.status_since)} <span className="muted">({since(s.status_since)})</span></span>
            {s.status_reason && <p>{s.status_reason}</p>}
            {s.pending_status && <p className="muted">Changement en cours de confirmation : {s.pending_status} depuis {fmtDate(s.pending_since)}</p>}
          </div>
          {d.warnings.map((w) => <div key={w} className="alert alert-warn">{w}</div>)}
          {(d.anomalies || []).map((a) => (
            <div key={a.id} className="alert alert-anomaly" style={{ '--c': ANOMALY[a.anomaly_type]?.color }}>
              <b>{ANOMALY[a.anomaly_type]?.label || a.anomaly_type}</b>
              {a.state === 'ACKNOWLEDGED' && <span className="muted small"> · pris en compte par {a.acknowledged_by}</span>}
              <div className="small">{ANOMALY[a.anomaly_type]?.help}</div>
              {a.details?.suggestion && <div className="small">Code proche au référentiel : <b>{a.details.suggestion}</b></div>}
              {a.note && <div className="small muted">« {a.note} »</div>}
            </div>
          ))}
          <nav className="tabs" role="tablist">
            {[['info', 'Détails'], ['elements', `Équipements (${d.elements.length})`],
              ['alarms', `Alarmes (${d.active_alarms.length})`], ['history', 'Historique']].map(([k, l]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
            ))}
          </nav>
          <div className="panel-body">
            {tab === 'info' && (
              <>
                <dl className="kvs">
                  <KV label="Identifiant">{s.external_id} <span className="muted">(n° interne {s.id})</span></KV>
                  <KV label="Wilaya">{s.wilaya_code ? `${String(s.wilaya_code).padStart(2, '0')} · ${s.wilaya_name}` : null}</KV>
                  <KV label="Région">{s.region}</KV>
                  <KV label="Commune">{s.commune}</KV>
                  <KV label="Adresse">{s.address}</KV>
                  <KV label="Coordonnées GPS">{s.latitude != null ? `${s.latitude.toFixed(6)}, ${s.longitude.toFixed(6)}` : 'Non renseignées'}</KV>
                  <KV label="Équipementier">{VENDOR_LABEL[s.vendor] || s.vendor}</KV>
                  <KV label="Technologies"><TechChips techs={s.technologies} /></KV>
                  <KV label="Dernière mise à jour">{fmtDate(s.last_observed_at)}{s.is_stale && <span className="tag-warn">périmée</span>}</KV>
                  <KV label="Connu depuis">{fmtDate(s.first_seen_at)}</KV>
                </dl>
                <h3>Référentiel des sites</h3>
                {s.in_reference ? (
                  <dl className="kvs">
                    <KV label="Catégorie">{REF_STATUS[s.ref_status]?.label || s.ref_status}</KV>
                    <KV label="Cycle de vie">{s.lifecycle}</KV>
                    <KV label="Direction régionale">{s.dr}</KV>
                    <KV label="Technologies (référentiel)"><TechChips techs={s.ref_technologies} /></KV>
                    <KV label="Supervision">{s.is_supervised ? 'Remonté par un OMC' : 'Aucun OMC ne remonte ce site'}
                      {s.last_supervised_at && <div className="muted small">dernière remontée {fmtDate(s.last_supervised_at)}</div>}</KV>
                    <KV label="Importé le">{fmtDate(s.reference_seen_at)}</KV>
                    {Object.entries(s.extra?.reference || {}).map(([k, v]) => <KV key={k} label={k}>{String(v)}</KV>)}
                  </dl>
                ) : <p className="muted">Ce site ne figure pas dans le référentiel importé{s.is_supervised ? ' : il est connu uniquement par les OMC.' : '.'}</p>}
                <h3>Dernière alarme connue</h3>
                {d.last_alarm ? (
                  <div className="alarm-card">
                    <SeverityBadge severity={d.last_alarm.severity} /> <b>{d.last_alarm.alarm_code}</b> {d.last_alarm.description}
                    <div className="muted small">{fmtDate(d.last_alarm.raised_at)} · {d.last_alarm.state === 'ACTIVE' ? 'active' : `terminée le ${fmtDate(d.last_alarm.cleared_at)}`} · {d.last_alarm.omc_code}</div>
                  </div>
                ) : <p className="muted">Aucune alarme enregistrée.</p>}
                <h3>Informations complémentaires (OMC)</h3>
                <Extra data={s.extra} />
              </>
            )}
            {tab === 'elements' && (
              <table className="tbl tbl-compact">
                <thead><tr><th>Techno</th><th>Équipement</th><th>État</th><th>Observé</th><th>OMC</th></tr></thead>
                <tbody>
                  {d.elements.map((e) => (
                    <tr key={e.id} className={e.is_active ? '' : 'inactive'}>
                      <td><span className={`tech tech-${e.technology}`}>{e.technology}</span></td>
                      <td>{e.name || e.external_id}<div className="muted small">{e.element_type} · {e.external_id}</div></td>
                      <td><StatusBadge status={e.is_stale ? 'UNKNOWN' : e.oper_status} small />
                        {e.is_stale && <div className="muted small">dernier : {e.oper_status}</div>}
                        {e.raw_status && <div className="muted small">brut : {e.raw_status}</div>}</td>
                      <td>{fmtDate(e.status_observed_at)}{e.last_communication_at && <div className="muted small">comm. {fmtDate(e.last_communication_at)}</div>}</td>
                      <td>{e.omc_code}{e.is_demo && <div className="tag-warn">fictif</div>}
                        {!e.integration_validated && !e.is_demo && <div className="muted small">non validée</div>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tab === 'alarms' && (d.active_alarms.length ? (
              <ul className="alarm-list">
                {d.active_alarms.map((a) => (
                  <li key={a.id} className="alarm-card">
                    <SeverityBadge severity={a.severity} /> <b>{a.alarm_code}</b> {a.description}
                    <div className="muted small">depuis {fmtDate(a.raised_at)} ({since(a.raised_at)}) · {a.omc_code}</div>
                  </li>
                ))}
              </ul>
            ) : <p className="muted">Aucune alarme active.</p>)}
            {tab === 'history' && <History siteId={s.id} initial={d.history} />}
          </div>
        </>
      )}
    </section>
  );
}
