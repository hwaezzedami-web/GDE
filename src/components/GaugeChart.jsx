const GaugeChart = ({ value, max = 100, size = 100 }) => {
  const r = (size - 14) / 2;
  const cx = size / 2;
  const cy = size / 2 + 8;
  const startAngle = -210;
  const endAngle = 30;
  const totalAngle = endAngle - startAngle;
  const pct = Math.min(value / max, 1);
  const valueAngle = startAngle + pct * totalAngle;

  const green = pct >= 0.9;
  const yellow = pct >= 0.7 && pct < 0.9;
  const color = green ? '#2e7d32' : yellow ? '#f9a825' : '#e53935';

  const pt = (a, rad) => ({
    x: cx + rad * Math.cos((a * Math.PI) / 180),
    y: cy + rad * Math.sin((a * Math.PI) / 180),
  });

  const arc = (from, to, rad) => {
    const s = pt(from, rad);
    const e = pt(to, rad);
    return `M ${s.x} ${s.y} A ${rad} ${rad} 0 ${to - from > 180 ? 1 : 0} 1 ${e.x} ${e.y}`;
  };

  return (
    <svg width={size} height={size * 0.65} viewBox={`0 0 ${size} ${size * 0.68}`}>
      <path d={arc(startAngle, endAngle, r)} fill="none" stroke="#e8e8e8" strokeWidth={7} strokeLinecap="round" />
      {pct > 0 && <path d={arc(startAngle, valueAngle, r)} fill="none" stroke={color} strokeWidth={7} strokeLinecap="round" />}
      <text x={cx} y={cy - 2} textAnchor="middle" fontSize={size * 0.22} fontWeight="800" fill="#333">{value}</text>
    </svg>
  );
};

export default GaugeChart;
