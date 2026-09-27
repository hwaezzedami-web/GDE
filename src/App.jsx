import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import GaugeChart from './components/GaugeChart';
import DonutChart from './components/DonutChart';
import {
  lastDayIndicators, competitors, dataTrafficDistribution, dataTrafficLast7Days,
  voiceTrafficDistribution, subscribersMaxRAT, subscriberEvolution,
  voiceKPI, voiceTrafficTrend, dataKPI, trafficVolumeTrend,
} from './data/networkData';
import './App.css';

const fmt = (n) => (n >= 1 ? `${n.toFixed(2)}M` : `${(n * 1000).toFixed(0)}K`);

const SidebarStat = ({ value, unit, label, icon, color = '#e4002b' }) => (
  <div className="sidebar-stat">
    <div className="sidebar-stat-value" style={{ color }}>{value}<span className="sidebar-stat-unit">{unit}</span></div>
    <div className="sidebar-stat-icon">{icon}</div>
    <div className="sidebar-stat-label">{label}</div>
  </div>
);

function App() {
  const d = lastDayIndicators;
  return (
    <div className="report-layout">
      {/* Left Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-logo">ooredoo</div>
        </div>
        <div className="sidebar-date-box">
          <div className="sidebar-date-label">Last day indicators</div>
          <div className="sidebar-date">{d.date}</div>
        </div>
        <SidebarStat value={d.totalActiveSubscribers} unit="M" label="Total Active Subscribers" icon="👥" />
        <SidebarStat value={d.dataSubscribers} unit="M" label="Data Subscribers" icon="📊" />
        <SidebarStat value={d.voiceSubscribers} unit="M" label="Voice Subscribers" icon="📞" />
        <SidebarStat value={d.totalTrafficTB} unit="" label="Total Traffic TB" color="#333" icon="📈" />
        <SidebarStat value={d.totalVoiceMillionH} unit="M" label="Total Voice Million (H)" color="#333" icon="🔊" />

        <div className="sidebar-cei">
          <div className="cei-label">Customer<br />Experience Index</div>
          <div className="cei-value">{d.customerExperienceIndex}</div>
          <div className="cei-bar">
            <div className="cei-fill" style={{ width: `${d.customerExperienceIndex}%` }} />
          </div>
        </div>

        <div className="sidebar-map">
          <svg viewBox="0 0 100 120" width="100%" style={{ maxWidth: 140 }}>
            <ellipse cx="50" cy="55" rx="35" ry="50" fill="#f9e4b7" stroke="#e4002b" strokeWidth="1" />
            <circle cx="45" cy="35" r="3" fill="#e4002b" opacity="0.6" />
            <circle cx="55" cy="45" r="2.5" fill="#e4002b" opacity="0.5" />
            <circle cx="40" cy="55" r="2" fill="#e4002b" opacity="0.4" />
            <circle cx="55" cy="60" r="3.5" fill="#e4002b" opacity="0.7" />
            <circle cx="48" cy="75" r="2" fill="#e4002b" opacity="0.3" />
          </svg>
        </div>

        <div className="sidebar-competitors">
          <div className="competitor-title">EnodeBs Number</div>
          <div className="competitor-subtitle">(source Ookla)<br />Last update 29/03/2026</div>
          {competitors.map(c => (
            <div className="competitor-item" key={c.name}>
              <div className="competitor-logo" style={{ color: c.color }}>{c.name}</div>
              <div className="competitor-count" style={{ color: c.color }}>{c.enodeBs.toLocaleString()}</div>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="report-header">
          <div className="header-badge">Daily Service Quality Report</div>
          <div className="header-right">SOC &<br />Network Performance</div>
        </header>

        {/* Distribution Charts */}
        <section className="section-row three-col">
          <div className="card">
            <DonutChart data={dataTrafficDistribution} title="Data Traffic Distribution" />
          </div>
          <div className="card">
            <DonutChart data={dataTrafficLast7Days} title="Data Traffic Distribution Last 7 Days" />
          </div>
          <div className="card">
            <DonutChart data={voiceTrafficDistribution} title="Voice Traffic Distribution" />
          </div>
        </section>

        {/* Subscriber Evolution + RAT Distribution */}
        <section className="section-row two-col-wide">
          <div className="card" style={{ flex: 2 }}>
            <div className="card-title">Subscribers Service Distribution Evolution</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={subscriberEvolution} barSize={8}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="month" fontSize={9} tick={{ fill: '#888' }} tickLine={false} />
                <YAxis fontSize={9} tick={{ fill: '#888' }} tickLine={false} tickFormatter={v => `${(v/1e6).toFixed(0)}M`} />
                <Tooltip contentStyle={{ fontSize: 11 }} formatter={v => `${(v/1e6).toFixed(2)}M`} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Bar dataKey="voiceOnly" name="Voice only" fill="#999" stackId="a" />
                <Bar dataKey="voiceAndData" name="Voice + Data" fill="#f5b0b0" stackId="a" />
                <Bar dataKey="dataOnly" name="Data only" fill="#e0e0e0" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card" style={{ flex: 1 }}>
            <DonutChart data={subscribersMaxRAT} title="Subscribers Max RAT Distribution" size={180} innerRadius={50} outerRadius={72} />
          </div>
        </section>

        {/* Voice KPI */}
        <section className="section-block">
          <h2 className="section-heading">Voice KPI</h2>
          <div className="kpi-gauges-row">
            <div className="kpi-gauge-card">
              <GaugeChart value={voiceKPI.callSetupSR} label="Call Setup SR %" size={130} thresholds={{ good: 95, warn: 90 }} />
              <div className="gauge-subs">
                <span>MO <b>{voiceKPI.mo}</b></span>
                <span>MT <b>{voiceKPI.mt}</b></span>
              </div>
              <div className="gauge-subs small">
                <span>MO CSFB SR % <b>{voiceKPI.moCSFBSR}</b></span>
                <span>MT CSFB SR % <b>{voiceKPI.mtCSFBSR}</b></span>
              </div>
            </div>
            <div className="kpi-gauge-card">
              <GaugeChart value={voiceKPI.dropRate} max={5} label="Drop Rate %" size={130} color="#f9a825" />
              <div className="gauge-subs">
                <span>2G % <b>{voiceKPI.dropRate2G}</b></span>
                <span>3G % <b>{voiceKPI.dropRate3G}</b></span>
              </div>
            </div>
            <div className="kpi-gauge-card">
              <GaugeChart value={voiceKPI.callSetupAvDuration} max={15} label="Call Setup Av Duration (Sec)" size={130} color="#f9a825" />
              <div className="gauge-subs">
                <span>2G (Sec) <b>{voiceKPI.callSetupAvDuration2G}</b></span>
                <span>3G (Sec) <b>{voiceKPI.callSetupAvDuration3G}</b></span>
              </div>
            </div>
            <div className="kpi-gauge-card">
              <GaugeChart value={voiceKPI.smsMTSR} label="SMS MT SR %" size={130} color="#c0ca33" />
            </div>
          </div>
        </section>

        {/* Voice Traffic Trend */}
        <section className="section-block">
          <div className="card">
            <div className="card-title">Total Voice Traffic (hours)</div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={voiceTrafficTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="period" fontSize={9} tick={{ fill: '#888' }} tickLine={false} interval={15} />
                <YAxis fontSize={9} tick={{ fill: '#888' }} tickLine={false} tickFormatter={v => `${(v/1e6).toFixed(0)}M`} />
                <Tooltip contentStyle={{ fontSize: 11 }} formatter={v => v.toLocaleString()} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Area type="monotone" dataKey="legacyVoice" name="Legacy Voice (h)" stroke="#e4002b" fill="#f5b0b0" fillOpacity={0.6} />
                <Area type="monotone" dataKey="ottVoice" name="OTT Voice (h)" stroke="#ccc" fill="#e8e8e8" fillOpacity={0.4} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>

        {/* Data KPI */}
        <section className="section-block">
          <h2 className="section-heading">Data KPI</h2>
          <div className="kpi-gauges-row">
            <div className="kpi-gauge-card">
              <GaugeChart value={dataKPI.internetAccessibility} label="Internet Accessibility(%)" size={130} color="#c75028" />
            </div>
            <div className="kpi-gauge-card">
              <GaugeChart value={dataKPI.latency} max={500} label="Latency (ms)" size={130} color="#7bad5e" />
              <div className="gauge-subs">
                <span style={{ color: '#2e7d32' }}>Intern <b>{dataKPI.latencyIntern}</b></span>
                <span style={{ color: '#2e7d32' }}>Extern <b>{dataKPI.latencyExtern}</b></span>
              </div>
            </div>
            <div className="kpi-gauge-card">
              <GaugeChart value={dataKPI.packetLoss} max={5} label="Packet Loss (%)" size={130} color="#00857c" />
              <div className="gauge-subs">
                <span style={{ color: '#2e7d32' }}>Downlink <b>{dataKPI.packetLossDL}</b></span>
                <span style={{ color: '#2e7d32' }}>Uplink <b>{dataKPI.packetLossUL}</b></span>
              </div>
            </div>
          </div>
        </section>

        {/* Traffic Volume */}
        <section className="section-block">
          <div className="card">
            <div className="card-title">Traffic Volume (TByte)</div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={trafficVolumeTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="period" fontSize={9} tick={{ fill: '#888' }} tickLine={false} interval={15} />
                <YAxis fontSize={9} tick={{ fill: '#888' }} tickLine={false} tickFormatter={v => `${(v/1000).toFixed(0)}K`} />
                <Tooltip contentStyle={{ fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Area type="monotone" dataKey="3G" stroke="#999" fill="#ddd" fillOpacity={0.4} stackId="1" />
                <Area type="monotone" dataKey="4G" stroke="#e4002b" fill="#f5b0b0" fillOpacity={0.6} stackId="1" />
                <Area type="monotone" dataKey="5G" stroke="#1565c0" fill="#90caf9" fillOpacity={0.5} stackId="1" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
