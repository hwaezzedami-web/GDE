import { SEVERITY, STATUS } from '../lib/constants';

export function StatusBadge({ status, small }) {
  const s = STATUS[status] || STATUS.UNKNOWN;
  return (
    <span className={`badge status-${status || 'UNKNOWN'}${small ? ' badge-sm' : ''}`} title={s.long}>
      <i className="dot" style={{ background: s.color }} />{s.label}
    </span>
  );
}

export function SeverityBadge({ severity }) {
  const s = SEVERITY[severity] || SEVERITY.INDETERMINATE;
  return <span className="sev" style={{ color: s.color, borderColor: s.color }}>{s.label}</span>;
}

export function TechChips({ techs }) {
  return (
    <span className="techs">
      {(techs || []).map((t) => <span key={t} className={`tech tech-${t}`}>{t}</span>)}
    </span>
  );
}

export function Pagination({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <span className="muted">{total.toLocaleString('fr-FR')} résultat{total > 1 ? 's' : ''}</span>
      <button type="button" className="btn btn-ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Préc.</button>
      <span>Page {page} / {pages}</span>
      <button type="button" className="btn btn-ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>Suiv. ›</button>
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="alert alert-error" role="alert">
      {error.message || String(error)}
      {onRetry && <button type="button" className="btn btn-ghost" onClick={onRetry}>Réessayer</button>}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function Spinner({ label = 'Chargement…' }) {
  return <div className="spinner" role="status"><span className="spin" />{label}</div>;
}
