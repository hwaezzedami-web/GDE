import { PieChart, Pie, Cell, Tooltip } from 'recharts';

const DonutChart = ({ data, size = 150, inner = 40, outer = 60 }) => (
  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
    <PieChart width={size} height={size}>
      <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
        innerRadius={inner} outerRadius={outer} paddingAngle={1} startAngle={90} endAngle={-270}>
        {data.map((d, i) => <Cell key={i} fill={d.color} />)}
      </Pie>
      <Tooltip formatter={(v) => `${v}%`} contentStyle={{ fontSize: 11, borderRadius: 6 }} />
    </PieChart>
    <div className="donut-legend">
      {data.map((d, i) => (
        <span className="donut-legend-item" key={i}>
          <span className="dot" style={{ background: d.color }} />
          {d.name} {d.value != null && <b>{d.value}%</b>}
        </span>
      ))}
    </div>
  </div>
);

export default DonutChart;
