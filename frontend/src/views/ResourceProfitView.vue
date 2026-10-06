<template>
  <main class="resource-profit-dashboard">
    <article class="panel chart-panel">
      <div class="panel-title"><span></span>省域 PVPI 对比<em>折线 · TOP12</em></div>
      <div ref="trendChartRef" class="chart"></div>
    </article>

    <article class="panel chart-panel">
      <div class="panel-title"><span></span>省域装机潜力排行<em>条形 · km²</em></div>
      <div ref="barChartRef" class="chart"></div>
    </article>

    <article class="panel chart-panel">
      <div class="panel-title"><span></span>资源收益散点<em>GHI × PVPI</em></div>
      <div ref="scatterChartRef" class="chart"></div>
    </article>

    <article class="panel chart-panel">
      <div class="panel-title"><span></span>等级结构占比<em>饼图 / %</em></div>
      <div ref="pieChartRef" class="chart"></div>
    </article>

    <article class="panel chart-panel">
      <div class="panel-title"><span></span>省域 PVPI 分布<em>箱线 · TOP10</em></div>
      <div ref="klineChartRef" class="chart"></div>
    </article>

    <article class="panel table-panel">
      <div class="panel-title"><span></span>综合评分 TOP10 候选电站<em>MCDM · 真实样本</em></div>
      <div class="scrollable-panel" style="height: calc(100% - 34px);">
        <table>
          <thead>
            <tr><th>序号</th><th>省份</th><th>面积 km2</th><th>GHI</th><th>降水 mm</th><th>PVPI</th></tr>
          </thead>
          <tbody>
            <!-- 该表固定展示全国 MCDM TOP10：资源收益页没有地图，
                 不能被态势页/实时页的省份选择静默过滤 -->
            <tr v-for="(row, index) in topSitesAll" :key="row.index">
              <td>{{ index + 1 }}</td><td>{{ row.provinceName }}</td><td>{{ row.area_km2 }}</td><td>{{ row.ghi_mean }}</td><td>{{ row.precip_annual }}</td><td>{{ row.PVPI }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </main>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";

import { useCharts } from "@/composables/useCharts";
import { useSolarDataStore } from "@/stores/solarData";
import { formatNumber, quantile } from "@/utils/format";
import { provinceNames } from "@/utils/provinces";

const solar = useSolarDataStore();
const { topSitesAll, statsData, stationData, suitability, loaded } = solar;
const { initChart } = useCharts();

const trendChartRef = ref(null);
const barChartRef = ref(null);
const scatterChartRef = ref(null);
const pieChartRef = ref(null);
const klineChartRef = ref(null);

const chartTheme = {
  textStyle: { color: "#8fb3d9" },
  grid: { left: 46, right: 28, top: 30, bottom: 32 }
};

const groupStationsByProvince = (stations) =>
  stations.reduce((groups, row) => {
    if (!groups.has(row.province)) groups.set(row.province, []);
    groups.get(row.province).push(row);
    return groups;
  }, new Map());

const renderProvincePvpi = (stats, stations) => {
  const stationGroups = groupStationsByProvince(stations);
  const provincePvpi = [...stats]
    .map((row) => {
      const provinceStations = stationGroups.get(row.province) || [];
      const avgPvpi = provinceStations.reduce((sum, station) => sum + station.PVPI, 0) / provinceStations.length;
      return {
        province: provinceNames[row.province] || row.province,
        avgPvpi: Number(avgPvpi.toFixed(2))
      };
    })
    .filter((row) => Number.isFinite(row.avgPvpi))
    .sort((a, b) => b.avgPvpi - a.avgPvpi)
    .slice(0, 12)
    .reverse();
  initChart(trendChartRef.value).setOption({
    ...chartTheme,
    xAxis: { type: "category", data: provincePvpi.map((row) => row.province) },
    yAxis: { type: "value" },
    series: [
      {
        type: "line",
        data: provincePvpi.map((row) => row.avgPvpi),
        symbol: "circle",
        symbolSize: 8,
        smooth: true,
        lineStyle: { color: "#00d4fe", width: 3, shadowBlur: 12, shadowColor: "rgba(0, 212, 254, .5)" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(0, 212, 254, .30)" },
            { offset: 1, color: "rgba(0, 212, 254, .02)" }
          ])
        },
        itemStyle: {
          color: "#ffc53d",
          borderColor: "#ffffff",
          borderWidth: 1,
          shadowBlur: 12,
          shadowColor: "rgba(255, 197, 61, .38)"
        },
        emphasis: { itemStyle: { shadowBlur: 18, shadowColor: "rgba(255, 197, 61, .35)" } }
      }
    ]
  });
};

const renderBar = (stats) => {
  const top = [...stats].sort((a, b) => b.Total_Area_km2 - a.Total_Area_km2).slice(0, 10).reverse();
  initChart(barChartRef.value).setOption({
    ...chartTheme,
    grid: { left: 58, right: 30, top: 22, bottom: 26 },
    xAxis: { type: "value" },
    yAxis: {
      type: "category",
      data: top.map((row) => provinceNames[row.province] || row.province)
    },
    series: [
      {
        type: "bar",
        data: top.map((row) => row.Total_Area_km2),
        barWidth: 10,
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: "#0e4b8f" },
            { offset: 0.72, color: "#00d4fe" },
            { offset: 1, color: "#7df0ff" }
          ]),
          shadowBlur: 10,
          shadowColor: "rgba(0, 212, 254, .28)"
        },
        label: { show: true, position: "right", color: "#dffbff", fontSize: 11, formatter: (p) => Number(p.value).toFixed(1) }
      }
    ]
  });
};

const renderResourceScatter = (stats, stations) => {
  const stationGroups = groupStationsByProvince(stations);
  const data = stats
    .map((row) => {
      const rows = stationGroups.get(row.province) || [];
      if (!rows.length) return null;
      const avg = (key) => rows.reduce((sum, item) => sum + item[key], 0) / rows.length;
      return [
        Number(avg("ghi_mean").toFixed(2)),
        Number(avg("PVPI").toFixed(2)),
        row.Count,
        provinceNames[row.province] || row.province,
        Number(row.Total_Area_km2.toFixed(1))
      ];
    })
    .filter(Boolean);
  initChart(scatterChartRef.value).setOption({
    ...chartTheme,
    grid: { left: 48, right: 42, top: 58, bottom: 38 },
    tooltip: {
      trigger: "item",
      formatter(params) {
        const value = params.value;
        return `${value[3]}<br/>平均 GHI：${value[0]}<br/>平均 PVPI：${value[1]}<br/>电站：${formatNumber(value[2])} 座<br/>面积：${value[4]} km²`;
      }
    },
    xAxis: { type: "value", name: "GHI", nameGap: 8, nameTextStyle: { color: "#8fb3d9" } },
    yAxis: { type: "value", name: "PVPI", nameGap: 12, nameTextStyle: { color: "#8fb3d9", align: "left" } },
    series: [
      {
        type: "scatter",
        data,
        symbolSize: (value) => Math.max(8, Math.min(30, Math.sqrt(value[2]) * 1.2)),
        itemStyle: {
          color: "rgba(0, 212, 254, .72)",
          borderColor: "#ffc53d",
          borderWidth: 1,
          shadowBlur: 12,
          shadowColor: "rgba(0, 212, 254, .42)"
        }
      }
    ]
  });
};

const renderSuitabilityPie = () => {
  initChart(pieChartRef.value).setOption({
    tooltip: { trigger: "item" },
    legend: {
      bottom: 8,
      itemWidth: 10,
      itemHeight: 10
    },
    series: [
      {
        type: "pie",
        radius: ["48%", "72%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: true,
        label: { color: "#e6f4ff", formatter: "{b}\n{d}%" },
        labelLine: { lineStyle: { color: "rgba(0, 212, 254, .45)" } },
        data: suitability.value.map((item) => ({
          name: item.name,
          value: Number(String(item.count).replace(/,/g, "")),
          itemStyle: { color: item.color }
        }))
      }
    ]
  });
};

const renderProvinceKline = (stats, stations) => {
  const stationGroups = groupStationsByProvince(stations);
  const rows = stats
    .map((row) => {
      const values = (stationGroups.get(row.province) || []).map((item) => item.PVPI).filter(Number.isFinite);
      if (values.length < 4) return null;
      return {
        province: provinceNames[row.province] || row.province,
        avg: values.reduce((sum, value) => sum + value, 0) / values.length,
        candle: [
          Number(quantile(values, 0.25).toFixed(2)),
          Number(quantile(values, 0.75).toFixed(2)),
          Number(Math.min(...values).toFixed(2)),
          Number(Math.max(...values).toFixed(2))
        ]
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 10)
    .reverse();
  const allValues = rows.flatMap((row) => row.candle);
  const yMin = Math.max(0, Math.floor(Math.min(...allValues) / 5) * 5);
  const yMax = Math.ceil(Math.max(...allValues) / 5) * 5;
  initChart(klineChartRef.value).setOption({
    ...chartTheme,
    grid: { left: 42, right: 18, top: 26, bottom: 36 },
    tooltip: {
      trigger: "axis",
      formatter(params) {
        const item = params[0];
        const value = item.value;
        return `${item.name}<br/>Q1：${value[1]}<br/>Q3：${value[2]}<br/>最低：${value[3]}<br/>最高：${value[4]}`;
      }
    },
    xAxis: { type: "category", data: rows.map((row) => row.province) },
    yAxis: { type: "value", min: yMin, max: yMax },
    series: [
      {
        type: "candlestick",
        data: rows.map((row) => row.candle),
        itemStyle: {
          color: "rgba(0, 212, 254, .72)",
          color0: "rgba(255, 197, 61, .72)",
          borderColor: "#00d4fe",
          borderColor0: "#ffc53d"
        }
      }
    ]
  });
};

const renderCharts = () => {
  const stats = statsData.value;
  const stations = stationData.value;
  if (!stats.length || !stations.length) return;
  renderProvincePvpi(stats, stations);
  renderBar(stats);
  renderResourceScatter(stats, stations);
  renderSuitabilityPie();
  renderProvinceKline(stats, stations);
};

onMounted(() => {
  if (loaded.value) nextTick(renderCharts);
});

watch(
  () => loaded.value,
  async (ready) => {
    if (ready) {
      await nextTick();
      renderCharts();
    }
  }
);
</script>
