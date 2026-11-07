import { STATUS, fmtInt } from '../lib/constants';

// Bandeau de compteurs cliquables : un clic filtre la carte sur l'état.
export default function KpiStrip({ totals, onPick, active = [] }) {
  if (!totals) return <div className="kpis skeleton" />;
  const items = [
    ['TOTAL', 'Sites', totals.total, '#0f2a3f'],
    ['DOWN', STATUS.DOWN.long, totals.down, STATUS.DOWN.color],
    ['DEGRADED', 'Dégradés', totals.degraded, STATUS.DEGRADED.color],
    ['UNKNOWN', 'Inconnus', totals.unknown, STATUS.UNKNOWN.color],
    ['UP', STATUS.UP.long, totals.up, STATUS.UP.color],
  ];
  // Sites du référentiel qu'aucun OMC ne remonte : affichés à part (ni pannes, ni états inconnus)
  if (totals.unsupervised) items.push(['UNSUPERVISED', 'Non supervisés', totals.unsupervised, STATUS.UNSUPERVISED.color]);
  return (
    <div className="kpis">
      {items.map(([k, label, v, c]) => (
        <button key={k} type="button" className={`kpi${active.length === 1 && active[0] === k ? ' on' : ''}`}
          style={{ '--c': c }} onClick={() => onPick?.(k === 'TOTAL' ? [] : [k])}>
          <span className="kpi-v">{fmtInt(v)}</span>
          <span className="kpi-l">{label}
            {k !== 'TOTAL' && totals.total > 0 && <span className="kpi-p"> · {((100 * v) / totals.total).toFixed(1)} %</span>}</span>
        </button>
      ))}
      {totals.stale > 0 && (
        <div className="kpi kpi-note" title="Sites dont une partie des données est périmée">
          <span className="kpi-v">{fmtInt(totals.stale)}</span><span className="kpi-l">données périmées</span>
        </div>
      )}
    </div>
  );
}
