const GaugeChart = ({ value, max = 100, label, sublabel, size = 120, color, thresholds }) => {
  const getColor = () => {
    if (color) return color;
    if (!thresholds) return '#00857c';
    if (value >= thresholds.good) return '#2e7d32';
    if (value >= thresholds.warn) return '#f9a825';
    return '#e4002b';
  };

  const gaugeColor = getColor();
  const r = (size - 16) / 2;
  const cx = size / 2;
  const cy = size / 2 + 10;
  const startAngle = -210;
  const endAngle = 30;
  const totalAngle = endAngle - startAngle;
  const valueAngle = startAngle + (value / max) * totalAngle;

  const polarToCart = (angle, radius) => ({
    x: cx + radius * Math.cos((angle * Math.PI) / 180),
    y: cy + radius * Math.sin((angle * Math.PI) / 180),
  });

  const arcPath = (from, to, radius) => {
    const s = polarToCart(from, radius);
    const e = polarToCart(to, radius);
    const large = to - from > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${large} 1 ${e.x} ${e.y}`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      {label && <div style={{ fontSize: 11, color: '#666', marginBottom: 4, fontWeight: 600 }}>{label}</div>}
      <svg width={size} height={size * 0.7} viewBox={`0 0 ${size} ${size * 0.75}`}>
        <path d={arcPath(startAngle, endAngle, r)} fill="none" stroke="#e0e0e0" strokeWidth={8} strokeLinecap="round" />
        <path d={arcPath(startAngle, valueAngle, r)} fill="none" stroke={gaugeColor} strokeWidth={8} strokeLinecap="round" />
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize={size * 0.2} fontWeight="700" fill="#333">{value}</text>
      </svg>
      {sublabel && <div style={{ fontSize: 10, color: '#999', marginTop: -4 }}>{sublabel}</div>}
    </div>
  );
};

export default GaugeChart;
