import { useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, PieChart, Pie, Cell,
} from 'recharts';
import GaugeChart from './components/GaugeChart';
import DonutChart from './components/DonutChart';
import DataUploader from './components/DataUploader';
import { useData } from './context/DataContext';
import './App.css';

const fmt = (n) => {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toString();
};

const tt = { fontSize: 11, borderRadius: 6 };
const COLORS = ['#4caf50', '#7b1fa2', '#1e88e5', '#fb8c00', '#e53935', '#00897b', '#999'];

function App() {
  const { data } = useData();
  const { reportMeta, subscriberOverview, dataTraffic, voiceKPI, volteKPI,
    smsKPI, dataQuality, topApps, gaming, devices, fiveG, roaming, geographic } = data;
  const [showUploader, setShowUploader] = useState(false);

  return (
    <div className="report">
      {showUploader && <DataUploader onClose={() => setShowUploader(false)} />}

      {/* HEADER */}
      <header className="report-header">
        <div className="header-left">
          <div className="header-logo">Mobilis</div>
          <div className="header-divider" />
          <div>
            <div className="header-title">Daily Service Quality Report</div>
            <div className="header-subtitle">{reportMeta.date}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn-upload" onClick={() => setShowUploader(true)}>Import CSV Data</button>
          <button className="btn-upload" onClick={() => window.print()}>Export PDF</button>
          <div className="header-right">{reportMeta.department}</div>
        </div>
      </header>

      {/* TOP STATS BAR */}
      <div className="stats-bar">
        <div className="stat-card">
          <div className="stat-value">{fmt(subscriberOverview.totalActive)}</div>
          <div className="stat-label">Total Subscribers</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{fmt(subscriberOverview.voiceSubscribers)}</div>
          <div className="stat-unit">CS Attach</div>
          <div className="stat-label">Voice Subscribers</div>
        </div>
        <div className="stat-card">
          <div className="stat-value blue">{fmt(subscriberOverview.dataSubscribers)}</div>
          <div className="stat-unit">PS Attach</div>
          <div className="stat-label">Data Subscribers</div>
        </div>
        <div className="stat-card">
          <div className="stat-value purple">{fmt(subscriberOverview.volteSubscribers)}</div>
          <div className="stat-label">VoLTE Subscribers</div>
        </div>
        <div className="stat-card">
          <div className="stat-value orange">{subscriberOverview.csActive ? fmt(subscriberOverview.csActive) : fmt(dataTraffic.totalTB)}</div>
          <div className="stat-label">{subscriberOverview.csActive ? 'CS Active' : 'Total Traffic TB'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{subscriberOverview.psActive ? fmt(subscriberOverview.psActive) : fmt(voiceKPI.totalVoiceHours)}</div>
          <div className="stat-label">{subscriberOverview.psActive ? 'PS Active' : 'Voice Hours'}</div>
        </div>
      </div>

      {/* 1. SUBSCRIBER OVERVIEW */}
      <div className="section">
        <div className="section-title">1. Subscriber Overview</div>
        <div className="section-grid cols-3">
          <div className="card">
            <div className="card-title">PS Subscribers by RAT</div>
            <DonutChart data={subscriberOverview.byRAT.map(r => ({ name: r.rat, value: r.pct, color: { '2G': '#999', '3G': '#f9a825', '4G': '#4caf50', '5G': '#7b1fa2' }[r.rat] || '#999' }))} />
            <table className="data-table" style={{ marginTop: 8 }}>
              <thead><tr><th>RAT</th><th className="num">Count</th><th className="num">%</th></tr></thead>
              <tbody>
                {subscriberOverview.byRAT.map(r => (
                  <tr key={r.rat}><td>{r.rat}</td><td className="num">{fmt(r.count)}</td><td className="num">{r.pct}%</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card">
            <div className="card-title">Service Distribution</div>
            <DonutChart data={subscriberOverview.serviceDistribution.map((s, i) => ({ name: s.type, value: s.pct, color: COLORS[i] }))} />
            <table className="data-table" style={{ marginTop: 8 }}>
              <thead><tr><th>Type</th><th className="num">Count</th><th className="num">%</th></tr></thead>
              <tbody>
                {subscriberOverview.serviceDistribution.map(s => (
                  <tr key={s.type}><td>{s.type}</td><td className="num">{fmt(s.count)}</td><td className="num">{s.pct}%</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card">
            <div className="card-title">Subscribers Trend (Daily)</div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={subscriberOverview.newSubscribersTrend} barSize={16}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey={subscriberOverview.newSubscribersTrend?.[0]?.day ? 'day' : 'month'} fontSize={9} tickLine={false} />
                <YAxis fontSize={9} tickLine={false} tickFormatter={v => fmt(v)} domain={['dataMin - 100000', 'dataMax + 100000']} />
                <Tooltip contentStyle={tt} formatter={v => v.toLocaleString()} />
                {subscriberOverview.newSubscribersTrend?.[0]?.totalActive != null ? (
                  <Bar dataKey="totalActive" fill="#4caf50" radius={[4,4,0,0]} name="Total Subs" />
                ) : (
                  <Bar dataKey="value" fill="#4caf50" radius={[4,4,0,0]} name="New Subs" />
                )}
              </BarChart>
            </ResponsiveContainer>
            {subscriberOverview.roaming && (subscriberOverview.roaming.inbound > 0 || subscriberOverview.roaming.outbound > 0) && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginTop: 8 }}>
                <div className="mini-stat">
                  <div className="ms-val" style={{ color: '#1e88e5' }}>{fmt(subscriberOverview.roaming.inbound)}</div>
                  <div className="ms-lbl">Roaming Inbound</div>
                </div>
                <div className="mini-stat">
                  <div className="ms-val" style={{ color: '#7b1fa2' }}>{fmt(subscriberOverview.roaming.outbound)}</div>
                  <div className="ms-lbl">Roaming Outbound</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 2. DATA TRAFFIC */}
      <div className="section">
        <div className="section-title">2. Data Traffic</div>
        <div className="section-grid cols-2-1">
          <div className="card">
            <div className="card-title">Traffic by RAT</div>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <div style={{ flex: 1 }}>
                <DonutChart data={dataTraffic.byRAT.map(r => ({ name: r.rat, value: r.pct, color: r.color }))} size={140} inner={35} outer={55} />
              </div>
              <div style={{ flex: 1 }}>
                {dataTraffic.byRAT.map(r => (
                  <div className="bar-row" key={r.rat}>
                    <span className="bar-label">{r.rat}</span>
                    <div className="bar-track"><div className="bar-fill" style={{ width: `${r.pct}%`, background: r.color }} /></div>
                    <span className="bar-value">{r.tb} TB</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="card">
            <div className="card-title">DOU & Growth</div>
            <div style={{ textAlign: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 36, fontWeight: 800, color: '#2e7d32' }}>{dataTraffic.dou}</div>
              <div style={{ fontSize: 10, color: '#777' }}>GB / USER / DAY</div>
            </div>
            <ResponsiveContainer width="100%" height={100}>
              <AreaChart data={dataTraffic.growthTrend}>
                <Area type="monotone" dataKey="daily" stroke="#4caf50" fill="#e8f5e9" />
                <XAxis dataKey="month" fontSize={9} tickLine={false} />
                <Tooltip contentStyle={tt} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="section-grid cols-2" style={{ marginTop: 12 }}>
          <div className="card">
            <div className="card-title">Traffic by Wilaya (Top 10)</div>
            <table className="data-table">
              <thead><tr><th>Wilaya</th><th className="num">Traffic (TB)</th><th className="num">Users</th></tr></thead>
              <tbody>
                {dataTraffic.byWilaya.map(w => (
                  <tr key={w.wilaya}><td>{w.wilaya}</td><td className="num">{w.traffic.toLocaleString()}</td><td className="num">{fmt(w.users)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card">
            <div className="card-title">Traffic by RAT by Wilaya (Top 5)</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={dataTraffic.byRATbyWilaya} barSize={10}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="wilaya" fontSize={9} tickLine={false} />
                <YAxis fontSize={9} tickLine={false} />
                <Tooltip contentStyle={tt} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Bar dataKey="2G" fill="#999" stackId="a" />
                <Bar dataKey="3G" fill="#f9a825" stackId="a" />
                <Bar dataKey="4G" fill="#4caf50" stackId="a" />
                <Bar dataKey="5G" fill="#7b1fa2" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="section-grid cols-1" style={{ marginTop: 12 }}>
          <div className="card">
            <div className="card-title">Traffic by APN</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {dataTraffic.byAPN.map((a, i) => (
                <div key={a.apn} className="mini-stat" style={{ flex: '1 1 120px' }}>
                  <div className="ms-val" style={{ color: COLORS[i % COLORS.length], fontSize: 16 }}>{a.pct}%</div>
                  <div className="ms-lbl">{a.apn} ({a.traffic} TB)</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 3. VOICE KPI */}
      <div className="section">
        <div className="section-title">3. Voice KPI (CS)</div>
        <div className="gauge-row">
          <div className="gauge-card">
            <div className="g-label">Call Setup SR %</div>
            <GaugeChart value={voiceKPI.callSetupSR.total} size={110} />
            <div className="g-sub">MO <b>{voiceKPI.callSetupSR.mo}</b> &nbsp; MT <b>{voiceKPI.callSetupSR.mt}</b></div>
          </div>
          <div className="gauge-card">
            <div className="g-label">Drop Rate 2G %</div>
            <GaugeChart value={voiceKPI.callDropRate['2G']} max={5} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">Drop Rate 3G %</div>
            <GaugeChart value={voiceKPI.callDropRate['3G']} max={5} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">Setup Duration 2G (s)</div>
            <GaugeChart value={voiceKPI.callSetupDuration['2G']} max={15} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">Setup Duration 3G (s)</div>
            <GaugeChart value={voiceKPI.callSetupDuration['3G']} max={15} size={110} />
          </div>
        </div>
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-title">Voice Traffic Daily Trend</div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={voiceKPI.voiceTrend} barSize={24}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="day" fontSize={10} tickLine={false} />
              <YAxis fontSize={10} tickLine={false} tickFormatter={v => `${(v/1e6).toFixed(1)}M`} />
              <Tooltip contentStyle={tt} formatter={v => fmt(v)} />
              <Bar dataKey="hours" fill="#4caf50" radius={[4,4,0,0]} name="Hours" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 4. VoLTE KPI */}
      <div className="section">
        <div className="section-title">4. VoLTE KPI</div>
        <div className="gauge-row">
          <div className="gauge-card">
            <div className="g-label">VoLTE Users</div>
            <div className="g-value" style={{ color: '#7b1fa2' }}>{fmt(volteKPI.volteUsers)}</div>
          </div>
          <div className="gauge-card">
            <div className="g-label">CSFB SR MO %</div>
            <GaugeChart value={volteKPI.csfbSR.mo} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">CSFB SR MT %</div>
            <GaugeChart value={volteKPI.csfbSR.mt} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">CSFB Fallback Rate %</div>
            <GaugeChart value={volteKPI.csfbFallbackRate} max={20} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">SRVCC SR %</div>
            <GaugeChart value={volteKPI.srvccSR} size={110} />
          </div>
        </div>
      </div>

      {/* 5. SMS */}
      <div className="section">
        <div className="section-title">5. SMS</div>
        <div className="gauge-row">
          <div className="gauge-card">
            <div className="g-label">SMS MO SR %</div>
            <GaugeChart value={smsKPI.moSR} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">SMS MT SR %</div>
            <GaugeChart value={smsKPI.mtSR} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">Total MO</div>
            <div className="g-value" style={{ color: '#1e88e5' }}>{fmt(smsKPI.totalMO)}</div>
          </div>
          <div className="gauge-card">
            <div className="g-label">Total MT</div>
            <div className="g-value" style={{ color: '#4caf50' }}>{fmt(smsKPI.totalMT)}</div>
          </div>
        </div>
      </div>

      {/* 6. DATA QUALITY */}
      <div className="section">
        <div className="section-title">6. Data Quality / User Experience</div>
        <div className="gauge-row">
          <div className="gauge-card">
            <div className="g-label">Latency (ms)</div>
            <GaugeChart value={dataQuality.latency.internal + dataQuality.latency.external} max={500} size={110} />
            <div className="g-sub">Int <b style={{ color: '#2e7d32' }}>{dataQuality.latency.internal}</b> &nbsp; Ext <b style={{ color: '#2e7d32' }}>{dataQuality.latency.external}</b></div>
          </div>
          <div className="gauge-card">
            <div className="g-label">Packet Loss %</div>
            <GaugeChart value={dataQuality.packetLoss.dl} max={5} size={110} />
            <div className="g-sub">DL <b>{dataQuality.packetLoss.dl}</b> &nbsp; UL <b>{dataQuality.packetLoss.ul}</b></div>
          </div>
          <div className="gauge-card">
            <div className="g-label">TCP Setup SR %</div>
            <GaugeChart value={dataQuality.tcpSetupSR} size={110} />
          </div>
          <div className="gauge-card">
            <div className="g-label">DNS SR %</div>
            <GaugeChart value={dataQuality.dnsSR} size={110} />
            <div className="g-sub">Delay: <b>{dataQuality.dnsDelay}ms</b></div>
          </div>
        </div>
        <div className="section-grid cols-4" style={{ marginTop: 12 }}>
          <div className="mini-stat"><div className="ms-val" style={{ color: '#2e7d32' }}>{dataQuality.avgThroughput.dl}</div><div className="ms-lbl">Avg DL Throughput (Mbps)</div></div>
          <div className="mini-stat"><div className="ms-val" style={{ color: '#1e88e5' }}>{dataQuality.avgThroughput.ul}</div><div className="ms-lbl">Avg UL Throughput (Mbps)</div></div>
          <div className="mini-stat"><div className="ms-val" style={{ color: '#7b1fa2' }}>{dataQuality.tcpRetransmission.dl}%</div><div className="ms-lbl">TCP Retrans DL</div></div>
          <div className="mini-stat"><div className="ms-val" style={{ color: '#fb8c00' }}>{dataQuality.tcpRetransmission.ul}%</div><div className="ms-lbl">TCP Retrans UL</div></div>
        </div>
      </div>

      {/* 8. TOP APPLICATIONS */}
      <div className="section">
        <div className="section-title">8. Top Applications</div>
        <div className="section-grid cols-3">
          <div className="card">
            <div className="card-title">Top Apps by Traffic</div>
            {topApps.byTraffic.map((a, i) => (
              <div className="bar-row" key={a.app}>
                <span className="bar-label">{a.app}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${a.pct}%`, background: COLORS[i % COLORS.length] }} /></div>
                <span className="bar-value">{a.pct}%</span>
              </div>
            ))}
          </div>
          <div className="card">
            <div className="card-title">Top Apps by Users</div>
            {topApps.byUsers.map((a, i) => (
              <div className="bar-row" key={a.app}>
                <span className="bar-label">{a.app}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${(a.users / 14200000) * 100}%`, background: COLORS[i % COLORS.length] }} /></div>
                <span className="bar-value">{fmt(a.users)}</span>
              </div>
            ))}
          </div>
          <div className="card">
            <div className="card-title">App Category Distribution</div>
            <DonutChart data={topApps.categoryDistribution.map(c => ({ name: c.category, value: c.pct, color: c.color }))} size={140} inner={35} outer={55} />
          </div>
        </div>
      </div>

      {/* 9. GAMING */}
      <div className="section">
        <div className="section-title">9. Gaming</div>
        <div className="section-grid cols-2">
          <div className="card">
            <div style={{ display: 'flex', gap: 16 }}>
              <div className="mini-stat" style={{ flex: 1 }}>
                <div className="ms-val" style={{ color: '#fb8c00', fontSize: 22 }}>{fmt(gaming.users)}</div>
                <div className="ms-lbl">Gaming Users</div>
              </div>
              <div className="mini-stat" style={{ flex: 1 }}>
                <div className="ms-val" style={{ color: '#7b1fa2', fontSize: 22 }}>{gaming.trafficTB}</div>
                <div className="ms-lbl">Traffic (TB)</div>
              </div>
            </div>
          </div>
          <div className="card">
            <div className="card-title">Top Games by Users</div>
            {gaming.topGames.map((g, i) => (
              <div className="bar-row" key={g.game}>
                <span className="bar-label" style={{ width: 110 }}>{g.game}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${(g.users / 1200000) * 100}%`, background: COLORS[i] }} /></div>
                <span className="bar-value">{fmt(g.users)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 10. DEVICES */}
      <div className="section">
        <div className="section-title">10. Device / Terminal</div>
        <div className="section-grid cols-3">
          <div className="card">
            <div className="card-title">Top Brands (Market Share)</div>
            {devices.topBrands.map((b, i) => (
              <div className="bar-row" key={b.brand}>
                <span className="bar-label">{b.brand}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${b.share}%`, background: COLORS[i % COLORS.length] }} /></div>
                <span className="bar-value">{b.share}%</span>
              </div>
            ))}
          </div>
          <div className="card">
            <div className="card-title">Device Capability</div>
            <DonutChart data={devices.capability.map((c, i) => ({ name: c.type, value: c.pct, color: COLORS[i] }))} size={140} inner={35} outer={55} />
          </div>
          <div className="card">
            <div className="card-title">OS Distribution</div>
            <DonutChart data={devices.osDistribution.map(o => ({ name: o.os, value: o.pct, color: o.color }))} size={140} inner={35} outer={55} />
            <div className="card-title" style={{ marginTop: 12 }}>Top Models</div>
            <table className="data-table">
              <tbody>
                {devices.topModels.map(m => (
                  <tr key={m.model}><td>{m.model}</td><td className="num">{fmt(m.count)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 11. 5G ANALYTICS */}
      <div className="section">
        <div className="section-title">11. 5G Analytics</div>
        <div className="section-grid cols-2-1">
          <div className="card">
            <div className="card-title">5G by Wilaya</div>
            <table className="data-table">
              <thead><tr><th>Wilaya</th><th className="num">Users</th><th className="num">Terminals</th><th className="num">Traffic (TB)</th><th className="num">DOU (GB)</th></tr></thead>
              <tbody>
                {fiveG.usersByWilaya.map(w => (
                  <tr key={w.wilaya}>
                    <td>{w.wilaya}</td><td className="num">{fmt(w.users)}</td><td className="num">{fmt(w.terminals)}</td><td className="num">{w.traffic}</td><td className="num">{w.dou}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card">
            <div className="card-title">5G Camping & Penetration</div>
            <div className="mini-stats">
              <div className="mini-stat"><div className="ms-val" style={{ color: '#7b1fa2' }}>{fiveG.campingRatio.user}%</div><div className="ms-lbl">User Camping</div></div>
              <div className="mini-stat"><div className="ms-val" style={{ color: '#4caf50' }}>{fiveG.campingRatio.traffic}%</div><div className="ms-lbl">Traffic Camping</div></div>
              <div className="mini-stat"><div className="ms-val" style={{ color: '#1e88e5' }}>{fiveG.dou}</div><div className="ms-lbl">5G DOU (GB)</div></div>
            </div>
            <div className="card-title" style={{ marginTop: 12 }}>By Band</div>
            {fiveG.penetrationByBand.map((b, i) => (
              <div className="bar-row" key={b.band}>
                <span className="bar-label" style={{ width: 100 }}>{b.band}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${b.pct}%`, background: COLORS[i] }} /></div>
                <span className="bar-value">{b.pct}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 12. ROAMING */}
      <div className="section">
        <div className="section-title">12. Roaming</div>
        <div className="section-grid cols-2">
          <div className="card">
            <div className="card-title">Inbound Roaming</div>
            <table className="data-table">
              <thead><tr><th>Country</th><th>Operator</th><th className="num">Users</th><th className="num">Traffic (TB)</th></tr></thead>
              <tbody>
                {roaming.inbound.map(r => (
                  <tr key={r.country}><td>{r.country}</td><td>{r.operator}</td><td className="num">{fmt(r.users)}</td><td className="num">{r.traffic}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card">
            <div className="card-title">Outbound Roaming</div>
            <table className="data-table">
              <thead><tr><th>Country</th><th>Operator</th><th className="num">Users</th><th className="num">Traffic (TB)</th></tr></thead>
              <tbody>
                {roaming.outbound.map(r => (
                  <tr key={r.country}><td>{r.country}</td><td>{r.operator}</td><td className="num">{fmt(r.users)}</td><td className="num">{r.traffic}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 16. GEOGRAPHIC ANALYSIS */}
      <div className="section">
        <div className="section-title">16. Geographic Analysis</div>
        <div className="section-grid cols-2">
          <div className="card">
            <div className="card-title">Urban vs Rural</div>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 24 }}>
              <div className="mini-stat" style={{ minWidth: 100 }}>
                <div className="ms-val" style={{ color: '#2e7d32', fontSize: 28 }}>{geographic.urbanVsRural.urban}%</div>
                <div className="ms-lbl">Urban</div>
              </div>
              <div className="mini-stat" style={{ minWidth: 100 }}>
                <div className="ms-val" style={{ color: '#fb8c00', fontSize: 28 }}>{geographic.urbanVsRural.rural}%</div>
                <div className="ms-lbl">Rural</div>
              </div>
            </div>
          </div>
          <div className="card">
            <div className="card-title">4G Coverage Gap (High Device Penetration, Low Usage)</div>
            <table className="data-table">
              <thead><tr><th>Wilaya</th><th className="num">4G Device %</th><th className="num">4G Usage %</th><th className="num">Gap</th></tr></thead>
              <tbody>
                {geographic.coverageGap.map(g => (
                  <tr key={g.wilaya}>
                    <td>{g.wilaya}</td>
                    <td className="num">{g.devicePenetration4G}%</td>
                    <td className="num">{g.usage4G}%</td>
                    <td className="num"><span className="badge warn">{g.gap}%</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ textAlign: 'center', padding: '20px 0', color: '#999', fontSize: 11, borderTop: '1px solid #e0e0e0', marginTop: 12 }}>
        ATM Mobilis - Daily Service Quality Report - {reportMeta.date} - Confidential
      </div>
    </div>
  );
}

export default App;
