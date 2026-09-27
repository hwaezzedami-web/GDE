import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, RadarChart,
  PolarGrid, PolarAngleAxis, Radar,
} from 'recharts';
import {
  Activity, Radio, Users, TrendingUp, TrendingDown, AlertTriangle,
  Wifi, Globe, Smartphone, BarChart3, Signal, Gauge,
} from 'lucide-react';
import {
  networkOverview, kpiData, kqiData, trafficTrend, regionPerformance,
  userBehavior, alarms,
} from './data/networkData';
import './App.css';

const COLORS = ['#4c8bf5', '#34d399', '#a78bfa', '#22d3ee', '#fbbf24', '#f87171'];

const formatNum = (n) => {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toString();
};

const KpiCard = ({ label, value, unit, trend, trendDir, color }) => (
  <div className="card kpi-card">
    <span className="label">{label}</span>
    <span className="value" style={{ color }}>
      {value}<span className="unit">{unit}</span>
    </span>
    {trend && (
      <span className={`trend ${trendDir}`}>
        {trendDir === 'up' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
        {trend}
      </span>
    )}
  </div>
);

const chartTooltipStyle = {
  backgroundColor: '#1e2235',
  border: '1px solid #2a2e45',
  borderRadius: '8px',
  color: '#e8eaed',
  fontSize: '12px',
};

const kqiRadarData = [
  { metric: 'Video MOS', value: kqiData.videoStreamingMOS * 20, fullMark: 100 },
  { metric: 'Voice MOS', value: kqiData.voiceMOS * 20, fullMark: 100 },
  { metric: 'Web Score', value: kqiData.webBrowsingScore, fullMark: 100 },
  { metric: 'App Speed', value: kqiData.appDownloadSpeed, fullMark: 100 },
  { metric: 'Video Call', value: kqiData.videoCallQuality * 20, fullMark: 100 },
  { metric: 'CSAT', value: kqiData.overallCSAT, fullMark: 100 },
];

function App() {
  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Network Operations Dashboard</h1>
        <span className="timestamp">Live | {new Date().toLocaleString()}</span>
      </header>

      {/* Top KPI Cards */}
      <div className="grid grid-4">
        <KpiCard label="Network Availability" value={kpiData.availability} unit="%" trend="+0.02%" trendDir="up" color="var(--accent-green)" />
        <KpiCard label="Avg DL Throughput" value={kpiData.avgThroughputDL} unit=" Mbps" trend="+3.2%" trendDir="up" color="var(--accent-blue)" />
        <KpiCard label="Active Subscribers" value={formatNum(networkOverview.activeSubscribers)} unit="" trend="+1.8%" trendDir="up" color="var(--accent-cyan)" />
        <KpiCard label="Call Drop Rate" value={kpiData.callDropRate} unit="%" trend="-0.05%" trendDir="up" color="var(--accent-green)" />
      </div>

      {/* Network Overview + Alarms */}
      <div className="grid grid-2">
        <div className="card">
          <h3 className="section-title"><Radio size={18} /> Network Overview</h3>
          <div className="overview-stats">
            <div className="stat-item">
              <div className="stat-value" style={{ color: 'var(--accent-blue)' }}>{formatNum(networkOverview.totalSites)}</div>
              <div className="stat-label">Total Sites</div>
            </div>
            <div className="stat-item">
              <div className="stat-value" style={{ color: 'var(--accent-green)' }}>{formatNum(networkOverview.activeSites)}</div>
              <div className="stat-label">Active Sites</div>
            </div>
            <div className="stat-item">
              <div className="stat-value" style={{ color: 'var(--accent-red)' }}>{networkOverview.sitesDown}</div>
              <div className="stat-label">Sites Down</div>
            </div>
          </div>
          {networkOverview.technologies.map((tech, i) => (
            <div className="tech-bar" key={tech.name}>
              <span className="tech-name">{tech.name}</span>
              <div className="bar-container">
                <div className="bar-fill" style={{ width: `${tech.coverage}%`, background: COLORS[i] }} />
              </div>
              <span className="tech-value">{tech.coverage}%</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 className="section-title"><AlertTriangle size={18} /> Active Alarms</h3>
          <div className="alarm-list">
            {alarms.map(a => (
              <div className={`alarm-item ${a.severity}`} key={a.id}>
                <div className={`severity-dot ${a.severity}`} />
                <span className="alarm-site">{a.site}</span>
                <span className="alarm-msg">{a.message}</span>
                <span className="alarm-time">{a.time}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Traffic Trend */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 className="section-title"><Activity size={18} /> Traffic Trend (24h)</h3>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={trafficTrend}>
            <defs>
              <linearGradient id="gradBlue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4c8bf5" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#4c8bf5" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradGreen" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2e45" />
            <XAxis dataKey="hour" stroke="#9aa0b4" fontSize={11} tickLine={false} />
            <YAxis yAxisId="left" stroke="#9aa0b4" fontSize={11} tickLine={false} />
            <YAxis yAxisId="right" orientation="right" stroke="#9aa0b4" fontSize={11} tickLine={false} />
            <Tooltip contentStyle={chartTooltipStyle} />
            <Area yAxisId="left" type="monotone" dataKey="dataTrafficTB" stroke="#4c8bf5" fill="url(#gradBlue)" name="Data (TB)" />
            <Area yAxisId="right" type="monotone" dataKey="voiceTrafficErl" stroke="#34d399" fill="url(#gradGreen)" name="Voice (Erl)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Network KPIs */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 className="section-title"><Gauge size={18} /> Network KPIs</h3>
        <div className="kpi-grid">
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-green)' }}>{kpiData.callSetupSuccessRate}%</div>
            <div className="kpi-lbl">Call Setup Success</div>
          </div>
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-green)' }}>{kpiData.handoverSuccessRate}%</div>
            <div className="kpi-lbl">Handover Success</div>
          </div>
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-blue)' }}>{kpiData.rrcConnectionSuccessRate}%</div>
            <div className="kpi-lbl">RRC Connection Success</div>
          </div>
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-blue)' }}>{kpiData.erabSetupSuccessRate}%</div>
            <div className="kpi-lbl">E-RAB Setup Success</div>
          </div>
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-cyan)' }}>{kpiData.latency} ms</div>
            <div className="kpi-lbl">Avg Latency</div>
          </div>
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-green)' }}>{kpiData.volteDropRate}%</div>
            <div className="kpi-lbl">VoLTE Drop Rate</div>
          </div>
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-purple)' }}>{kpiData.prbUtilizationDL}%</div>
            <div className="kpi-lbl">PRB Util (DL)</div>
          </div>
          <div className="kpi-mini">
            <div className="kpi-val" style={{ color: 'var(--accent-purple)' }}>{kpiData.prbUtilizationUL}%</div>
            <div className="kpi-lbl">PRB Util (UL)</div>
          </div>
        </div>
      </div>

      {/* KQIs + Region Performance */}
      <div className="grid grid-2">
        <div className="card">
          <h3 className="section-title"><Signal size={18} /> Key Quality Indicators (KQI)</h3>
          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <div className="kpi-mini" style={{ flex: 1 }}>
              <div className="kpi-val" style={{ color: 'var(--accent-green)' }}>{kqiData.overallCSAT}%</div>
              <div className="kpi-lbl">Overall CSAT</div>
            </div>
            <div className="kpi-mini" style={{ flex: 1 }}>
              <div className="kpi-val" style={{ color: 'var(--accent-blue)' }}>{kqiData.nps}</div>
              <div className="kpi-lbl">NPS Score</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <RadarChart data={kqiRadarData}>
              <PolarGrid stroke="#2a2e45" />
              <PolarAngleAxis dataKey="metric" tick={{ fill: '#9aa0b4', fontSize: 11 }} />
              <Radar dataKey="value" stroke="#4c8bf5" fill="#4c8bf5" fillOpacity={0.2} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3 className="section-title"><Globe size={18} /> Regional Performance</h3>
          <table className="region-table">
            <thead>
              <tr>
                <th>Region</th>
                <th>Availability</th>
                <th>Throughput</th>
                <th>Subscribers</th>
                <th>Satisfaction</th>
              </tr>
            </thead>
            <tbody>
              {regionPerformance.map(r => (
                <tr key={r.region}>
                  <td style={{ fontWeight: 600 }}>{r.region}</td>
                  <td><span className={`status-badge ${r.availability >= 99.9 ? 'good' : 'warning'}`}>{r.availability}%</span></td>
                  <td>{r.throughput} Mbps</td>
                  <td>{formatNum(r.subscribers)}</td>
                  <td>{r.satisfaction}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* User Behavior */}
      <div className="grid grid-3">
        <div className="card">
          <h3 className="section-title"><Smartphone size={18} /> App Data Usage</h3>
          {userBehavior.appUsage.map((app, i) => (
            <div className="app-usage-item" key={app.app}>
              <span className="app-name">{app.app}</span>
              <div className="app-bar-bg">
                <div className="app-bar-fill" style={{ width: `${app.percentage}%`, background: COLORS[i] }} />
              </div>
              <span className="app-pct">{app.percentage}%</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 className="section-title"><Wifi size={18} /> Device Distribution</h3>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={userBehavior.deviceDistribution} dataKey="percentage" nameKey="type" cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={3}>
                {userBehavior.deviceDistribution.map((_, i) => <Cell key={i} fill={COLORS[i]} />)}
              </Pie>
              <Tooltip contentStyle={chartTooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
          <div className="device-list">
            {userBehavior.deviceDistribution.map((d, i) => (
              <div className="device-item" key={d.type}>
                <div className="device-pct" style={{ color: COLORS[i] }}>{d.percentage}%</div>
                <div className="device-type">{d.type}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h3 className="section-title"><Users size={18} /> Daily Active Users</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={userBehavior.dailyActiveUsers}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e45" />
              <XAxis dataKey="day" stroke="#9aa0b4" fontSize={11} tickLine={false} />
              <YAxis stroke="#9aa0b4" fontSize={11} tickLine={false} tickFormatter={formatNum} />
              <Tooltip contentStyle={chartTooltipStyle} formatter={(v) => formatNum(v)} />
              <Bar dataKey="users" fill="#4c8bf5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: 12 }}>
            <div className="stat-item" style={{ flex: 1, marginRight: 8 }}>
              <div className="stat-value" style={{ fontSize: 18, color: 'var(--accent-cyan)' }}>{userBehavior.avgDataPerUser} GB</div>
              <div className="stat-label">Avg Data/User</div>
            </div>
            <div className="stat-item" style={{ flex: 1 }}>
              <div className="stat-value" style={{ fontSize: 18, color: 'var(--accent-purple)' }}>{userBehavior.avgSessionDuration} min</div>
              <div className="stat-label">Avg Session</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
