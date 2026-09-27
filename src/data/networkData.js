// ATM Mobilis - Daily Service Quality Report Data

export const reportMeta = {
  operator: 'Mobilis',
  date: 'September 27, 2026',
  department: 'SOC & Network Performance',
};

// 1. SUBSCRIBER OVERVIEW
export const subscriberOverview = {
  totalActive: 21450000,
  dataSubscribers: 17820000,
  voiceSubscribers: 19100000,
  volteSubscribers: 8340000,
  byRAT: [
    { rat: '2G', count: 2150000, pct: 10.0 },
    { rat: '3G', count: 4290000, pct: 20.0 },
    { rat: '4G', count: 12860000, pct: 59.9 },
    { rat: '5G', count: 2150000, pct: 10.1 },
  ],
  serviceDistribution: [
    { type: 'Voice + Data', count: 15200000, pct: 70.9 },
    { type: 'Voice Only', count: 3900000, pct: 18.2 },
    { type: 'Data Only', count: 2350000, pct: 10.9 },
  ],
  newSubscribersTrend: [
    { month: 'Apr', value: 182000 }, { month: 'May', value: 195000 },
    { month: 'Jun', value: 210000 }, { month: 'Jul', value: 228000 },
    { month: 'Aug', value: 215000 }, { month: 'Sep', value: 237000 },
  ],
  roaming: { inbound: 142000, outbound: 98000 },
};

// 2. DATA TRAFFIC
export const dataTraffic = {
  totalTB: 12480,
  byRAT: [
    { rat: '2G', tb: 12.5, pct: 0.1, color: '#999' },
    { rat: '3G', tb: 624, pct: 5.0, color: '#f9a825' },
    { rat: '4G', tb: 9984, pct: 80.0, color: '#4caf50' },
    { rat: '5G', tb: 1859.5, pct: 14.9, color: '#7b1fa2' },
  ],
  byWilaya: [
    { wilaya: 'Alger', traffic: 2870, users: 4200000 },
    { wilaya: 'Oran', traffic: 1420, users: 2100000 },
    { wilaya: 'Constantine', traffic: 980, users: 1450000 },
    { wilaya: 'Annaba', traffic: 620, users: 920000 },
    { wilaya: 'Blida', traffic: 580, users: 860000 },
    { wilaya: 'Sétif', traffic: 540, users: 810000 },
    { wilaya: 'Batna', traffic: 480, users: 720000 },
    { wilaya: 'Tlemcen', traffic: 420, users: 630000 },
    { wilaya: 'Béjaïa', traffic: 390, users: 580000 },
    { wilaya: 'Tizi Ouzou', traffic: 370, users: 550000 },
  ],
  byRATbyWilaya: [
    { wilaya: 'Alger', '2G': 2, '3G': 115, '4G': 2296, '5G': 457 },
    { wilaya: 'Oran', '2G': 1.5, '3G': 71, '4G': 1136, '5G': 211.5 },
    { wilaya: 'Constantine', '2G': 1, '3G': 49, '4G': 784, '5G': 146 },
    { wilaya: 'Annaba', '2G': 0.8, '3G': 31, '4G': 496, '5G': 92.2 },
    { wilaya: 'Blida', '2G': 0.7, '3G': 29, '4G': 464, '5G': 86.3 },
  ],
  byAPN: [
    { apn: 'internet', traffic: 8736, pct: 70.0 },
    { apn: 'mms', traffic: 124.8, pct: 1.0 },
    { apn: 'wap', traffic: 62.4, pct: 0.5 },
    { apn: 'enterprise', traffic: 1872, pct: 15.0 },
    { apn: 'iot', traffic: 374.4, pct: 3.0 },
    { apn: 'other', traffic: 1310.4, pct: 10.5 },
  ],
  dou: 0.58,
  growthTrend: [
    { month: 'Apr', daily: 380, monthly: 11400 },
    { month: 'May', daily: 392, monthly: 11760 },
    { month: 'Jun', daily: 405, monthly: 12150 },
    { month: 'Jul', daily: 418, monthly: 12540 },
    { month: 'Aug', daily: 410, monthly: 12300 },
    { month: 'Sep', daily: 416, monthly: 12480 },
  ],
};

// 3. VOICE KPI (CS)
export const voiceKPI = {
  callSetupSR: { total: 97.2, mo: 96.8, mt: 97.6 },
  callDropRate: { '2G': 1.05, '3G': 0.42 },
  callSetupDuration: { '2G': 5.8, '3G': 3.9 },
  totalVoiceHours: 4820000,
  voiceTrend: [
    { day: 'Mon', hours: 720000 }, { day: 'Tue', hours: 695000 },
    { day: 'Wed', hours: 710000 }, { day: 'Thu', hours: 685000 },
    { day: 'Fri', hours: 640000 }, { day: 'Sat', hours: 680000 },
    { day: 'Sun', hours: 690000 },
  ],
};

// 4. VoLTE KPI
export const volteKPI = {
  volteUsers: 8340000,
  csfbSR: { mo: 93.5, mt: 95.1 },
  csfbFallbackRate: 6.2,
  srvccSR: 97.8,
};

// 5. SMS
export const smsKPI = {
  mtSR: 94.6,
  moSR: 96.3,
  totalMO: 18200000,
  totalMT: 22400000,
};

// 6. DATA QUALITY / USER EXPERIENCE
export const dataQuality = {
  latency: { internal: 185, external: 62 },
  packetLoss: { dl: 0.95, ul: 0.38 },
  tcpSetupSR: 98.2,
  tcpRetransmission: { dl: 2.1, ul: 1.4 },
  avgThroughput: { dl: 42.5, ul: 12.8 },
  serviceSR: 97.1,
  dnsSR: 99.4,
  dnsDelay: 28,
};

// 8. TOP APPLICATIONS
export const topApps = {
  byTraffic: [
    { app: 'YouTube', traffic: 3120, pct: 25.0 },
    { app: 'TikTok', traffic: 1872, pct: 15.0 },
    { app: 'Facebook', traffic: 1497.6, pct: 12.0 },
    { app: 'Instagram', traffic: 1248, pct: 10.0 },
    { app: 'WhatsApp', traffic: 624, pct: 5.0 },
    { app: 'Snapchat', traffic: 499.2, pct: 4.0 },
    { app: 'Netflix', traffic: 374.4, pct: 3.0 },
    { app: 'Other', traffic: 3244.8, pct: 26.0 },
  ],
  byUsers: [
    { app: 'WhatsApp', users: 14200000 },
    { app: 'Facebook', users: 12800000 },
    { app: 'YouTube', users: 11500000 },
    { app: 'Instagram', users: 9800000 },
    { app: 'TikTok', users: 8400000 },
  ],
  categoryDistribution: [
    { category: 'Video', pct: 43, color: '#e53935' },
    { category: 'Social', pct: 26, color: '#1e88e5' },
    { category: 'Messaging', pct: 12, color: '#43a047' },
    { category: 'Gaming', pct: 8, color: '#fb8c00' },
    { category: 'Other', pct: 11, color: '#999' },
  ],
};

// 9. GAMING
export const gaming = {
  users: 3200000,
  trafficTB: 998.4,
  topGames: [
    { game: 'PUBG Mobile', users: 1200000 },
    { game: 'Free Fire', users: 850000 },
    { game: 'Mobile Legends', users: 420000 },
    { game: 'Clash Royale', users: 380000 },
    { game: 'FIFA Mobile', users: 350000 },
  ],
};

// 10. DEVICE / TERMINAL
export const devices = {
  topBrands: [
    { brand: 'Samsung', share: 32.5 },
    { brand: 'Xiaomi', share: 18.2 },
    { brand: 'Oppo', share: 12.4 },
    { brand: 'Huawei', share: 10.8 },
    { brand: 'Infinix', share: 8.1 },
    { brand: 'Other', share: 18.0 },
  ],
  topModels: [
    { model: 'Samsung Galaxy A14', count: 820000 },
    { model: 'Xiaomi Redmi Note 12', count: 650000 },
    { model: 'Samsung Galaxy A54', count: 480000 },
    { model: 'Oppo A78', count: 420000 },
    { model: 'Infinix Hot 30', count: 390000 },
  ],
  capability: [
    { type: '2G Only', pct: 4.2 },
    { type: '3G', pct: 12.5 },
    { type: '4G', pct: 62.8 },
    { type: '5G', pct: 20.5 },
  ],
  osDistribution: [
    { os: 'Android', pct: 87.3, color: '#43a047' },
    { os: 'iOS', pct: 11.2, color: '#555' },
    { os: 'Other', pct: 1.5, color: '#ccc' },
  ],
};

// 11. 5G ANALYTICS
export const fiveG = {
  usersByWilaya: [
    { wilaya: 'Alger', users: 820000, terminals: 950000, traffic: 457, dou: 0.92 },
    { wilaya: 'Oran', users: 380000, terminals: 440000, traffic: 212, dou: 0.88 },
    { wilaya: 'Constantine', users: 245000, terminals: 285000, traffic: 146, dou: 0.85 },
    { wilaya: 'Annaba', users: 165000, terminals: 192000, traffic: 92, dou: 0.82 },
    { wilaya: 'Blida', users: 148000, terminals: 172000, traffic: 86, dou: 0.80 },
    { wilaya: 'Sétif', users: 120000, terminals: 140000, traffic: 68, dou: 0.78 },
  ],
  campingRatio: { user: 72.4, traffic: 68.9 },
  dou: 0.87,
  penetrationByBand: [
    { band: 'n78 (3.5 GHz)', pct: 68.5 },
    { band: 'n1 (2.1 GHz)', pct: 22.3 },
    { band: 'n28 (700 MHz)', pct: 9.2 },
  ],
};

// 12. ROAMING
export const roaming = {
  inbound: [
    { country: 'France', operator: 'Orange', users: 42000, traffic: 18.5 },
    { country: 'Tunisia', operator: 'Tunisie Telecom', users: 28000, traffic: 8.2 },
    { country: 'Morocco', operator: 'Maroc Telecom', users: 18000, traffic: 5.4 },
    { country: 'Turkey', operator: 'Turkcell', users: 12000, traffic: 4.1 },
    { country: 'Spain', operator: 'Movistar', users: 9500, traffic: 3.2 },
  ],
  outbound: [
    { country: 'France', operator: 'Orange', users: 35000, traffic: 14.2 },
    { country: 'Tunisia', operator: 'Ooredoo TN', users: 22000, traffic: 6.8 },
    { country: 'Turkey', operator: 'Turkcell', users: 15000, traffic: 5.1 },
    { country: 'UAE', operator: 'Etisalat', users: 8000, traffic: 3.5 },
    { country: 'Spain', operator: 'Movistar', users: 6500, traffic: 2.8 },
  ],
  byRAT: [
    { rat: '2G', pct: 5 },
    { rat: '3G', pct: 18 },
    { rat: '4G', pct: 72 },
    { rat: '5G', pct: 5 },
  ],
  topWilayas: ['Alger', 'Oran', 'Annaba', 'Constantine', 'Tlemcen'],
};

// 16. GEOGRAPHIC ANALYSIS
export const geographic = {
  urbanVsRural: { urban: 68, rural: 32 },
  coverageGap: [
    { wilaya: 'Djelfa', devicePenetration4G: 55, usage4G: 28, gap: 27 },
    { wilaya: 'M\'sila', devicePenetration4G: 52, usage4G: 26, gap: 26 },
    { wilaya: 'Tiaret', devicePenetration4G: 48, usage4G: 24, gap: 24 },
    { wilaya: 'Saïda', devicePenetration4G: 45, usage4G: 23, gap: 22 },
    { wilaya: 'Médéa', devicePenetration4G: 50, usage4G: 29, gap: 21 },
  ],
};
