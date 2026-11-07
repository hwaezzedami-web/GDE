import { useEffect, useRef, useState } from 'react';

// Respect de la préférence « réduire les animations » du système d'exploitation.
export const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

// Valeur qui s'incrémente en douceur vers `target` (sans animation si mouvement réduit).
export function useCountUp(target, duration = 520) {
  const [shown, setShown] = useState(target ?? 0);
  const from = useRef(target ?? 0);
  useEffect(() => {
    if (target == null) return undefined;
    if (reducedMotion() || from.current === target) {
      from.current = target;
      setShown(target);
      return undefined;
    }
    const start = performance.now();
    const origin = from.current;
    let frame;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3; // ease-out cubique
      setShown(Math.round(origin + (target - origin) * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return shown;
}
