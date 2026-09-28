import { PieChart, Pie, Cell, Tooltip } from 'recharts';

const DonutChart = ({ data, size = 160, inner = 45, outer = 65, showCenter }) => {
  const total = data.reduce((s, d) => s + (d.value || 0), 0);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div style={{ position: 'relative' }}>
        <PieChart width={size} height={size}>
          <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
            innerRadius={inner} outerRadius={outer} paddingAngle={2} startAngle={90} endAngle={-270}
            stroke="none">
            {data.map((d, i) => <Cell key={i} fill={d.color} />)}
          </Pie>
          <Tooltip formatter={(v) => `${v}%`} contentStyle={{ fontSize: 11, borderRadius: 8, border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
        </PieChart>
        {showCenter && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center' }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#1e293b' }}>{total.toFixed(1)}%</div>
          </div>
        )}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', justifyContent: 'center', marginTop: 4 }}>
        {data.map((d, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, color: '#64748b' }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: d.color, display: 'inline-block', flexShrink: 0 }} />
            <span>{d.name}</span>
            {d.value != null && <b style={{ color: '#334155' }}>{d.value}%</b>}
          </span>
        ))}
      </div>
    </div>
  );
};

export default DonutChart;
