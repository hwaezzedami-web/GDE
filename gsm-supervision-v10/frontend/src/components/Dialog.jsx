import { useEffect, useId, useRef } from 'react';

// Fenêtre modale native (<dialog> + showModal) : le navigateur rend la page inerte, garde le focus
// dans la fenêtre, gère Échap et rend le focus au bouton d'origine à la fermeture.
// Pas de role="dialog", aria-modal, piège à focus ou gestion d'Échap manuels : ils feraient doublon.
export default function Dialog({ open, onClose, title, children, footer, wide, lightDismiss = false, describedBy }) {
  const ref = useRef(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    else if (!open && d.open) d.close();
  }, [open]);

  // Fermeture par clic à l'extérieur là où l'attribut closedby n'est pas pris en charge (Safari)
  useEffect(() => {
    const d = ref.current;
    if (!d || !lightDismiss || 'closedBy' in HTMLDialogElement.prototype) return undefined;
    const outside = (e) => {
      const r = d.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    let pressedOutside = false;
    const down = (e) => { pressedOutside = outside(e); };
    const up = (e) => { if (pressedOutside && outside(e)) d.close(); };
    d.addEventListener('pointerdown', down);
    d.addEventListener('pointerup', up);
    return () => { d.removeEventListener('pointerdown', down); d.removeEventListener('pointerup', up); };
  }, [lightDismiss]);

  return (
    <dialog ref={ref} className={`modal${wide ? ' modal-wide' : ''}`} aria-labelledby={titleId}
      aria-describedby={describedBy} closedby={lightDismiss ? 'any' : 'closerequest'}
      onClose={() => { if (open) onClose?.(); }}>
      {open && (
        <>
          <header className="modal-head">
            <h2 id={titleId}>{title}</h2>
            <button type="button" className="btn btn-icon" aria-label="Fermer" onClick={() => ref.current?.close()}>✕</button>
          </header>
          <div className="modal-body">{children}</div>
          {footer && <footer className="modal-foot">{footer}</footer>}
        </>
      )}
    </dialog>
  );
}

// Confirmation (remplace window.confirm) : bouton sûr (Annuler) focalisé par défaut
export function ConfirmDialog({ open, title, children, confirmLabel = 'Confirmer', danger, busy, onConfirm, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} title={title} lightDismiss
      footer={(
        <>
          <button type="button" className="btn btn-ghost" autoFocus onClick={onClose}>Annuler</button>
          <button type="button" className={`btn${danger ? ' btn-danger' : ''}`} disabled={busy} onClick={onConfirm}>
            {busy ? 'Traitement…' : confirmLabel}
          </button>
        </>
      )}>
      {children}
    </Dialog>
  );
}
