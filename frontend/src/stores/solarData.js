/* 全站共享的站点统计数据（单例 composable，等价于轻量 store）。
   数据只加载一次，三个视图与地图组件共用。 */

import { computed, ref } from "vue";

import { formatNumber, parseCsv } from "@/utils/format";
import { provinceNames } from "@/utils/provinces";
import { gradeOf100 } from "@/utils/pvpi";

const dataLoadError = ref("");
const loaded = ref(false);

const statsData = ref([]);
const stationData = ref([]);
const chinaGeoJson = ref(null);

const summary = ref({
  avgPvpi: "--",
  maxGhi: "--",
  totalArea: "--",
  totalStations: "--"
});
const suitability = ref([]);
const gradeThresholds = ref([0, 0, 0]);
const kpiItems = ref([]);
const topSitesAll = ref([]);
const rankItemsAll = ref([]);
const provincePvpiMap = ref({});
const selectedProvince = ref("");
const resourceRows = ref([]);
const profitRows = ref([]);

let loadPromise = null;
let chinaMapPromise = null;

const loadChinaMap = async () => {
  if (!chinaMapPromise) {
    chinaMapPromise = (async () => {
      const urls = ["/data/china_full.json", "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json"];
      let lastError;
      for (const url of urls) {
        try {
          const response = await fetch(url);
          if (!response.ok) throw new Error(`${url} load failed`);
          const geoJson = await response.json();
          chinaGeoJson.value = geoJson;
          return geoJson;
        } catch (error) {
          lastError = error;
        }
      }
      throw lastError || new Error("china map load failed");
    })();
  }
  return chinaMapPromise;
};

const resetState = () => {
  suitability.value = [];
  topSitesAll.value = [];
  kpiItems.value = [];
  rankItemsAll.value = [];
  provincePvpiMap.value = {};
  selectedProvince.value = "";
  resourceRows.value = [];
  profitRows.value = [];
  summary.value = { avgPvpi: "--", maxGhi: "--", totalArea: "--", totalStations: "--" };
  statsData.value = [];
  stationData.value = [];
};

const validateData = (stats, stations) => {
  if (!stats.length || !stations.length) {
    throw new Error("真实数据文件为空");
  }
  const requiredStats = ["province", "Count", "Total_Area_km2"];
  const requiredStations = ["province", "lon", "lat", "area_km2", "ghi_mean", "temp_mean", "temp_std", "precip_annual", "PVPI"];
  for (const field of requiredStats) {
    if (!(field in stats[0])) throw new Error(`省级统计缺少字段: ${field}`);
  }
  for (const field of requiredStations) {
    if (!(field in stations[0])) throw new Error(`站点数据缺少字段: ${field}`);
  }
};

const prepareCards = (stats, stations) => {
  const totalStations = stats.reduce((sum, row) => sum + row.Count, 0);
  const totalArea = stats.reduce((sum, row) => sum + row.Total_Area_km2, 0);
  const avgPvpi = stations.reduce((sum, row) => sum + row.PVPI, 0) / stations.length;
  const maxGhi = Math.max(...stations.map((row) => row.ghi_mean));

  summary.value = {
    avgPvpi: formatNumber(avgPvpi, 2),
    maxGhi: formatNumber(maxGhi, 2),
    totalArea: formatNumber(totalArea, 1),
    totalStations: formatNumber(totalStations)
  };

  const sortedPvpi = [...stations].sort((a, b) => b.PVPI - a.PVPI);
  const thresholds = [
    sortedPvpi[Math.floor(sortedPvpi.length * 0.15)].PVPI,
    sortedPvpi[Math.floor(sortedPvpi.length * 0.4)].PVPI,
    sortedPvpi[Math.floor(sortedPvpi.length * 0.7)].PVPI
  ];
  const counts = [
    stations.filter((row) => row.PVPI >= thresholds[0]).length,
    stations.filter((row) => row.PVPI < thresholds[0] && row.PVPI >= thresholds[1]).length,
    stations.filter((row) => row.PVPI < thresholds[1] && row.PVPI >= thresholds[2]).length,
    stations.filter((row) => row.PVPI < thresholds[2]).length
  ];
  suitability.value = [
    { name: "优选区", value: Math.round((counts[0] / stations.length) * 100), count: formatNumber(counts[0]), color: "#00ffa3" },
    { name: "适宜区", value: Math.round((counts[1] / stations.length) * 100), count: formatNumber(counts[1]), color: "#00d4fe" },
    { name: "备选区", value: Math.round((counts[2] / stations.length) * 100), count: formatNumber(counts[2]), color: "#ffc53d" },
    { name: "约束区", value: Math.round((counts[3] / stations.length) * 100), count: formatNumber(counts[3]), color: "#ff6b6b" }
  ];
  gradeThresholds.value = thresholds;

  kpiItems.value = [
    { label: "候选电站", value: totalStations, digits: 0, unit: "座", hero: true },
    { label: "覆盖省域", value: stats.length, digits: 0, unit: "个" },
    { label: "可用面积", value: totalArea, digits: 1, unit: "km²" },
    { label: "平均 PVPI", value: avgPvpi, digits: 2, unit: "" },
    { label: "最大辐照", value: maxGhi, digits: 2, unit: "kWh/m²" },
    { label: "优选区占比", value: (counts[0] / stations.length) * 100, digits: 1, unit: "%" }
  ];

  topSitesAll.value = sortedPvpi.slice(0, 10).map((row, index) => ({
    ...row,
    rank: index + 1,
    gradeColor: gradeOf100(row.PVPI, thresholds).color,
    provinceName: provinceNames[row.province] || row.province,
    area_km2: formatNumber(row.area_km2, 2),
    ghi_mean: formatNumber(row.ghi_mean, 2),
    precip_annual: formatNumber(row.precip_annual, 0),
    PVPI: formatNumber(row.PVPI, 2)
  }));

  const stationGroups = stations.reduce((groups, row) => {
    if (!groups.has(row.province)) groups.set(row.province, []);
    groups.get(row.province).push(row);
    return groups;
  }, new Map());

  const provinceSummary = stats.map((row) => {
    const rows = stationGroups.get(row.province) || [];
    const avgValue = (key) => rows.reduce((sum, item) => sum + item[key], 0) / rows.length;
    const avgPvpi = avgValue("PVPI");
    const avgGhi = avgValue("ghi_mean");
    return {
      province: row.province,
      provinceName: provinceNames[row.province] || row.province,
      count: row.Count,
      totalArea: row.Total_Area_km2,
      avgPvpi,
      avgGhi,
      profitIndex: avgPvpi * row.Total_Area_km2
    };
  }).filter((row) => Number.isFinite(row.avgPvpi) && Number.isFinite(row.avgGhi));

  provincePvpiMap.value = Object.fromEntries(
    provinceSummary.filter((row) => Number.isFinite(row.avgPvpi)).map((row) => [row.provinceName, Number(row.avgPvpi.toFixed(2))])
  );

  rankItemsAll.value = [...provinceSummary]
    .filter((row) => Number.isFinite(row.avgPvpi))
    .sort((a, b) => b.avgPvpi - a.avgPvpi)
    .slice(0, 8)
    .map((row) => ({ name: row.provinceName, value: Number(row.avgPvpi.toFixed(2)) }));

  resourceRows.value = [...provinceSummary]
    .sort((a, b) => b.avgGhi - a.avgGhi)
    .slice(0, 10)
    .map((row) => ({
      ...row,
      count: formatNumber(row.count),
      totalArea: formatNumber(row.totalArea, 1),
      avgPvpi: formatNumber(row.avgPvpi, 2),
      avgGhi: formatNumber(row.avgGhi, 2)
    }));

  profitRows.value = [...provinceSummary]
    .sort((a, b) => b.profitIndex - a.profitIndex)
    .slice(0, 10)
    .map((row) => ({
      ...row,
      count: formatNumber(row.count),
      totalArea: formatNumber(row.totalArea, 1),
      avgPvpi: formatNumber(row.avgPvpi, 2),
      profitIndex: formatNumber(row.profitIndex, 0)
    }));
};

const loadData = async () => {
  if (loaded.value) return;
  if (!loadPromise) {
    dataLoadError.value = "";
    loadPromise = (async () => {
      try {
        const [statsText, stationText] = await Promise.all([
          fetch("/data/provincial_statistics.csv").then((res) => {
            if (!res.ok) throw new Error("provincial_statistics.csv load failed");
            return res.text();
          }),
          fetch("/data/pv_stations_mcdm_scored.csv").then((res) => {
            if (!res.ok) throw new Error("pv_stations_mcdm_scored.csv load failed");
            return res.text();
          })
        ]);
        const stats = parseCsv(statsText);
        const stations = parseCsv(stationText);
        validateData(stats, stations);
        statsData.value = stats;
        stationData.value = stations;
        prepareCards(stats, stations);
        loaded.value = true;
      } catch (error) {
        dataLoadError.value = error.message || "真实数据加载失败";
        resetState();
        loadPromise = null;
        throw error;
      }
    })();
  }
  return loadPromise;
};

const setSelectedProvince = (province) => {
  selectedProvince.value = province || "";
};

/* 态势页排行：选中省份时只显示该省 PVPI，否则显示 TOP8 */
const rankItems = computed(() => {
  if (selectedProvince.value) {
    const hit = provincePvpiMap.value[selectedProvince.value];
    return Number.isFinite(Number(hit)) ? [{ name: selectedProvince.value, value: Number(hit) }] : [];
  }
  return rankItemsAll.value;
});

/* TOP10 榜单：选中省份时按省过滤（态势页），资源收益页固定用 topSitesAll */
const topSites = computed(() =>
  selectedProvince.value ? topSitesAll.value.filter((row) => row.provinceName === selectedProvince.value) : topSitesAll.value
);

export function useSolarDataStore() {
  return {
    // state
    dataLoadError,
    loaded,
    statsData,
    stationData,
    chinaGeoJson,
    summary,
    suitability,
    gradeThresholds,
    kpiItems,
    topSitesAll,
    rankItemsAll,
    provincePvpiMap,
    selectedProvince,
    resourceRows,
    profitRows,
    // computed
    rankItems,
    topSites,
    // actions
    loadChinaMap,
    loadData,
    setSelectedProvince
  };
}
