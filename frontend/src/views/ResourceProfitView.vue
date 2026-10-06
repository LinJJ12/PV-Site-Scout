<template>
  <main class="resource-profit-dashboard">
    <article class="panel chart-panel scatter-panel">
      <div class="panel-title">
        <span></span>资源收益联动散点<em>GHI × PVPI · 气泡=站点数 · 点击联动</em>
      </div>
      <div ref="scatterChartRef" class="chart"></div>
    </article>

    <article class="panel link-detail-panel">
      <div class="panel-title">
        <span></span>{{ detail ? `${detail.provinceName} · 省域详情` : "全国概览" }}
        <button v-if="detail" class="detail-reset" type="button" @click="selectProvince()">返回全国</button>
      </div>
      <div class="panel-body">
        <div class="link-detail">
        <template v-if="detail">
          <div class="detail-head">
            <strong>{{ detail.provinceName }}</strong>
            <span class="detail-badge" :style="{ background: detail.grade.color }">{{ detail.grade.name }}</span>
          </div>
          <div class="detail-rows">
            <div class="detail-row"><span>候选电站</span><strong>{{ detail.count }}</strong><i>座</i></div>
            <div class="detail-row"><span>可用面积</span><strong>{{ detail.totalArea }}</strong><i>km²</i></div>
            <div class="detail-row"><span>平均 PVPI</span><strong :style="{ color: detail.grade.color }">{{ detail.avgPvpi }}</strong></div>
            <div class="detail-row"><span>平均 GHI</span><strong>{{ detail.avgGhi }}</strong><i>kWh/m²</i></div>
            <div class="detail-row"><span>收益潜力指数</span><strong>{{ detail.profitIndex }}</strong></div>
          </div>
          <p class="detail-hint">点击散点图空白处或「返回全国」可重置联动</p>
        </template>
        <template v-else>
          <div class="detail-head">
            <strong>全国汇总</strong>
            <span class="detail-badge neutral">34 省域</span>
          </div>
          <div class="detail-rows">
            <div class="detail-row"><span>候选电站</span><strong>{{ national.count }}</strong><i>座</i></div>
            <div class="detail-row"><span>可用面积</span><strong>{{ national.totalArea }}</strong><i>km²</i></div>
            <div class="detail-row"><span>全国平均 PVPI</span><strong>{{ national.avgPvpi }}</strong></div>
            <div class="detail-row"><span>平均 PVPI 最高</span><strong>{{ national.topPvpi }}</strong><i>{{ national.topPvpiProvince }}</i></div>
            <div class="detail-row"><span>装机潜力最高</span><strong>{{ national.topArea }}</strong><i>{{ national.topAreaProvince }}</i></div>
          </div>
          <p class="detail-hint">点击左侧散点气泡，联动查看省域详情</p>
        </template>
        </div>
      </div>
    </article>

    <article class="panel chart-panel bar-panel">
      <div class="panel-title"><span></span>省域装机潜力排行<em>条形 · km² · 点击联动</em></div>
      <div ref="barChartRef" class="chart"></div>
    </article>

    <article class="panel chart-panel pie-panel">
      <div class="panel-title"><span></span>等级结构占比<em>饼图 / %</em></div>
      <div ref="pieChartRef" class="chart"></div>
    </article>

    <article class="panel chart-panel scroll-board-panel">
      <div class="panel-title"><span></span>综合评分 TOP10 候选电站<em>MCDM · 自动滚动</em></div>
      <div class="panel-body">
        <div class="board-wrap">
          <!-- 该榜固定展示全国 MCDM TOP10：资源收益页没有地图，不能被省份选择静默过滤 -->
          <AutoScrollTable
            grid-template="34px 1fr 64px 48px 56px 56px"
            :columns="[
              { key: 'rank', label: '排名', align: 'center' },
              { key: 'provinceName', label: '省份' },
              { key: 'area_km2', label: '面积 km²', align: 'right' },
              { key: 'ghi_mean', label: 'GHI', align: 'right' },
              { key: 'precip_annual', label: '降水 mm', align: 'right' },
              { key: 'PVPI', label: 'PVPI', align: 'right', colorKey: 'gradeColor' }
            ]"
            :rows="topSitesAll"
          />
        </div>
      </div>
    </article>

    <article class="panel chart-panel kline-panel">
      <div class="panel-title"><span></span>省域 PVPI 分布<em>箱线 · TOP10</em></div>
      <div ref="klineChartRef" class="chart"></div>
    </article>
  </main>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";

import AutoScrollTable from "@/components/AutoScrollTable.vue";
import { useCharts } from "@/composables/useCharts";
import { useSolarDataStore } from "@/stores/solarData";
import { formatNumber, quantile } from "@/utils/format";
import { gradeOf100 } from "@/utils/pvpi";
import { provinceNames } from "@/utils/provinces";

const solar = useSolarDataStore();
const { topSitesAll, statsData, stationData, suitability, gradeThresholds, loaded } = solar;
const { initChart } = useCharts();

const scatterChartRef = ref(null);
const barChartRef = ref(null);
const pieChartRef = ref(null);
const klineChartRef = ref(null);

/* 联动选中态：本页独立于态势页的地图省份选择，避免跨页干扰 */
const selectedProvince = ref("");

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

/* 每省聚合指标（详情卡与散点/条形共用） */
const provinceMetrics = computed(() => {
  const stats = statsData.value;
  const stations = stationData.value;
  if (!stats.length || !stations.length) return [];
  const stationGroups = groupStationsByProvince(stations);
  return stats.map((row) => {
    const rows = stationGroups.get(row.province) || [];
    const avg = (key) => (rows.length ? rows.reduce((sum, item) => sum + item[key], 0) / rows.length : 0);
    const avgPvpi = avg("PVPI");
    const avgGhi = avg("ghi_mean");
    return {
      province: row.province,
      provinceName: provinceNames[row.province] || row.province,
      count: rows.length,
      totalArea: row.Total_Area_km2,
      avgPvpi: Number(avgPvpi.toFixed(2)),
      avgGhi: Number(avgGhi.toFixed(2)),
      profitIndex: Number((avgPvpi * row.Total_Area_km2).toFixed(0))
    };
  }).filter((row) => row.count > 0);
});

const detail = computed(() => {
  if (!selectedProvince.value) return null;
  const hit = provinceMetrics.value.find((row) => row.provinceName === selectedProvince.value);
  if (!hit) return null;
  return {
    ...hit,
    count: formatNumber(hit.count),
    totalArea: formatNumber(hit.totalArea, 1),
    profitIndex: formatNumber(hit.profitIndex),
    grade: gradeOf100(hit.avgPvpi, gradeThresholds.value)
  };
});

const national = computed(() => {
  const rows = provinceMetrics.value;
  if (!rows.length) {
    return { count: "--", totalArea: "--", avgPvpi: "--", topPvpi: "--", topPvpiProvince: "--", topArea: "--", topAreaProvince: "--" };
  }
  const byPvpi = [...rows].sort((a, b) => b.avgPvpi - a.avgPvpi)[0];
  const byArea = [...rows].sort((a, b) => b.totalArea - a.totalArea)[0];
  const totalArea = rows.reduce((sum, row) => sum + row.totalArea, 0);
  const totalCount = rows.reduce((sum, row) => sum + row.count, 0);
  return {
    count: formatNumber(totalCount),
    totalArea: formatNumber(totalArea, 1),
    avgPvpi: Number((rows.reduce((sum, row) => sum + row.avgPvpi, 0) / rows.length).toFixed(2)),
    topPvpi: byPvpi.avgPvpi,
    topPvpiProvince: byPvpi.provinceName,
    topArea: formatNumber(byArea.totalArea, 1),
    topAreaProvince: byArea.provinceName
  };
});

const selectProvince = (name) => {
  // 同名再点一次视为取消选中（返回全国）
  selectedProvince.value = selectedProvince.value === name ? "" : name || "";
};

const renderScatter = () => {
  const data = provinceMetrics.value.map((row) => {
    const selected = row.provinceName === selectedProvince.value;
    return {
      name: row.provinceName,
      value: [row.avgGhi, row.avgPvpi, row.count, row.totalArea],
      itemStyle: selected
        ? {
            color: "rgba(0, 255, 163, .85)",
            borderColor: "#ffffff",
            borderWidth: 1.5,
            shadowBlur: 16,
            shadowColor: "rgba(0, 255, 163, .6)"
          }
        : {
            color: "rgba(0, 212, 254, .72)",
            borderColor: "#ffc53d",
            borderWidth: 1,
            shadowBlur: 12,
            shadowColor: "rgba(0, 212, 254, .42)"
          }
    };
  });
  initChart(scatterChartRef.value).setOption(
    {
      ...chartTheme,
      grid: { left: 48, right: 42, top: 40, bottom: 38 },
      tooltip: {
        trigger: "item",
        formatter(params) {
          const value = params.value;
          return `${params.name}<br/>平均 GHI：${value[0]}<br/>平均 PVPI：${value[1]}<br/>电站：${formatNumber(value[2])} 座<br/>面积：${Number(value[3]).toFixed(1)} km²`;
        }
      },
      xAxis: { type: "value", name: "GHI", nameGap: 8, nameTextStyle: { color: "#8fb3d9" } },
      yAxis: { type: "value", name: "PVPI", nameGap: 12, nameTextStyle: { color: "#8fb3d9", align: "left" } },
      series: [
        {
          type: "scatter",
          data,
          symbolSize: (value) => Math.max(10, Math.min(34, Math.sqrt(value[2]) * 1.3)),
          emphasis: { scale: 1.15 }
        }
      ]
    },
    true
  );
};

const renderBar = () => {
  const rows = [...provinceMetrics.value].sort((a, b) => b.totalArea - a.totalArea).slice(0, 10).reverse();
  initChart(barChartRef.value).setOption(
    {
      ...chartTheme,
      grid: { left: 58, right: 44, top: 22, bottom: 26 },
      xAxis: { type: "value" },
      yAxis: {
        type: "category",
        data: rows.map((row) => row.provinceName),
        axisLabel: {
          // axisLabel 仅 color 支持回调（fontWeight 不支持），选中省份用颜色区分
          color: (value) => (value === selectedProvince.value ? "#00ffa3" : "#8fb3d9")
        }
      },
      series: [
        {
          type: "bar",
          data: rows.map((row) => ({
            value: row.totalArea,
            itemStyle:
              row.provinceName === selectedProvince.value
                ? {
                    borderRadius: [0, 6, 6, 0],
                    color: "#00ffa3",
                    shadowBlur: 12,
                    shadowColor: "rgba(0, 255, 163, .5)"
                  }
                : {
                    borderRadius: [0, 6, 6, 0],
                    color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                      { offset: 0, color: "#0e4b8f" },
                      { offset: 0.72, color: "#00d4fe" },
                      { offset: 1, color: "#7df0ff" }
                    ]),
                    shadowBlur: 10,
                    shadowColor: "rgba(0, 212, 254, .28)"
                  }
          })),
          barWidth: 10,
          label: { show: true, position: "right", color: "#dffbff", fontSize: 11, formatter: (p) => Number(p.value).toFixed(1) }
        }
      ]
    },
    true
  );
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

const renderProvinceKline = () => {
  const stationGroups = groupStationsByProvince(stationData.value);
  const rows = statsData.value
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
  initChart(klineChartRef.value).setOption(
    {
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
    },
    true
  );
};

const renderCharts = () => {
  if (!statsData.value.length || !stationData.value.length) return;
  renderScatter();
  renderBar();
  renderSuitabilityPie();
  renderProvinceKline();

  // 联动入口：点散点气泡选中/切换省份，点空白处重置
  const scatter = initChart(scatterChartRef.value);
  scatter.off("click");
  scatter.off("zr:click");
  scatter.on("click", (params) => {
    if (params.componentType === "series") selectProvince(params.name);
  });
  scatter.getZr().on("click", (event) => {
    // 无命中目标时视为点击空白：重置联动
    if (!event.target) selectProvince("");
  });
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

/* 选中态变化 → 散点/条形联动重绘（详情卡为 computed 自动更新） */
watch(selectedProvince, () => {
  if (!loaded.value) return;
  renderScatter();
  renderBar();
});
</script>
