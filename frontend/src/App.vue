<template>
  <div ref="screenRef" class="screen" :class="{ 'data-load-error': dataLoadError }">
    <div class="scanline"></div>
    <div class="frame-corner tl"></div><div class="frame-corner tr"></div>
    <div class="frame-corner bl"></div><div class="frame-corner br"></div>
    <transition name="boot-fade">
      <div class="boot-loading" v-if="booting">
        <div class="boot-mark"></div>
        <div class="boot-bar"><b></b></div>
        <p>正在接入真实选址数据</p>
      </div>
    </transition>
    <header class="screen-header">
      <div class="brand">
        <span class="brand-mark"></span>
        <div>
          <h1>光伏电站智能选址数据可视化大屏</h1>
          <small>PV SITE INTELLIGENCE · REAL DATA EDITION</small>
        </div>
      </div>
      <nav class="tabs" aria-label="数据视图">
        <button class="tab" :class="{ active: activeTab === 'dashboard' }" @click="activeTab = 'dashboard'">选址态势</button>
        <button class="tab" :class="{ active: activeTab === 'resourceProfit' }" @click="activeTab = 'resourceProfit'">资源收益评估</button>
        <button class="tab" :class="{ active: activeTab === 'realtime' }" @click="activeTab = 'realtime'">实时选址</button>
      </nav>
      <div class="timebox">
        <strong>{{ currentTime }}</strong>
        <span>{{ currentDate }}</span>
      </div>
    </header>

    <main class="dashboard" v-if="activeTab === 'dashboard'">
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
            @map-pick="handleThreeMapPick"
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

    <main class="resource-profit-dashboard" v-else-if="activeTab === 'resourceProfit'">
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
                   若沿用 topSites 会被态势页/实时页的省份选择静默过滤成空表 -->
              <tr v-for="(row, index) in topSitesAll" :key="row.index">
                <td>{{ index + 1 }}</td><td>{{ row.provinceName }}</td><td>{{ row.area_km2 }}</td><td>{{ row.ghi_mean }}</td><td>{{ row.precip_annual }}</td><td>{{ row.PVPI }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </main>

    <main class="realtime-dashboard" v-else-if="activeTab === 'realtime'">
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
            @province-focus="handleProvinceFocus"
            @map-pick="handleThreeMapPick"
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
  </div>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";
import ThreeChinaMap from "./components/ThreeChinaMap.vue";
import PanelCard from "./components/PanelCard.vue";
import KpiStrip from "./components/KpiStrip.vue";
import RankBars from "./components/RankBars.vue";
import AutoScrollTable from "./components/AutoScrollTable.vue";
import { useFitScreen } from "./composables/useFitScreen.js";
import "./theme/bigscreen.js";

const activeTab = ref("dashboard");
const screenRef = ref(null);
useFitScreen(screenRef);
const realtimeResult = ref(null);
const historyRecords = ref([]);
const realtimeGaugeRef = ref(null);
const booting = ref(true);
let gaugeChart = null;
const isLoading = ref(false);
const errorMessage = ref("");
const lastClickLatLng = ref(null);
const mouseCoords = ref(null);
const useFullModel = ref(false);
const torchAvailable = ref(false);
const modelStatusText = ref("简化公式");
// 实时选址请求的竞态保护
let requestSeq = 0;
let pendingAbort = null;
// 用户是否手动切换过预测模型（切换后不再被后端状态自动覆盖）
const modelChoiceTouched = ref(false);

const fullModelButtonLabel = computed(() => (torchAvailable.value ? "GAT+GBDT" : "GBDT模型"));
const fullModelHint = computed(() =>
  torchAvailable.value
    ? "完整模型：使用图神经网络和梯度提升树进行预测"
    : "完整模型：当前环境未启用 torch，使用已训练的 GBDT 运行包推理"
);
const loadingModelText = computed(() =>
  useFullModel.value
    ? torchAvailable.value
      ? "正在运行 GAT+GBDT 模型计算 PVPI..."
      : "正在运行 GBDT 模型计算 PVPI..."
    : "正在运行简化公式计算 PVPI..."
);

const provinceNames = {
  anhui: "安徽",
  beijing: "北京",
  chongqing: "重庆",
  fujian: "福建",
  gansu: "甘肃",
  guangdong: "广东",
  guangxi: "广西",
  guizhou: "贵州",
  hainan: "海南",
  hebei: "河北",
  heilongjiang: "黑龙江",
  henan: "河南",
  hong_kong: "香港",
  hubei: "湖北",
  hunan: "湖南",
  Inner_Mongolia: "内蒙古",
  jiangsu: "江苏",
  jiangxi: "江西",
  jilin: "吉林",
  liaoning: "辽宁",
  macao: "澳门",
  ningxia: "宁夏",
  qinghai: "青海",
  shaanxi: "陕西",
  shandong: "山东",
  shanghai: "上海",
  shanxi: "山西",
  sichuan: "四川",
  taiwan: "台湾",
  tianjin: "天津",
  xinjiang: "新疆",
  xizang: "西藏",
  yunnan: "云南",
  zhejiang: "浙江"
};

const normalizeProvinceName = (name = "") =>
  String(name)
    .replace("新疆维吾尔自治区", "新疆")
    .replace("广西壮族自治区", "广西")
    .replace("宁夏回族自治区", "宁夏")
    .replace("西藏自治区", "西藏")
    .replace("内蒙古自治区", "内蒙古")
    .replace("香港特别行政区", "香港")
    .replace("澳门特别行政区", "澳门")
    .replace(/[省市]/g, "");

const currentTime = ref("--:--:--");
const currentDate = ref("");
const suitability = ref([]);
const topSitesAll = ref([]);
const rankItemsAll = ref([]);
const provincePvpiMap = ref({});
const selectedProvince = ref("");
const kpiItems = ref([]);
const gradeThresholds = ref([0, 0, 0]);
const topSites = computed(() =>
  selectedProvince.value ? topSitesAll.value.filter((row) => row.provinceName === selectedProvince.value) : topSitesAll.value
);
const rankItems = computed(() => {
  if (selectedProvince.value) {
    const hit = provincePvpiMap.value[selectedProvince.value];
    return Number.isFinite(Number(hit)) ? [{ name: selectedProvince.value, value: Number(hit) }] : [];
  }
  return rankItemsAll.value;
});
const resourceRows = ref([]);
const profitRows = ref([]);
const dataLoadError = ref("");
const summary = ref({
  avgPvpi: "--",
  maxGhi: "--",
  totalArea: "--",
  totalStations: "--"
});
const statsData = ref([]);
const stationData = ref([]);
const chinaGeoJson = ref(null);

const trendChartRef = ref(null);
const radarChartRef = ref(null);
const barChartRef = ref(null);
const suitabilityPieRef = ref(null);
const scatterChartRef = ref(null);
const pieChartRef = ref(null);
const klineChartRef = ref(null);
const charts = [];
let clockTimer;

const chartTheme = {
  textStyle: { color: "#8fb3d9" },
  grid: { left: 46, right: 28, top: 30, bottom: 32 }
};

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

const chartRefs = () => charts.filter(Boolean);

const formatNumber = (value, digits = 0) =>
  Number(value || 0).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  });

const normalizeSolarData = (row, source) => ({
  ghi_annual_mean: Number(row.ghi_mean || row.ghi_annual_mean || 0),
  ghi_annual_std: Number(row.ghi_std || row.ghi_annual_std || 0),
  temp_annual_mean: Number(row.temp_mean || row.temp_annual_mean || 0),
  temp_annual_std: Number(row.temp_std || row.temp_annual_std || 0),
  precip_annual_mean: Number(row.precip_annual || row.precip_annual_mean || 0),
  source
});

const calculateSimplePvpi = (solarData) => {
  const ghi = Number(solarData.ghi_annual_mean || 0);
  const temp = Number(solarData.temp_annual_mean || 0);
  const tempStd = Number(solarData.temp_annual_std || 0);
  const precip = Number(solarData.precip_annual_mean || 0);
  const ghiScore = Math.min(ghi / 6, 1);
  const tempScore = Math.min(Math.max((25 - Math.abs(temp - 15)) / 25, 0), 1);
  const precipScore = Math.min(Math.max((1000 - precip) / 1000, 0), 1);
  const stabilityScore = Math.min(Math.max((10 - tempStd) / 10, 0), 1);
  return Math.max(0.1, Math.min(0.95, Number((0.3 * ghiScore + 0.2 * tempScore + 0.25 * precipScore + 0.25 * stabilityScore).toFixed(4))));
};

const classifyPvpi = (pvpi) => {
  if (pvpi >= 0.8) return { level: "优选区", level_color: "#00ffa3", suitability: "极高" };
  if (pvpi >= 0.6) return { level: "适宜区", level_color: "#00d4fe", suitability: "高" };
  if (pvpi >= 0.4) return { level: "备选区", level_color: "#ffc53d", suitability: "中等" };
  return { level: "约束区", level_color: "#ff6b6b", suitability: "低" };
};

/* 静态数据 PVPI 为 0~100 分，按与首页占比一致的分位阈值分级（0~0.95 的实时预测走 classifyPvpi） */
const gradeOf100 = (value) => {
  const [t0, t1, t2] = gradeThresholds.value;
  if (value >= t0) return { name: "优选区", color: "#00ffa3" };
  if (value >= t1) return { name: "适宜区", color: "#00d4fe" };
  if (value >= t2) return { name: "备选区", color: "#ffc53d" };
  return { name: "约束区", color: "#ff6b6b" };
};

const buildLocalPrediction = (lat, lon, reason = "") => {
  if (!stationData.value.length) {
    throw new Error("本地真实电站数据尚未加载");
  }
  const nearest = stationData.value.reduce((best, row) => {
    const distance = Math.hypot(Number(row.lon) - lon, Number(row.lat) - lat);
    return !best || distance < best.distance ? { row, distance } : best;
  }, null);
  const solarData = normalizeSolarData(
    nearest.row,
    `nearest real station: ${provinceNames[nearest.row.province] || nearest.row.province} #${nearest.row.index}`
  );
  const pvpi = calculateSimplePvpi(solarData);
  const classification = classifyPvpi(pvpi);
  return {
    lat,
    lon,
    pvpi,
    pvssi: pvpi,
    ...classification,
    model_type: "简化公式（本地真实数据兜底）",
    fallback_reason: reason,
    solar_data: {
      ghi_annual_mean: Number(solarData.ghi_annual_mean.toFixed(2)),
      ghi_annual_std: Number(solarData.ghi_annual_std.toFixed(2)),
      temp_annual_mean: Number(solarData.temp_annual_mean.toFixed(2)),
      temp_annual_std: Number(solarData.temp_annual_std.toFixed(2)),
      precip_annual_mean: Number(Math.max(0, solarData.precip_annual_mean).toFixed(2)),
      source: solarData.source
    }
  };
};

const parseCsv = (text) => {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines.shift().split(",");
  return lines.map((line) => {
    const cols = line.split(",");
    return headers.reduce((row, key, index) => {
      const value = cols[index];
      const numeric = Number(value);
      row[key] = Number.isFinite(numeric) && value !== "" ? numeric : value;
      return row;
    }, {});
  });
};

const tick = () => {
  const now = new Date();
  currentTime.value = now.toLocaleTimeString("zh-CN", { hour12: false });
  currentDate.value = now.toLocaleDateString("zh-CN", {
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  });
};

const loadData = async () => {
  dataLoadError.value = "";

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
    await nextTick();
    renderActiveCharts();
  } catch (error) {
    dataLoadError.value = error.message || "真实数据加载失败";
    suitability.value = [];
    topSitesAll.value = [];
    kpiItems.value = [];
    rankItemsAll.value = [];
    provincePvpiMap.value = {};
    selectedProvince.value = "";
    resourceRows.value = [];
    profitRows.value = [];
    summary.value = {
      avgPvpi: "--",
      maxGhi: "--",
      totalArea: "--",
      totalStations: "--"
    };
    statsData.value = [];
    stationData.value = [];
    chartRefs().forEach((chart) => chart.dispose());
    charts.length = 0;
    throw error;
  }
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
    gradeColor: gradeOf100(row.PVPI).color,
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

const initChart = (chartRef) => {
  const chart = echarts.init(chartRef.value, "bigscreen");
  charts.push(chart);
  return chart;
};

const renderCharts = (stats, stations) => {
  chartRefs().forEach((chart) => chart.dispose());
  charts.length = 0;
  renderRadar(stats, stations);
};

const renderActiveCharts = () => {
  const stats = statsData.value;
  const stations = stationData.value;
  if (!stats.length || !stations.length) return;

  chartRefs().forEach((chart) => chart.dispose());
  charts.length = 0;

  if (activeTab.value === "dashboard") {
    renderDashboardSuitabilityPie();
    renderRadar(stats, stations);
  } else if (activeTab.value === "resourceProfit") {
    renderProvincePvpi(stats, stations);
    renderBar(stats);
    renderResourceScatter(stats, stations);
    renderSuitabilityPie();
    renderProvinceKline(stats, stations);
  }
};

const renderProvincePvpi = (stats, stations) => {
  const stationGroups = stations.reduce((groups, row) => {
    if (!groups.has(row.province)) groups.set(row.province, []);
    groups.get(row.province).push(row);
    return groups;
  }, new Map());
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
  const chart = initChart(trendChartRef);
  chart.setOption({
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
  const chart = initChart(barChartRef);
  chart.setOption({
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

const renderDashboardSuitabilityPie = () => {
  const chart = initChart(suitabilityPieRef);
  chart.setOption({
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
        data: suitability.value.map((item) => ({
          name: item.name,
          value: Number(String(item.count).replace(/,/g, "")),
          itemStyle: { color: item.color }
        }))
      }
    ]
  });
};

const renderResourceScatter = (stats, stations) => {
  const stationGroups = stations.reduce((groups, row) => {
    if (!groups.has(row.province)) groups.set(row.province, []);
    groups.get(row.province).push(row);
    return groups;
  }, new Map());
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
  const chart = initChart(scatterChartRef);
  chart.setOption({
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
  const chart = initChart(pieChartRef);
  chart.setOption({
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

const quantile = (values, q) => {
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  return sorted[base + 1] === undefined ? sorted[base] : sorted[base] + rest * (sorted[base + 1] - sorted[base]);
};

const renderProvinceKline = (stats, stations) => {
  const stationGroups = stations.reduce((groups, row) => {
    if (!groups.has(row.province)) groups.set(row.province, []);
    groups.get(row.province).push(row);
    return groups;
  }, new Map());
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
  const chart = initChart(klineChartRef);
  chart.setOption({
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

  const chart = initChart(radarChartRef);
  chart.setOption({
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

const handleResize = () => {
  chartRefs().forEach((chart) => chart.resize());
};

const API_BASES = [
  typeof window !== "undefined" ? window.location.origin : "",
  "http://127.0.0.1:5000",
  "http://localhost:5000"
].filter(Boolean);

const modelLabel = (loaded, torchAvailable = false) => {
  if (!loaded) return "简化公式";
  return torchAvailable ? "GAT+GBDT集成模型" : "GBDT模型";
};

const fetchFromApi = async (path, options = {}) => {
  let lastError = null;
  for (const base of API_BASES) {
    try {
      const response = await fetch(`${base}${path}`, {
        ...options,
        signal: options.signal || AbortSignal.timeout(15000)
      });
      if (!response.ok) {
        throw new Error(`接口响应异常：${response.status}`);
      }
      return response;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("后端服务不可用");
};

/* 本次会话的选址勘察记录（内存态，最多保留 8 条） */
const pushHistory = (lat, lon, result) => {
  historyRecords.value.unshift({
    time: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
    lat: Number(lat),
    lon: Number(lon),
    pvpi: Number(result.pvpi),
    level: result.level,
    color: result.level_color || "#00d4fe"
  });
  if (historyRecords.value.length > 8) historyRecords.value.pop();
};

const rerunFromHistory = (rec) => {
  lastClickLatLng.value = { lat: rec.lat, lon: rec.lon };
  fetchPrediction(rec.lat, rec.lon);
};

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
  if (result && activeTab.value === "realtime") {
    await nextTick();
    renderRealtimeGauge(result);
  }
});

const fetchPrediction = async (lat, lon) => {
  // 竞态保护：连续点击时旧请求的结果直接丢弃
  const seq = ++requestSeq;
  if (pendingAbort) pendingAbort.abort();
  const controller = new AbortController();
  pendingAbort = controller;
  isLoading.value = true;
  errorMessage.value = "";
  realtimeResult.value = null;

  const timeoutMs = useFullModel.value ? 120000 : 30000;
  const makeSignal = () => {
    const timeoutSignal = AbortSignal.timeout(timeoutMs);
    return typeof AbortSignal.any === "function"
      ? AbortSignal.any([timeoutSignal, controller.signal])
      : timeoutSignal;
  };

  try {
    const mode = useFullModel.value ? "full" : "simple";
    let lastError = null;

    for (const base of API_BASES) {
      if (controller.signal.aborted) return;
      try {
        const response = await fetch(
          `${base}/api/predict?lat=${lat}&lon=${lon}&mode=${mode}`,
          { signal: makeSignal() }
        );
        let result = null;
        try {
          result = await response.json();
        } catch {
          result = null;
        }
        if (!response.ok || result?.error || !result) {
          throw new Error(result?.error || (result ? `接口响应异常：${response.status}` : "无法解析响应数据"));
        }
        const source = String(result?.solar_data?.source || "");
        if (useFullModel.value) {
          if (!source.includes("NASA")) {
            throw new Error("未获取到 NASA 气候数据，请检查网络后重试");
          }
          if (result.inference_version !== "v3-nasa-gat-reg") {
            throw new Error("后端推理版本过旧，请重启 backend（uv run python main.py）后重试");
          }
          if (Number(result.pvpi) >= 0.999) {
            throw new Error("PVPI 结果异常（恒为 1.00），请确认已启动最新版 backend");
          }
        }
        if (seq !== requestSeq) return;
        realtimeResult.value = result;
        pushHistory(lat, lon, result);
        updateMapMarker(lat, lon, result.pvpi);
        return;
      } catch (error) {
        if (controller.signal.aborted) return;
        lastError = error;
      }
    }

    if (useFullModel.value) {
      if (seq !== requestSeq) return;
      throw lastError || new Error("完整模型后端不可用，请确认已启动：cd backend && uv run python main.py");
    }

    if (seq !== requestSeq) return;
    const fallback = buildLocalPrediction(lat, lon, lastError?.message || "后端服务不可用");
    realtimeResult.value = fallback;
    pushHistory(lat, lon, fallback);
    updateMapMarker(lat, lon, fallback.pvpi);

  } catch (error) {
    if (seq === requestSeq) {
      errorMessage.value = error.message || "获取真实数据失败";
    }
  } finally {
    if (seq === requestSeq) {
      isLoading.value = false;
    }
  }
};

const toggleModel = async (mode) => {
  errorMessage.value = "";
  modelChoiceTouched.value = true;
  try {
    const response = await fetchFromApi("/api/toggle_mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode })
    });
    const result = await response.json();
    if (result.success) {
      useFullModel.value = mode === "full";
      if (typeof result.torch_available === "boolean") {
        torchAvailable.value = result.torch_available;
      }
      modelStatusText.value = result.model_type || modelLabel(useFullModel.value, torchAvailable.value);
    }
  } catch (error) {
    useFullModel.value = mode === "full";
    modelStatusText.value = modelLabel(useFullModel.value, torchAvailable.value);
  }
  if (lastClickLatLng.value) {
    fetchPrediction(lastClickLatLng.value.lat, lastClickLatLng.value.lon);
  }
};

const checkModelStatus = async () => {
  try {
    const response = await fetchFromApi("/api/status");
    const result = await response.json();
    const modelLoaded = Boolean(result.model_loaded);
    torchAvailable.value = Boolean(result.torch_available);
    // 仅在用户尚未手动切换过模型时同步后端状态，避免覆盖用户选择
    if (!modelChoiceTouched.value) {
      useFullModel.value = modelLoaded;
      modelStatusText.value = result.model_type || modelLabel(modelLoaded, torchAvailable.value);
    }
  } catch (error) {
    if (modelChoiceTouched.value) return;
    useFullModel.value = false;
    torchAvailable.value = false;
    modelStatusText.value = "简化公式";
  }
};

const updateMapMarker = (lat, lon, pvpi) => {
  void lat;
  void lon;
  void pvpi;
};

const handleProvinceFocus = ({ province }) => {
  mouseCoords.value = null;
  selectedProvince.value = province || "";
  if (province) {
    errorMessage.value = "";
  }
};

const handleThreeMapPick = ({ lat, lon }) => {
  mouseCoords.value = { lon, lat };
  lastClickLatLng.value = { lat, lon };
  if (activeTab.value === "realtime") {
    fetchPrediction(lat, lon);
  }
};

const retryAnalysis = () => {
  if (lastClickLatLng.value) {
    fetchPrediction(lastClickLatLng.value.lat, lastClickLatLng.value.lon);
  }
};

const handleRealtimeResize = () => {
  return;
};

watch(activeTab, async (newTab) => {
  if (newTab !== "realtime" && gaugeChart) {
    gaugeChart.dispose();
    gaugeChart = null;
  }
  if (newTab === "realtime") {
    await nextTick();
    if (!statsData.value.length || !stationData.value.length) {
      await loadData();
    }
    checkModelStatus();
  } else {
    await nextTick();
    if (!statsData.value.length || !stationData.value.length) {
      await loadData();
    } else {
      renderActiveCharts();
    }
  }
});

onMounted(async () => {
  tick();
  clockTimer = window.setInterval(tick, 1000);
  try {
    await loadChinaMap();
  } catch (error) {
    // 地图边界全部加载失败时不能卡住启动流程：继续加载数据，
    // 地图区域会因 chinaGeoJson 为空而不渲染，dataLoadError 展示错误提示
    console.error("中国地图边界加载失败", error);
  }
  try {
    await loadData();
  } catch (error) {
    // dataLoadError 已在 loadData 内写入并展示，这里避免未处理的 Promise 拒绝
  } finally {
    booting.value = false;
  }
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.clearInterval(clockTimer);
  window.removeEventListener("resize", handleResize);
  chartRefs().forEach((chart) => chart.dispose());
  charts.length = 0;
  if (gaugeChart) {
    gaugeChart.dispose();
    gaugeChart = null;
  }
});
</script>

