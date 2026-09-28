const GaugeChart = ({ value, max = 100, size = 120, label, subs }) => {
  const r = (size - 16) / 2;
  const cx = size / 2;
  const cy = size / 2 + 6;
  const startAngle = -220;
  const endAngle = 40;
  const totalAngle = endAngle - startAngle;
  const pct = Math.min(value / max, 1);
  const valueAngle = startAngle + pct * totalAngle;

  const color = pct >= 0.9 ? '#0d9488'
    : pct >= 0.7 ? '#d97706'
    : '#dc2626';

  const pt = (a, rad) => ({
    x: cx + rad * Math.cos((a * Math.PI) / 180),
    y: cy + rad * Math.sin((a * Math.PI) / 180),
  });

  const arc = (from, to, rad) => {
    const s = pt(from, rad);
    const e = pt(to, rad);
    return `M ${s.x} ${s.y} A ${rad} ${rad} 0 ${to - from > 180 ? 1 : 0} 1 ${e.x} ${e.y}`;
  };

  const needlePt = pt(valueAngle, r - 6);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      {label && <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600, letterSpacing: '0.02em', textTransform: 'uppercase', marginBottom: 2 }}>{label}</div>}
      <svg width={size} height={size * 0.58} viewBox={`0 0 ${size} ${size * 0.62}`}>
        <defs>
          <linearGradient id={`g-${label?.replace(/\s/g,'')}-bg`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#e2e8f0" />
            <stop offset="100%" stopColor="#e2e8f0" />
          </linearGradient>
          <linearGradient id={`g-${label?.replace(/\s/g,'')}-fg`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={color} stopOpacity="0.6" />
            <stop offset="100%" stopColor={color} />
          </linearGradient>
          <filter id="needle-shadow"><feDropShadow dx="0" dy="1" stdDeviation="1.5" floodOpacity="0.2" /></filter>
        </defs>
        <path d={arc(startAngle, endAngle, r)} fill="none" stroke={`url(#g-${label?.replace(/\s/g,'')}-bg)`} strokeWidth={10} strokeLinecap="round" />
        {pct > 0 && <path d={arc(startAngle, valueAngle, r)} fill="none" stroke={`url(#g-${label?.replace(/\s/g,'')}-fg)`} strokeWidth={10} strokeLinecap="round" />}
        <line x1={cx} y1={cy} x2={needlePt.x} y2={needlePt.y} stroke="#334155" strokeWidth={2.5} strokeLinecap="round" filter="url(#needle-shadow)" />
        <circle cx={cx} cy={cy} r={4} fill="#334155" />
        <circle cx={cx} cy={cy} r={2} fill="#fff" />
        <text x={cx} y={cy + size * 0.18} textAnchor="middle" fontSize={size * 0.2} fontWeight="800" fill="#1e293b">{value}</text>
      </svg>
      {subs && <div style={{ fontSize: 10, color: '#94a3b8', marginTop: -2 }}>{subs}</div>}
    </div>
  );
};

export default GaugeChart;
