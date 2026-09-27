export const networkOverview = {
  totalSites: 12847,
  activeSites: 12103,
  sitesDown: 744,
  totalSubscribers: 28400000,
  activeSubscribers: 24100000,
  technologies: [
    { name: '5G', sites: 4250, coverage: 62 },
    { name: '4G LTE', sites: 8100, coverage: 94 },
    { name: '3G', sites: 6200, coverage: 88 },
    { name: '2G', sites: 3800, coverage: 72 },
  ],
};

export const kpiData = {
  availability: 99.87,
  avgThroughputDL: 84.3,
  avgThroughputUL: 22.7,
  latency: 12.4,
  callSetupSuccessRate: 99.2,
  callDropRate: 0.34,
  handoverSuccessRate: 98.7,
  rrcConnectionSuccessRate: 99.5,
  erabSetupSuccessRate: 99.1,
  volteDropRate: 0.21,
  prbUtilizationDL: 48.2,
  prbUtilizationUL: 32.6,
};

export const kqiData = {
  videoStreamingMOS: 4.1,
  voiceMOS: 4.3,
  webBrowsingScore: 92,
  gamingLatency: 18.5,
  appDownloadSpeed: 76.2,
  videoCallQuality: 4.0,
  overallCSAT: 78,
  nps: 42,
};

export const trafficTrend = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  dataTrafficTB: Math.round((120 + 80 * Math.sin((i - 6) * Math.PI / 12) + Math.random() * 20) * 10) / 10,
  voiceTrafficErl: Math.round((3000 + 2000 * Math.sin((i - 8) * Math.PI / 12) + Math.random() * 300) * 10) / 10,
  activeUsers: Math.round(800000 + 600000 * Math.sin((i - 10) * Math.PI / 12) + Math.random() * 50000),
}));

export const regionPerformance = [
  { region: 'North', availability: 99.9, throughput: 92, subscribers: 6200000, satisfaction: 82 },
  { region: 'South', availability: 99.8, throughput: 78, subscribers: 7100000, satisfaction: 76 },
  { region: 'East', availability: 99.7, throughput: 85, subscribers: 5800000, satisfaction: 79 },
  { region: 'West', availability: 99.9, throughput: 88, subscribers: 5400000, satisfaction: 81 },
  { region: 'Central', availability: 99.95, throughput: 96, subscribers: 3900000, satisfaction: 85 },
];

export const userBehavior = {
  appUsage: [
    { app: 'Video Streaming', percentage: 38, dataGB: 4200 },
    { app: 'Social Media', percentage: 24, dataGB: 2640 },
    { app: 'Messaging', percentage: 12, dataGB: 1320 },
    { app: 'Web Browsing', percentage: 10, dataGB: 1100 },
    { app: 'Gaming', percentage: 8, dataGB: 880 },
    { app: 'Other', percentage: 8, dataGB: 880 },
  ],
  avgDataPerUser: 12.4,
  avgSessionDuration: 42,
  peakHour: '20:00',
  deviceDistribution: [
    { type: '5G Devices', count: 8200000, percentage: 34 },
    { type: '4G Devices', count: 12400000, percentage: 51 },
    { type: '3G Devices', count: 2600000, percentage: 11 },
    { type: '2G Devices', count: 900000, percentage: 4 },
  ],
  dailyActiveUsers: Array.from({ length: 7 }, (_, i) => ({
    day: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][i],
    users: Math.round(18000000 + Math.random() * 4000000 + (i >= 5 ? 2000000 : 0)),
  })),
};

export const alarms = [
  { id: 1, severity: 'critical', site: 'Site-NR-4521', message: 'gNB link failure', time: '2 min ago' },
  { id: 2, severity: 'critical', site: 'Site-LTE-1287', message: 'S1 interface down', time: '8 min ago' },
  { id: 3, severity: 'major', site: 'Site-NR-3892', message: 'High PRB utilization (>90%)', time: '15 min ago' },
  { id: 4, severity: 'major', site: 'Site-LTE-0654', message: 'Handover failure rate >5%', time: '22 min ago' },
  { id: 5, severity: 'minor', site: 'Site-NR-2103', message: 'Throughput degradation', time: '35 min ago' },
  { id: 6, severity: 'minor', site: 'Site-LTE-4401', message: 'Temperature warning', time: '1 hr ago' },
];
