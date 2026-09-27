import { createContext, useContext, useState, useCallback } from 'react';
import * as defaults from '../data/networkData';

const DataContext = createContext();

const defaultState = {
  reportMeta: defaults.reportMeta,
  subscriberOverview: defaults.subscriberOverview,
  dataTraffic: defaults.dataTraffic,
  voiceKPI: defaults.voiceKPI,
  volteKPI: defaults.volteKPI,
  smsKPI: defaults.smsKPI,
  dataQuality: defaults.dataQuality,
  topApps: defaults.topApps,
  gaming: defaults.gaming,
  devices: defaults.devices,
  fiveG: defaults.fiveG,
  roaming: defaults.roaming,
  geographic: defaults.geographic,
};

export function DataProvider({ children }) {
  const [data, setData] = useState(defaultState);
  const [loadedSections, setLoadedSections] = useState(new Set());

  const updateSection = useCallback((sectionKey, parsed) => {
    setData(prev => {
      const next = { ...prev };
      const map = {
        subscribers_overview: () => {
          next.subscriberOverview = { ...prev.subscriberOverview, ...parsed };
        },
        subscribers_by_rat: () => {
          next.subscriberOverview = { ...prev.subscriberOverview, byRAT: parsed };
        },
        subscribers_service_dist: () => {
          next.subscriberOverview = { ...prev.subscriberOverview, serviceDistribution: parsed };
        },
        subscribers_trend: () => {
          next.subscriberOverview = { ...prev.subscriberOverview, newSubscribersTrend: parsed };
        },
        data_traffic_overview: () => {
          next.dataTraffic = { ...prev.dataTraffic, ...parsed };
        },
        data_traffic_by_rat: () => {
          next.dataTraffic = { ...prev.dataTraffic, byRAT: parsed };
        },
        data_traffic_by_wilaya: () => {
          next.dataTraffic = { ...prev.dataTraffic, byWilaya: parsed };
        },
        data_traffic_by_rat_wilaya: () => {
          next.dataTraffic = { ...prev.dataTraffic, byRATbyWilaya: parsed };
        },
        data_traffic_by_apn: () => {
          next.dataTraffic = { ...prev.dataTraffic, byAPN: parsed };
        },
        data_traffic_growth: () => {
          next.dataTraffic = { ...prev.dataTraffic, growthTrend: parsed };
        },
        voice_kpi: () => {
          next.voiceKPI = { ...prev.voiceKPI, ...parsed };
        },
        voice_daily_trend: () => {
          next.voiceKPI = { ...prev.voiceKPI, voiceTrend: parsed };
        },
        volte_kpi: () => {
          next.volteKPI = parsed;
        },
        sms_kpi: () => {
          next.smsKPI = parsed;
        },
        data_quality: () => {
          next.dataQuality = parsed;
        },
        top_apps_traffic: () => {
          next.topApps = { ...prev.topApps, byTraffic: parsed };
        },
        top_apps_users: () => {
          next.topApps = { ...prev.topApps, byUsers: parsed };
        },
        app_categories: () => {
          next.topApps = { ...prev.topApps, categoryDistribution: parsed };
        },
        gaming: () => {
          next.gaming = { ...prev.gaming, ...parsed };
        },
        gaming_top: () => {
          next.gaming = { ...prev.gaming, topGames: parsed };
        },
        device_brands: () => {
          next.devices = { ...prev.devices, topBrands: parsed };
        },
        device_models: () => {
          next.devices = { ...prev.devices, topModels: parsed };
        },
        device_capability: () => {
          next.devices = { ...prev.devices, capability: parsed };
        },
        device_os: () => {
          next.devices = { ...prev.devices, osDistribution: parsed };
        },
        fiveg_wilaya: () => {
          next.fiveG = { ...prev.fiveG, usersByWilaya: parsed };
        },
        fiveg_overview: () => {
          next.fiveG = { ...prev.fiveG, ...parsed };
        },
        fiveg_bands: () => {
          next.fiveG = { ...prev.fiveG, penetrationByBand: parsed };
        },
        roaming_inbound: () => {
          next.roaming = { ...prev.roaming, inbound: parsed };
        },
        roaming_outbound: () => {
          next.roaming = { ...prev.roaming, outbound: parsed };
        },
        geographic: () => {
          next.geographic = { ...prev.geographic, ...parsed };
        },
        coverage_gap: () => {
          next.geographic = { ...prev.geographic, coverageGap: parsed };
        },
      };
      if (map[sectionKey]) map[sectionKey]();
      return next;
    });
    setLoadedSections(prev => new Set([...prev, sectionKey]));
  }, []);

  return (
    <DataContext.Provider value={{ data, updateSection, loadedSections }}>
      {children}
    </DataContext.Provider>
  );
}

export const useData = () => useContext(DataContext);
