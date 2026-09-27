export const lastDayIndicators = {
  date: 'Wednesday, September 27, 2026',
  totalActiveSubscribers: 11.69,
  dataSubscribers: 9.32,
  voiceSubscribers: 9.32,
  totalTrafficTB: 8.256,
  totalVoiceMillionH: 5.33,
  customerExperienceIndex: 85,
};

export const competitors = [
  { name: 'Ooredoo', logo: 'ooredoo', enodeBs: 9789, color: '#e4002b' },
  { name: 'Djezzy', logo: 'djezzy', enodeBs: 7437, color: '#e4002b' },
  { name: 'Mobilis', logo: 'mobilis', enodeBs: 11099, color: '#4a9b4a' },
];

export const dataTrafficDistribution = [
  { name: '4G', value: 91.5, color: '#e4002b' },
  { name: '5G', value: 3.7, color: '#00857c' },
  { name: '3G', value: 4.8, color: '#7fba42' },
];

export const dataTrafficLast7Days = [
  { name: '4G', value: 91.1, color: '#e4002b' },
  { name: '5G', value: 3.8, color: '#00857c' },
  { name: '3G', value: 5.1, color: '#7fba42' },
];

export const voiceTrafficDistribution = [
  { name: 'Legacy Voice', value: 69.2, color: '#00857c' },
  { name: 'OTT', value: 30.8, color: '#b0dcd5' },
];

export const subscribersMaxRAT = [
  { name: '4G', value: 68.5, color: '#00857c' },
  { name: '3G', value: 13.3, color: '#b0dcd5' },
  { name: '2G', value: 12.0, color: '#7fba42' },
  { name: '5G', value: 6.2, color: '#e4002b' },
];

const months = ['Jan 2026', 'Feb 2026', 'Mar 2026', 'Apr 2026', 'May 2026', 'Jun 2026', 'Jul 2026', 'Aug 2026', 'Sep 2026'];
export const subscriberEvolution = months.map((m, i) => ({
  month: m,
  voiceOnly: Math.round(1800000 + Math.random() * 200000),
  voiceAndData: Math.round(5500000 + i * 80000 + Math.random() * 200000),
  dataOnly: Math.round(3200000 + i * 50000 + Math.random() * 150000),
}));

export const voiceKPI = {
  callSetupSR: 96.64,
  moCSFBSR: 92.29,
  mtCSFBSR: 94.27,
  mo: 96.6,
  mt: 98.9,
  dropRate: 0.28,
  dropRate2G: 1.18,
  dropRate3G: 0.16,
  callSetupAvDuration: 4.64,
  callSetupAvDuration2G: 6.40,
  callSetupAvDuration3G: 4.44,
  smsMTSR: 85.17,
};

const voiceMonths = [];
for (let y = 2025; y <= 2026; y++) {
  for (let m = (y === 2025 ? 1 : 1); m <= (y === 2026 ? 9 : 12); m++) {
    for (let w = 0; w < 4; w++) {
      voiceMonths.push({
        period: `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1]} ${y}`,
        legacyVoice: Math.round(2800000 + Math.random() * 800000 + (y === 2026 ? -200000 * m / 12 : 0)),
        ottVoice: Math.round(3200000 + Math.random() * 600000 + (y === 2026 ? 100000 * m / 12 : 0)),
      });
    }
  }
}
export const voiceTrafficTrend = voiceMonths;

export const dataKPI = {
  internetAccessibility: 87.8,
  latency: 281,
  latencyIntern: 204,
  latencyExtern: 72,
  packetLoss: 1.09,
  packetLossDL: 1.20,
  packetLossUL: 0.40,
};

const trafficMonths = [];
for (let y = 2025; y <= 2026; y++) {
  for (let m = (y === 2025 ? 1 : 1); m <= (y === 2026 ? 9 : 12); m++) {
    for (let w = 0; w < 4; w++) {
      const base3G = 200 + Math.random() * 100;
      const base4G = 3500 + Math.random() * 1000 + (y === 2026 ? m * 150 : m * 80);
      const base5G = (y === 2026 && m > 3 ? 200 + m * 50 + Math.random() * 100 : 50 + Math.random() * 50);
      trafficMonths.push({
        period: `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1]} ${y}`,
        '3G': Math.round(base3G),
        '4G': Math.round(base4G),
        '5G': Math.round(base5G),
      });
    }
  }
}
export const trafficVolumeTrend = trafficMonths;
