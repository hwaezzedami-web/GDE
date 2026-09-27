import { PieChart, Pie, Cell, Tooltip } from 'recharts';

const DonutChart = ({ data, title, size = 160, innerRadius = 45, outerRadius = 65 }) => (
  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
    {title && <div style={{ fontSize: 12, fontWeight: 600, color: '#444', marginBottom: 8 }}>{title}</div>}
    <PieChart width={size} height={size}>
      <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
        innerRadius={innerRadius} outerRadius={outerRadius} paddingAngle={1} startAngle={90} endAngle={-270}>
        {data.map((d, i) => <Cell key={i} fill={d.color} />)}
      </Pie>
      <Tooltip formatter={(v) => `${v}%`} contentStyle={{ fontSize: 11, borderRadius: 6 }} />
    </PieChart>
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center', marginTop: 4 }}>
      {data.map((d, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: d.color, display: 'inline-block' }} />
          <span style={{ color: '#666' }}>{d.name}</span>
          {d.value && <span style={{ fontWeight: 600, color: '#333' }}>{d.value}%</span>}
        </div>
      ))}
    </div>
  </div>
);

export default DonutChart;
