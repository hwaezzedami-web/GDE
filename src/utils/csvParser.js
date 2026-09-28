export function parseCSV(text) {
  const clean = text.trim().replace(/\r\n/g, '\n');
  const firstLine = clean.split('\n')[0];
  const sep = firstLine.includes('|') ? '|' : firstLine.includes(';') ? ';' : firstLine.includes('\t') ? '\t' : ',';
  const lines = clean.split('\n').map(l => l.split(sep).map(c => c.trim().replace(/^"|"$/g, '')));
  if (lines.length < 2) return [];
  const headers = lines[0];
  return lines.slice(1).filter(r => r.some(c => c !== '') && r.length === headers.length).map(row => {
    const obj = {};
    headers.forEach((h, i) => {
      const v = row[i];
      obj[h] = v === '' ? null : isNaN(v) ? v : Number(v);
    });
    return obj;
  });
}

const SUFFIX_TO_DATE = (suffix) => {
  const base = new Date('2026-09-28');
  const today = 20725;
  const diff = today - suffix;
  const d = new Date(base);
  d.setDate(d.getDate() - diff);
  return d;
};

const fmtDate = (d) => {
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]}`;
};

export function detectAndParse(rows) {
  if (!rows.length) return null;
  const cols = Object.keys(rows[0]);

  if (cols.includes('day_suffix') && cols.includes('total_subs_mobilis')) {
    return parseKpiAllDays(rows);
  }
  return null;
}

function parseKpiAllDays(rows) {
  const sorted = [...rows].sort((a, b) => (a.day_suffix || 0) - (b.day_suffix || 0));
  const latest = sorted[sorted.length - 1];
  const d = latest;

  const totalActive = d.total_subs_mobilis || 0;
  const csAttach = d.cs_attach || 0;
  const csActive = d.cs_active || 0;
  const psAttach = d.ps_attach || 0;
  const psActive = d.ps_active || 0;
  const volte = d.volte_subs || 0;

  const ps2g = d.ps_2g_only || 0;
  const ps3g = d.ps_3g_only || 0;
  const ps4g = d.ps_4g_only || 0;
  const cs2g = d.cs_2g_only || 0;
  const cs3g = d.cs_3g_only || 0;

  const psTotal = ps2g + ps3g + ps4g;

  const result = {
    subscribers_overview: {
      totalActive,
      dataSubscribers: psAttach,
      voiceSubscribers: csAttach,
      volteSubscribers: volte,
      csActive,
      psActive,
      roaming: { inbound: 0, outbound: 0 },
    },
    subscribers_by_rat: [
      { rat: '2G', count: ps2g, pct: psTotal ? Math.round(ps2g / psTotal * 1000) / 10 : 0 },
      { rat: '3G', count: ps3g, pct: psTotal ? Math.round(ps3g / psTotal * 1000) / 10 : 0 },
      { rat: '4G', count: ps4g, pct: psTotal ? Math.round(ps4g / psTotal * 1000) / 10 : 0 },
    ],
    subscribers_service_dist: [
      { type: 'Voice + Data', count: Math.min(csAttach, psAttach), pct: 0 },
      { type: 'Voice Only', count: Math.max(0, csAttach - psAttach), pct: 0 },
      { type: 'Data Only', count: Math.max(0, psAttach - csAttach), pct: 0 },
    ],
    subscribers_trend: sorted.map(r => ({
      day: fmtDate(SUFFIX_TO_DATE(r.day_suffix)),
      suffix: r.day_suffix,
      totalActive: r.total_subs_mobilis || 0,
      psAttach: r.ps_attach || 0,
      csAttach: r.cs_attach || 0,
    })),
  };

  const distTotal = result.subscribers_service_dist.reduce((s, x) => s + x.count, 0);
  result.subscribers_service_dist.forEach(s => {
    s.pct = distTotal ? Math.round(s.count / distTotal * 1000) / 10 : 0;
  });

  return result;
}

export function csvToSectionData(sectionKey, rows) {
  const parsers = {
    subscribers_overview: (rows) => {
      const r = rows[0] || {};
      return {
        totalActive: r.total_active || 0,
        dataSubscribers: r.data_subscribers || 0,
        voiceSubscribers: r.voice_subscribers || 0,
        volteSubscribers: r.volte_subscribers || 0,
        roaming: { inbound: r.roaming_inbound || 0, outbound: r.roaming_outbound || 0 },
      };
    },
    subscribers_by_rat: (rows) => rows.map(r => ({
      rat: r.rat, count: r.count || 0, pct: r.pct || 0,
    })),
    subscribers_service_dist: (rows) => rows.map(r => ({
      type: r.type, count: r.count || 0, pct: r.pct || 0,
    })),
    subscribers_trend: (rows) => rows.map(r => ({
      month: r.month, value: r.new_subscribers || 0,
    })),
    data_traffic_overview: (rows) => {
      const r = rows[0] || {};
      return { totalTB: r.total_tb || 0, dou: r.dou || 0 };
    },
    data_traffic_by_rat: (rows) => rows.map(r => ({
      rat: r.rat, tb: r.tb || 0, pct: r.pct || 0,
      color: { '2G': '#999', '3G': '#f9a825', '4G': '#4caf50', '5G': '#7b1fa2' }[r.rat] || '#999',
    })),
    data_traffic_by_wilaya: (rows) => rows.map(r => ({
      wilaya: r.wilaya, traffic: r.traffic_tb || 0, users: r.users || 0,
    })),
    data_traffic_by_rat_wilaya: (rows) => rows.map(r => ({
      wilaya: r.wilaya, '2G': r['2G'] || 0, '3G': r['3G'] || 0, '4G': r['4G'] || 0, '5G': r['5G'] || 0,
    })),
    data_traffic_by_apn: (rows) => rows.map(r => ({
      apn: r.apn, traffic: r.traffic_tb || 0, pct: r.pct || 0,
    })),
    data_traffic_growth: (rows) => rows.map(r => ({
      month: r.month, daily: r.daily_tb || 0, monthly: r.monthly_tb || 0,
    })),
    voice_kpi: (rows) => {
      const r = rows[0] || {};
      return {
        callSetupSR: { total: r.call_setup_sr || 0, mo: r.call_setup_sr_mo || 0, mt: r.call_setup_sr_mt || 0 },
        callDropRate: { '2G': r.drop_rate_2g || 0, '3G': r.drop_rate_3g || 0 },
        callSetupDuration: { '2G': r.setup_duration_2g || 0, '3G': r.setup_duration_3g || 0 },
        totalVoiceHours: r.total_voice_hours || 0,
      };
    },
    voice_daily_trend: (rows) => rows.map(r => ({
      day: r.day, hours: r.hours || 0,
    })),
    volte_kpi: (rows) => {
      const r = rows[0] || {};
      return {
        volteUsers: r.volte_users || 0,
        csfbSR: { mo: r.csfb_sr_mo || 0, mt: r.csfb_sr_mt || 0 },
        csfbFallbackRate: r.csfb_fallback_rate || 0,
        srvccSR: r.srvcc_sr || 0,
      };
    },
    sms_kpi: (rows) => {
      const r = rows[0] || {};
      return {
        moSR: r.mo_sr || 0, mtSR: r.mt_sr || 0,
        totalMO: r.total_mo || 0, totalMT: r.total_mt || 0,
      };
    },
    data_quality: (rows) => {
      const r = rows[0] || {};
      return {
        latency: { internal: r.latency_internal || 0, external: r.latency_external || 0 },
        packetLoss: { dl: r.packet_loss_dl || 0, ul: r.packet_loss_ul || 0 },
        tcpSetupSR: r.tcp_setup_sr || 0,
        tcpRetransmission: { dl: r.tcp_retrans_dl || 0, ul: r.tcp_retrans_ul || 0 },
        avgThroughput: { dl: r.avg_throughput_dl || 0, ul: r.avg_throughput_ul || 0 },
        serviceSR: r.service_sr || 0,
        dnsSR: r.dns_sr || 0,
        dnsDelay: r.dns_delay || 0,
      };
    },
    top_apps_traffic: (rows) => rows.map(r => ({
      app: r.app, traffic: r.traffic_tb || 0, pct: r.pct || 0,
    })),
    top_apps_users: (rows) => rows.map(r => ({
      app: r.app, users: r.users || 0,
    })),
    app_categories: (rows) => rows.map((r, i) => ({
      category: r.category, pct: r.pct || 0,
      color: ['#e53935', '#1e88e5', '#43a047', '#fb8c00', '#999'][i] || '#999',
    })),
    gaming: (rows) => {
      const r = rows[0] || {};
      return { users: r.gaming_users || 0, trafficTB: r.traffic_tb || 0 };
    },
    gaming_top: (rows) => rows.map(r => ({
      game: r.game, users: r.users || 0,
    })),
    device_brands: (rows) => rows.map(r => ({
      brand: r.brand, share: r.share || 0,
    })),
    device_models: (rows) => rows.map(r => ({
      model: r.model, count: r.count || 0,
    })),
    device_capability: (rows) => rows.map(r => ({
      type: r.type, pct: r.pct || 0,
    })),
    device_os: (rows) => rows.map((r, i) => ({
      os: r.os, pct: r.pct || 0,
      color: ['#43a047', '#555', '#ccc'][i] || '#999',
    })),
    fiveg_wilaya: (rows) => rows.map(r => ({
      wilaya: r.wilaya, users: r.users || 0, terminals: r.terminals || 0,
      traffic: r.traffic_tb || 0, dou: r.dou || 0,
    })),
    fiveg_overview: (rows) => {
      const r = rows[0] || {};
      return {
        campingRatio: { user: r.camping_user || 0, traffic: r.camping_traffic || 0 },
        dou: r.dou || 0,
      };
    },
    fiveg_bands: (rows) => rows.map(r => ({
      band: r.band, pct: r.pct || 0,
    })),
    roaming_inbound: (rows) => rows.map(r => ({
      country: r.country, operator: r.operator, users: r.users || 0, traffic: r.traffic_tb || 0,
    })),
    roaming_outbound: (rows) => rows.map(r => ({
      country: r.country, operator: r.operator, users: r.users || 0, traffic: r.traffic_tb || 0,
    })),
    geographic: (rows) => {
      const r = rows[0] || {};
      return { urbanVsRural: { urban: r.urban_pct || 0, rural: r.rural_pct || 0 } };
    },
    coverage_gap: (rows) => rows.map(r => ({
      wilaya: r.wilaya, devicePenetration4G: r.device_4g_pct || 0,
      usage4G: r.usage_4g_pct || 0, gap: r.gap || 0,
    })),
  };

  const parser = parsers[sectionKey];
  if (!parser) return null;
  return parser(rows);
}

export const CSV_SECTIONS = [
  { key: 'subscribers_overview', label: '1. Subscribers Overview', desc: 'total_active, data_subscribers, voice_subscribers, volte_subscribers, roaming_inbound, roaming_outbound' },
  { key: 'subscribers_by_rat', label: '1. Subscribers by RAT', desc: 'rat, count, pct' },
  { key: 'subscribers_service_dist', label: '1. Service Distribution', desc: 'type, count, pct' },
  { key: 'subscribers_trend', label: '1. New Subscribers Trend', desc: 'month, new_subscribers' },
  { key: 'data_traffic_overview', label: '2. Data Traffic Overview', desc: 'total_tb, dou' },
  { key: 'data_traffic_by_rat', label: '2. Traffic by RAT', desc: 'rat, tb, pct' },
  { key: 'data_traffic_by_wilaya', label: '2. Traffic by Wilaya', desc: 'wilaya, traffic_tb, users' },
  { key: 'data_traffic_by_rat_wilaya', label: '2. Traffic by RAT by Wilaya', desc: 'wilaya, 2G, 3G, 4G, 5G' },
  { key: 'data_traffic_by_apn', label: '2. Traffic by APN', desc: 'apn, traffic_tb, pct' },
  { key: 'data_traffic_growth', label: '2. Traffic Growth', desc: 'month, daily_tb, monthly_tb' },
  { key: 'voice_kpi', label: '3. Voice KPI', desc: 'call_setup_sr, call_setup_sr_mo, call_setup_sr_mt, drop_rate_2g, drop_rate_3g, setup_duration_2g, setup_duration_3g, total_voice_hours' },
  { key: 'voice_daily_trend', label: '3. Voice Daily Trend', desc: 'day, hours' },
  { key: 'volte_kpi', label: '4. VoLTE KPI', desc: 'volte_users, csfb_sr_mo, csfb_sr_mt, csfb_fallback_rate, srvcc_sr' },
  { key: 'sms_kpi', label: '5. SMS KPI', desc: 'mo_sr, mt_sr, total_mo, total_mt' },
  { key: 'data_quality', label: '6. Data Quality', desc: 'latency_internal, latency_external, packet_loss_dl, packet_loss_ul, tcp_setup_sr, tcp_retrans_dl, tcp_retrans_ul, avg_throughput_dl, avg_throughput_ul, service_sr, dns_sr, dns_delay' },
  { key: 'top_apps_traffic', label: '8. Top Apps by Traffic', desc: 'app, traffic_tb, pct' },
  { key: 'top_apps_users', label: '8. Top Apps by Users', desc: 'app, users' },
  { key: 'app_categories', label: '8. App Categories', desc: 'category, pct' },
  { key: 'gaming', label: '9. Gaming Overview', desc: 'gaming_users, traffic_tb' },
  { key: 'gaming_top', label: '9. Top Games', desc: 'game, users' },
  { key: 'device_brands', label: '10. Device Brands', desc: 'brand, share' },
  { key: 'device_models', label: '10. Device Models', desc: 'model, count' },
  { key: 'device_capability', label: '10. Device Capability', desc: 'type, pct' },
  { key: 'device_os', label: '10. OS Distribution', desc: 'os, pct' },
  { key: 'fiveg_wilaya', label: '11. 5G by Wilaya', desc: 'wilaya, users, terminals, traffic_tb, dou' },
  { key: 'fiveg_overview', label: '11. 5G Overview', desc: 'camping_user, camping_traffic, dou' },
  { key: 'fiveg_bands', label: '11. 5G Bands', desc: 'band, pct' },
  { key: 'roaming_inbound', label: '12. Roaming Inbound', desc: 'country, operator, users, traffic_tb' },
  { key: 'roaming_outbound', label: '12. Roaming Outbound', desc: 'country, operator, users, traffic_tb' },
  { key: 'geographic', label: '16. Geographic', desc: 'urban_pct, rural_pct' },
  { key: 'coverage_gap', label: '16. Coverage Gap', desc: 'wilaya, device_4g_pct, usage_4g_pct, gap' },
];

export function generateTemplateCSV(key) {
  const section = CSV_SECTIONS.find(s => s.key === key);
  if (!section) return '';
  const headers = section.desc;
  const sampleRows = {
    subscribers_overview: '21450000,17820000,19100000,8340000,142000,98000',
    subscribers_by_rat: '2G,2150000,10.0\n3G,4290000,20.0\n4G,12860000,59.9\n5G,2150000,10.1',
    subscribers_service_dist: 'Voice + Data,15200000,70.9\nVoice Only,3900000,18.2\nData Only,2350000,10.9',
    subscribers_trend: 'Apr,182000\nMay,195000\nJun,210000',
    data_traffic_overview: '12480,0.58',
    data_traffic_by_rat: '2G,12.5,0.1\n3G,624,5.0\n4G,9984,80.0\n5G,1859.5,14.9',
    data_traffic_by_wilaya: 'Alger,2870,4200000\nOran,1420,2100000',
    data_traffic_by_rat_wilaya: 'Alger,2,115,2296,457\nOran,1.5,71,1136,211.5',
    data_traffic_by_apn: 'internet,8736,70.0\nmms,124.8,1.0',
    data_traffic_growth: 'Apr,380,11400\nMay,392,11760',
    voice_kpi: '97.2,96.8,97.6,1.05,0.42,5.8,3.9,4820000',
    voice_daily_trend: 'Mon,720000\nTue,695000\nWed,710000',
    volte_kpi: '8340000,93.5,95.1,6.2,97.8',
    sms_kpi: '96.3,94.6,18200000,22400000',
    data_quality: '185,62,0.95,0.38,98.2,2.1,1.4,42.5,12.8,97.1,99.4,28',
    top_apps_traffic: 'YouTube,3120,25.0\nTikTok,1872,15.0',
    top_apps_users: 'WhatsApp,14200000\nFacebook,12800000',
    app_categories: 'Video,43\nSocial,26\nMessaging,12\nGaming,8\nOther,11',
    gaming: '3200000,998.4',
    gaming_top: 'PUBG Mobile,1200000\nFree Fire,850000',
    device_brands: 'Samsung,32.5\nXiaomi,18.2\nOppo,12.4',
    device_models: 'Samsung Galaxy A14,820000\nXiaomi Redmi Note 12,650000',
    device_capability: '2G Only,4.2\n3G,12.5\n4G,62.8\n5G,20.5',
    device_os: 'Android,87.3\niOS,11.2\nOther,1.5',
    fiveg_wilaya: 'Alger,820000,950000,457,0.92\nOran,380000,440000,212,0.88',
    fiveg_overview: '72.4,68.9,0.87',
    fiveg_bands: 'n78 (3.5 GHz),68.5\nn1 (2.1 GHz),22.3\nn28 (700 MHz),9.2',
    roaming_inbound: 'France,Orange,42000,18.5\nTunisia,Tunisie Telecom,28000,8.2',
    roaming_outbound: 'France,Orange,35000,14.2\nTunisia,Ooredoo TN,22000,6.8',
    geographic: '68,32',
    coverage_gap: 'Djelfa,55,28,27\nMsila,52,26,26',
  };
  return headers + '\n' + (sampleRows[key] || '');
}
