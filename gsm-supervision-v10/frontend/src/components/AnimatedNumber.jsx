import { useCountUp } from '../lib/motion';
import { fmtInt } from '../lib/constants';

// Nombre affiché avec transition : le texte reste exact à la fin de l'animation.
export default function AnimatedNumber({ value }) {
  const shown = useCountUp(typeof value === 'number' ? value : null);
  return <span className="num-anim">{typeof value === 'number' ? fmtInt(shown) : fmtInt(value)}</span>;
}
