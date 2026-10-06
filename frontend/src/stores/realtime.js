/* 实时选址状态（单例 composable）：预测请求、模型切换、会话内历史记录。
   切换视图不会丢失未完成的请求与历史，与旧版单文件行为一致。 */

import { computed, ref } from "vue";

import { fetchFromApi, modelLabel } from "@/api/client";
import { fetchNasaSolar } from "@/api/nasa";
import { useSolarDataStore } from "@/stores/solarData";
import { calculateSimplePvpi, classifyPvpi } from "@/utils/pvpi";
import { provinceNames } from "@/utils/provinces";

const realtimeResult = ref(null);
const historyRecords = ref([]);
const isLoading = ref(false);
const errorMessage = ref("");
const lastClickLatLng = ref(null);
const mouseCoords = ref(null);
const useFullModel = ref(false);
const torchAvailable = ref(false);
const modelStatusText = ref("简化公式");
/* 用户是否手动切换过预测模型（切换后不再被后端状态自动覆盖） */
const modelChoiceTouched = ref(false);

/* 实时选址请求的竞态保护 */
let requestSeq = 0;
let pendingAbort = null;

const INFERENCE_VERSION = "v3-nasa-gat-reg";

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

const normalizeSolarData = (row, source) => ({
  ghi_annual_mean: Number(row.ghi_mean || row.ghi_annual_mean || 0),
  ghi_annual_std: Number(row.ghi_std || row.ghi_annual_std || 0),
  temp_annual_mean: Number(row.temp_mean || row.temp_annual_mean || 0),
  temp_annual_std: Number(row.temp_std || row.temp_annual_std || 0),
  precip_annual_mean: Number(row.precip_annual || row.precip_annual_mean || 0),
  source
});

/* 后端完全不可达时的本地兜底：用最近真实站点数据按简化公式估算 */
const buildLocalPrediction = (lat, lon, reason = "") => {
  const { stationData } = useSolarDataStore();
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

/* 简化公式（纯前端）：直连 NASA POWER 取数 → 本地公式计算，不经过后端。
   NASA 不可用时回退到最近真实站点数据兜底。 */
const predictSimpleLocally = async (lat, lon, signal) => {
  const solarData = await fetchNasaSolar(lat, lon, { signal });
  const pvpi = calculateSimplePvpi(solarData);
  return {
    lat,
    lon,
    pvpi,
    pvssi: pvpi,
    ...classifyPvpi(pvpi),
    model_type: "简化公式",
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

  const bases = [window.location.origin, "http://127.0.0.1:5000", "http://localhost:5000"].filter(Boolean);

  try {
    /* 简化公式：纯前端直连 NASA POWER，后端只服务完整模型推理 */
    if (!useFullModel.value) {
      try {
        const result = await predictSimpleLocally(lat, lon, makeSignal());
        if (seq !== requestSeq) return;
        realtimeResult.value = result;
        pushHistory(lat, lon, result);
      } catch (error) {
        if (controller.signal.aborted || seq !== requestSeq) return;
        if (error.name === "AbortError") return;
        const fallback = buildLocalPrediction(lat, lon, error.message || "NASA POWER 不可用");
        realtimeResult.value = fallback;
        pushHistory(lat, lon, fallback);
      }
      return;
    }

    let lastError = null;

    for (const base of bases) {
      if (controller.signal.aborted) return;
      try {
        const response = await fetch(
          `${base}/api/predict?lat=${lat}&lon=${lon}&mode=full`,
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
        if (!source.includes("NASA")) {
          throw new Error("未获取到 NASA 气候数据，请检查网络后重试");
        }
        if (result.inference_version !== INFERENCE_VERSION) {
          throw new Error("后端推理版本过旧，请重启 backend（uv run python main.py）后重试");
        }
        if (Number(result.pvpi) >= 0.999) {
          throw new Error("PVPI 结果异常（恒为 1.00），请确认已启动最新版 backend");
        }
        if (seq !== requestSeq) return;
        realtimeResult.value = result;
        pushHistory(lat, lon, result);
        return;
      } catch (error) {
        if (controller.signal.aborted) return;
        lastError = error;
      }
    }

    if (seq !== requestSeq) return;
    throw lastError || new Error("完整模型后端不可用，请确认已启动：cd backend && uv run python main.py");
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
  if (mode !== "full") {
    /* 简化公式纯前端运行，无需后端参与 */
    useFullModel.value = false;
    modelStatusText.value = "简化公式";
  } else {
    try {
      const response = await fetchFromApi("/api/toggle_mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode })
      });
      const result = await response.json();
      if (result.success) {
        useFullModel.value = true;
        if (typeof result.torch_available === "boolean") {
          torchAvailable.value = result.torch_available;
        }
        modelStatusText.value = result.model_type || modelLabel(true, torchAvailable.value);
      }
    } catch {
      // 后端不可达时仍按用户选择切换展示，预测时会给出明确错误
      useFullModel.value = true;
      modelStatusText.value = modelLabel(true, torchAvailable.value);
    }
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
  } catch {
    if (modelChoiceTouched.value) return;
    useFullModel.value = false;
    torchAvailable.value = false;
    modelStatusText.value = "简化公式";
  }
};

const rerunFromHistory = (rec) => {
  lastClickLatLng.value = { lat: rec.lat, lon: rec.lon };
  fetchPrediction(rec.lat, rec.lon);
};

const handleMapPick = ({ lat, lon }) => {
  mouseCoords.value = { lon, lat };
  lastClickLatLng.value = { lat, lon };
  fetchPrediction(lat, lon);
};

const retryAnalysis = () => {
  if (lastClickLatLng.value) {
    fetchPrediction(lastClickLatLng.value.lat, lastClickLatLng.value.lon);
  }
};

export function useRealtimeStore() {
  return {
    // state
    realtimeResult,
    historyRecords,
    isLoading,
    errorMessage,
    lastClickLatLng,
    mouseCoords,
    useFullModel,
    torchAvailable,
    modelStatusText,
    // computed
    fullModelButtonLabel,
    fullModelHint,
    loadingModelText,
    // actions
    fetchPrediction,
    toggleModel,
    checkModelStatus,
    rerunFromHistory,
    handleMapPick,
    retryAnalysis
  };
}
