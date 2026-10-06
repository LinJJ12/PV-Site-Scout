<template>
  <main class="dashboard">
    <KpiStrip :items="kpiItems" class="dash-kpi" />
    <aside class="dash-col">
      <PanelCard title="各等级选址占比" note="SUITABILITY MIX" style="flex: 11;">
        <div class="donut-wrap">
          <div ref="suitabilityPieRef" class="chart-fill"></div>
          <div class="donut-center"><strong>{{ summary.totalStations }}</strong><span>候选站点总数</span></div>
          <div class="grade-rows">
            <div class="grade-row" v-for="grade in suitability" :key="grade.name">
              <i :style="{ background: grade.color, boxShadow: `0 0 6px ${grade.color}` }"></i>
              <span>{{ grade.name }}</span>
              <span class="bar"><b :style="{ width: grade.value + '%', background: `linear-gradient(90deg, transparent, ${grade.color})` }"></b></span>
              <strong>{{ grade.count }}</strong>
              <span class="pct">{{ Number(grade.value).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </PanelCard>

      <PanelCard title="省域潜力梯队" :note="selectedProvince ? `${selectedProvince} · PVPI` : 'TOP 8 · PVPI'" style="flex: 9;">
        <RankBars :items="rankItems" />
      </PanelCard>
    </aside>

    <section class="dash-center">
      <div class="map-shell">
        <ThreeChinaMap
          v-if="chinaGeoJson"
          class="map-chart"
          :geo-json="chinaGeoJson"
          :stats="statsData"
          :stations="stationData"
          :province-names="provinceNames"
          :normalize-province-name="normalizeProvinceName"
          :province-pvpi="provincePvpiMap"
          mode="dashboard"
          @province-focus="handleProvinceFocus"
        />
        <div class="map-chips">
          <div class="chip"><span>PVPI 均值</span><strong>{{ summary.avgPvpi }}</strong></div>
          <div class="chip"><span>最大辐照</span><strong>{{ summary.maxGhi }}</strong><small>kWh/m²</small></div>
        </div>
      </div>
    </section>

    <aside class="dash-col">
      <PanelCard title="资源与风险画像" note="NATIONAL PROFILE" style="flex: 8;">
        <div ref="radarChartRef" class="chart-fill"></div>
      </PanelCard>

      <PanelCard
        :title="selectedProvince ? `${selectedProvince} · 候选电站评分` : '综合评分 TOP10 候选电站'"
        :note="selectedProvince ? 'CLICK MAP TO RESET' : 'MCDM RANKING'"
        style="flex: 12;"
      >
        <div class="board-wrap">
          <AutoScrollTable
            :columns="[
              { key: 'rank', label: '排名', align: 'center' },
              { key: 'provinceName', label: '省份' },
              { key: 'area_km2', label: '可用面积 km²' },
              { key: 'ghi_mean', label: 'GHI', align: 'right' },
              { key: 'PVPI', label: 'PVPI', align: 'right', colorKey: 'gradeColor' }
            ]"
            :rows="topSites"
          />
        </div>
      </PanelCard>
    </aside>
  </main>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";

import ThreeChinaMap from "@/components/ThreeChinaMap.vue";
import AutoScrollTable from "@/components/AutoScrollTable.vue";
import KpiStrip from "@/components/KpiStrip.vue";
import PanelCard from "@/components/PanelCard.vue";
import RankBars from "@/components/RankBars.vue";
import { useCharts } from "@/composables/useCharts";
import { useSolarDataStore } from "@/stores/solarData";
import { formatNumber } from "@/utils/format";
import { normalizeProvinceName, provinceNames } from "@/utils/provinces";

const solar = useSolarDataStore();
const {
  chinaGeoJson,
  statsData,
  stationData,
  summary,
  suitability,
  kpiItems,
  provincePvpiMap,
  selectedProvince,
  rankItems,
  topSites,
  setSelectedProvince
} = solar;
const { initChart } = useCharts();

const suitabilityPieRef = ref(null);
const radarChartRef = ref(null);

const renderDashboardCharts = () => {
  const stats = solar.statsData.value;
  const stations = solar.stationData.value;
  if (!stats.length || !stations.length) return;

  initChart(suitabilityPieRef.value).setOption({
    tooltip: {
      trigger: "item",
      formatter(params) {
        return `${params.name}<br/>站点数量：${formatNumber(params.value)} 座<br/>占比：${params.percent}%`;
      }
    },
    series: [
      {
        type: "pie",
        radius: ["58%", "80%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: {
          borderColor: "rgba(5, 13, 31, .9)",
          borderWidth: 2
        },
        data: solar.suitability.value.map((item) => ({
          name: item.name,
          value: Number(String(item.count).replace(/,/g, "")),
          itemStyle: { color: item.color }
        }))
      }
    ]
  });

  renderRadar(stats, stations);
};

const renderRadar = (stats, stations) => {
  const avg = (key) => stations.reduce((sum, row) => sum + row[key], 0) / stations.length;
  const max = (key) => Math.max(...stations.map((row) => row[key]));
  const totalArea = stats.reduce((sum, row) => sum + row.Total_Area_km2, 0);
  const stationDensity = totalArea > 0 ? stations.length / totalArea : 0;
  const densityScore = Math.min(1, stationDensity / 3);
  const values = [
    avg("ghi_mean") / max("ghi_mean"),
    densityScore,
    avg("PVPI") / max("PVPI"),
    1 - avg("precip_annual") / max("precip_annual"),
    1 - avg("temp_std") / max("temp_std")
  ].map((value) => Number((Math.max(0, Math.min(1, value)) * 100).toFixed(1)));

  initChart(radarChartRef.value).setOption({
    radar: {
      center: ["50%", "52%"],
      radius: "66%",
      splitNumber: 4,
      axisName: { color: "#e6f4ff" },
      splitLine: { lineStyle: { color: "rgba(0, 212, 254, .2)" } },
      splitArea: { areaStyle: { color: ["rgba(0, 212, 254, .03)", "rgba(0, 212, 254, .08)"] } },
      axisLine: { lineStyle: { color: "rgba(0, 212, 254, .25)" } },
      indicator: [
        { name: "辐照", max: 100 },
        { name: "密度", max: 100 },
        { name: "PVPI", max: 100 },
        { name: "少雨", max: 100 },
        { name: "稳定", max: 100 }
      ]
    },
    series: [
      {
        type: "radar",
        data: [{ value: values, name: "全国均值" }],
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { color: "#00d4fe", width: 2, shadowBlur: 12, shadowColor: "rgba(0, 212, 254, .5)" },
        areaStyle: {
          color: new echarts.graphic.RadialGradient(0.5, 0.5, 0.8, [
            { offset: 0, color: "rgba(0, 212, 254, .28)" },
            { offset: 1, color: "rgba(0, 212, 254, .18)" }
          ])
        },
        itemStyle: { color: "#7df0ff", borderColor: "#fff", borderWidth: 1 }
      }
    ]
  });
};

const handleProvinceFocus = ({ province }) => {
  setSelectedProvince(province);
};

onMounted(() => {
  if (solar.loaded.value) nextTick(renderDashboardCharts);
});

watch(
  () => solar.loaded.value,
  async (ready) => {
    if (ready) {
      await nextTick();
      renderDashboardCharts();
    }
  }
);
</script>
