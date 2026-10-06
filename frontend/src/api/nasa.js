/* NASA POWER 直连客户端（简化公式模式专用，纯前端获取气候数据）。
   与后端 src/lib/solar_data.py 同口径：同样的参数、清洗规则与统计方法，
   并复用其 0.5° 网格缓存策略（NASA 对同一位置持续重复请求会限流）。 */

const BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point";
const START_YEAR = 2020;
const END_YEAR = 2023;

/* 各要素的物理合理范围，用于剔除填充值与异常值（与 Python 端一致） */
const PHYSICAL_BOUNDS = {
  ALLSKY_SFC_SW_DWN: [0, 40],
  T2M: [-90, 60],
  PRECTOTCORR: [0, 2000],
  PRECTOT: [0, 2000]
};
const FILL_SENTINELS = new Set([-999, -99]);

/* ---------- 0.5° 网格缓存（历史数据不变，24h TTL，上限淘汰最早条目） ---------- */
const CACHE_TTL_MS = 24 * 3600 * 1000;
const CACHE_MAX = 2048;
const gridCache = new Map();

const gridCell = (lat, lon) =>
  `${Math.floor(lat * 2) / 2},${Math.floor(lon * 2) / 2}`;

const cacheGet = (key) => {
  const entry = gridCache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > CACHE_TTL_MS) {
    gridCache.delete(key);
    return null;
  }
  return entry.data;
};

const cachePut = (key, data) => {
  if (gridCache.size >= CACHE_MAX) {
    const oldest = gridCache.keys().next().value;
    gridCache.delete(oldest);
  }
  gridCache.set(key, { data, ts: Date.now() });
};

/* ---------- 数据清洗与统计 ---------- */

const cleanSeries = (values, [low, high]) => {
  const cleaned = [];
  for (const value of values) {
    const num = Number(value);
    if (Number.isFinite(num) && !FILL_SENTINELS.has(num) && num >= low && num <= high) {
      cleaned.push(num);
    }
  }
  return cleaned;
};

const mean = (arr) => arr.reduce((sum, v) => sum + v, 0) / arr.length;
const std = (arr) => {
  const m = mean(arr);
  return Math.sqrt(arr.reduce((sum, v) => sum + (v - m) ** 2, 0) / arr.length);
};

const toSolarData = (parameter, source) => {
  const ghi = cleanSeries(Object.values(parameter.ALLSKY_SFC_SW_DWN || {}), PHYSICAL_BOUNDS.ALLSKY_SFC_SW_DWN);
  const temp = cleanSeries(Object.values(parameter.T2M || {}), PHYSICAL_BOUNDS.T2M);
  const precipRaw = parameter.PRECTOTCORR && Object.keys(parameter.PRECTOTCORR).length
    ? parameter.PRECTOTCORR
    : parameter.PRECTOT;
  const precip = cleanSeries(Object.values(precipRaw || {}), PHYSICAL_BOUNDS.PRECTOTCORR);

  if (!ghi.length || !temp.length || !precip.length) return null;
  const numYears = END_YEAR - START_YEAR + 1;
  const result = {
    ghi_annual_mean: mean(ghi),
    ghi_annual_std: std(ghi),
    temp_annual_mean: mean(temp),
    temp_annual_std: std(temp),
    precip_annual_mean: precip.reduce((sum, v) => sum + v, 0) / numYears
  };
  if (!Object.values(result).every(Number.isFinite)) return null;
  return { ...result, source };
};

/* ---------- 对外接口 ---------- */

const requestNasa = async (lat, lon, signal) => {
  const params = new URLSearchParams({
    parameters: "ALLSKY_SFC_SW_DWN,T2M,PRECTOTCORR",
    community: "RE",
    longitude: lon,
    latitude: lat,
    start: `${START_YEAR}0101`,
    end: `${END_YEAR}1231`,
    format: "JSON"
  });
  const response = await fetch(`${BASE_URL}?${params}`, { signal });
  if (!response.ok) throw new Error(`NASA POWER 响应异常：${response.status}`);
  const payload = await response.json();
  const parameter = payload?.properties?.parameter;
  if (!parameter) throw new Error("NASA POWER 返回数据结构异常");
  return parameter;
};

/* 获取指定位置的气候数据（带网格缓存与重试），失败时抛错由调用方兜底 */
export const fetchNasaSolar = async (lat, lon, { signal, retries = 3 } = {}) => {
  const key = gridCell(lat, lon);
  const cached = cacheGet(key);
  if (cached) return { ...cached, source: "NASA POWER 2020-2023 (cached)" };

  let lastError = null;
  for (let attempt = 0; attempt < retries; attempt++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    try {
      const parameter = await requestNasa(lat, lon, signal);
      const solarData = toSolarData(parameter, "NASA POWER 2020-2023");
      if (!solarData) throw new Error("NASA POWER 返回无效气候序列");
      cachePut(key, solarData);
      return solarData;
    } catch (error) {
      if (error.name === "AbortError") throw error;
      lastError = error;
      if (attempt < retries - 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500 * (attempt + 1)));
      }
    }
  }
  throw lastError || new Error("NASA POWER 请求失败");
};
