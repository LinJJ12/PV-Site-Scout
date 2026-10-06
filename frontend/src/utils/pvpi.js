/* PVPI 计算与分级（实时预测口径 0~1；静态数据口径 0~100 按分位阈值） */

export const classifyPvpi = (pvpi) => {
  if (pvpi >= 0.8) return { level: "优选区", level_color: "#00ffa3", suitability: "极高" };
  if (pvpi >= 0.6) return { level: "适宜区", level_color: "#00d4fe", suitability: "高" };
  if (pvpi >= 0.4) return { level: "备选区", level_color: "#ffc53d", suitability: "中等" };
  return { level: "约束区", level_color: "#ff6b6b", suitability: "低" };
};

export const calculateSimplePvpi = (solarData) => {
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

/* 静态数据 PVPI 为 0~100 分，按与占比面板一致的分位阈值分级 */
export const gradeOf100 = (value, thresholds) => {
  const [t0, t1, t2] = thresholds;
  if (value >= t0) return { name: "优选区", color: "#00ffa3" };
  if (value >= t1) return { name: "适宜区", color: "#00d4fe" };
  if (value >= t2) return { name: "备选区", color: "#ffc53d" };
  return { name: "约束区", color: "#ff6b6b" };
};
