<template>
  <main class="realtime-dashboard">
    <section class="realtime-map-section">
      <div class="realtime-map-shell">
        <ThreeChinaMap
          v-if="chinaGeoJson"
          class="realtime-map-chart"
          :geo-json="chinaGeoJson"
          :stats="statsData"
          :stations="stationData"
          :province-names="provinceNames"
          :normalize-province-name="normalizeProvinceName"
          :result-point="lastClickLatLng"
          mode="realtime"
          @map-pick="handleMapPick"
        />
        <div class="map-hint">
          <span class="hint-icon">+</span>
          <span>点击省份聚焦，点击地图表面进行实时选址分析</span>
        </div>
      </div>
    </section>

    <section class="realtime-result-section">
      <article class="panel model-toggle-panel">
        <div class="panel-title"><span></span>预测模型选择</div>
        <div class="toggle-content">
          <div class="model-status">
            <span class="status-label">当前模型：</span>
            <strong class="status-value" :class="{ 'full-model': useFullModel }">{{ modelStatusText }}</strong>
          </div>
          <div class="toggle-buttons">
            <button class="toggle-btn" :class="{ active: !useFullModel }" @click="toggleModel('simple')">简化公式</button>
            <button class="toggle-btn full-btn" :class="{ active: useFullModel }" @click="toggleModel('full')">{{ fullModelButtonLabel }}</button>
          </div>
          <div class="model-hint">
            <span v-if="useFullModel">{{ fullModelHint }}</span>
            <span v-else>简化公式：基于真实太阳能数据快速估算</span>
          </div>
        </div>
      </article>

      <PanelCard v-if="historyRecords.length" title="选址记录" note="HISTORY · 本次会话" class="history-panel">
        <div class="history-list">
          <button
            class="history-row"
            v-for="(rec, index) in historyRecords"
            :key="rec.time + '-' + index"
            type="button"
            @click="rerunFromHistory(rec)"
          >
            <span class="h-time">{{ rec.time }}</span>
            <span class="h-coord">{{ rec.lat.toFixed(2) }}, {{ rec.lon.toFixed(2) }}</span>
            <strong class="h-pvpi" :style="{ color: rec.color }">{{ rec.pvpi.toFixed(2) }}</strong>
          </button>
        </div>
      </PanelCard>

      <article class="panel result-panel analysis-panel">
        <div class="panel-title">
          <span></span>{{ realtimeResult ? "选址分析结果" : isLoading ? "正在分析..." : errorMessage ? "分析状态" : "实时选址分析" }}
          <em v-if="realtimeResult" class="model-tag" :class="{ 'full-model': realtimeResult.model_type !== '简化公式' }">{{ realtimeResult.model_type }}</em>
        </div>
        <div class="loading-content" v-if="isLoading">
          <div class="loading-spinner"></div>
          <p>正在从 NASA POWER 获取点击位置气候数据...</p>
          <p>{{ loadingModelText }}</p>
          <p class="loading-hint">{{ useFullModel ? "首次请求可能需要 30-90 秒，请耐心等待" : "NASA 不可用或超时（30 秒）时自动回退本地真实站点数据" }}</p>
        </div>

        <div class="error-content" v-else-if="errorMessage">
          <div class="error-icon">×</div>
          <p>{{ errorMessage }}</p>
          <button class="retry-btn" @click="retryAnalysis">重试</button>
        </div>

        <div class="result-content" v-else-if="realtimeResult">
          <div class="result-hero" :style="{ '--score-color': realtimeResult.level_color }">
            <div ref="realtimeGaugeRef" class="result-gauge"></div>
            <div class="result-hero-meta">
              <div class="level-badge" :style="{ background: realtimeResult.level_color }">{{ realtimeResult.level }}</div>
              <div class="suitability-text"><span>适配度</span><strong :style="{ color: realtimeResult.level_color }">{{ realtimeResult.suitability }}</strong></div>
            </div>
          </div>

          <div class="compact-data-grid">
            <div class="data-card"><span class="data-label">经度</span><strong>{{ Number(realtimeResult.lon).toFixed(4) }}°</strong></div>
            <div class="data-card"><span class="data-label">纬度</span><strong>{{ Number(realtimeResult.lat).toFixed(4) }}°</strong></div>
            <div class="data-card"><span class="data-label">年均太阳辐射</span><strong>{{ realtimeResult.solar_data.ghi_annual_mean }} kWh/m2</strong></div>
            <div class="data-card"><span class="data-label">辐射标准差</span><strong>{{ realtimeResult.solar_data.ghi_annual_std }} kWh/m2</strong></div>
            <div class="data-card"><span class="data-label">年均温度</span><strong>{{ realtimeResult.solar_data.temp_annual_mean }} °C</strong></div>
            <div class="data-card"><span class="data-label">年降水量</span><strong>{{ realtimeResult.solar_data.precip_annual_mean }} mm</strong></div>
          </div>
          <div class="data-card source-card" v-if="realtimeResult.solar_data.source"><span class="data-label">数据来源</span><strong>{{ realtimeResult.solar_data.source }}</strong></div>
          <div class="data-card source-card" v-if="realtimeResult.inference_version"><span class="data-label">推理版本</span><strong>{{ realtimeResult.inference_version }}</strong></div>
          <div class="data-card source-card" v-if="realtimeResult.fallback_reason"><span class="data-label">回退原因</span><strong>{{ realtimeResult.fallback_reason }}</strong></div>
        </div>

        <div class="empty-content" v-else>
          <div class="empty-icon">+</div>
          <p>请在左侧地图上点击任意位置</p>
          <p>系统将获取真实太阳能数据</p>
          <p>并进行光伏电站选址适配度评估</p>
          <div class="mouse-coords" v-if="mouseCoords">
            <div class="coord-item"><span>经度</span><strong>{{ mouseCoords.lon.toFixed(4) }}°</strong></div>
            <div class="coord-item"><span>纬度</span><strong>{{ mouseCoords.lat.toFixed(4) }}°</strong></div>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";

import ThreeChinaMap from "@/components/ThreeChinaMap.vue";
import PanelCard from "@/components/PanelCard.vue";
import { useRealtimeStore } from "@/stores/realtime";
import { useSolarDataStore } from "@/stores/solarData";
import { normalizeProvinceName, provinceNames } from "@/utils/provinces";

const solar = useSolarDataStore();
const { chinaGeoJson, statsData, stationData, loaded } = solar;
const realtime = useRealtimeStore();

const {
  realtimeResult,
  historyRecords,
  isLoading,
  errorMessage,
  lastClickLatLng,
  mouseCoords,
  useFullModel,
  modelStatusText,
  fullModelButtonLabel,
  fullModelHint,
  loadingModelText,
  toggleModel,
  checkModelStatus,
  rerunFromHistory,
  handleMapPick,
  retryAnalysis
} = realtime;

const realtimeGaugeRef = ref(null);
let gaugeChart = null;

/* PVPI 仪表盘（实时预测口径 0~1，颜色随等级） */
const renderRealtimeGauge = (result) => {
  const el = realtimeGaugeRef.value;
  if (!el) return;
  // 结果区随 realtimeResult 销毁重建，旧 echarts 实例会挂在已卸载的 DOM 上，
  // 导致第二次预测起仪表盘空白；检测到 DOM 变化时必须重新 init
  if (gaugeChart && gaugeChart.getDom() !== el) {
    gaugeChart.dispose();
    gaugeChart = null;
  }
  if (!gaugeChart) gaugeChart = echarts.init(el, "bigscreen");
  const levelColor = result.level_color || "#00d4fe";
  gaugeChart.setOption({
    series: [
      {
        type: "gauge",
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 1,
        radius: "96%",
        center: ["50%", "56%"],
        progress: { show: true, width: 12, roundCap: true, itemStyle: { color: levelColor, shadowBlur: 10, shadowColor: levelColor } },
        axisLine: { roundCap: true, lineStyle: { width: 12, color: [[1, "rgba(143, 179, 217, .14)"]] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        anchor: { show: false },
        title: { show: true, offsetCenter: [0, "40%"], fontSize: 11, color: "#8fb3d9" },
        detail: {
          valueAnimation: true,
          fontSize: 30,
          fontFamily: "Bahnschrift, Segoe UI, sans-serif",
          fontWeight: 600,
          color: "#fff",
          offsetCenter: [0, "-4%"],
          formatter: (value) => Number(value).toFixed(2)
        },
        data: [{ value: Number(result.pvpi), name: "PVPI" }]
      }
    ]
  });
};

watch(realtimeResult, async (result) => {
  if (result) {
    await nextTick();
    renderRealtimeGauge(result);
  }
});

onBeforeUnmount(() => {
  if (gaugeChart) {
    gaugeChart.dispose();
    gaugeChart = null;
  }
});

onMounted(async () => {
  if (!loaded.value) {
    await solar.loadData().catch(() => {});
  }
  checkModelStatus();
});
</script>
