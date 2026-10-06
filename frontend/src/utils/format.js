/* 无状态的格式化与统计工具 */

export const formatNumber = (value, digits = 0) =>
  Number(value || 0).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  });

export const quantile = (values, q) => {
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  return sorted[base + 1] === undefined ? sorted[base] : sorted[base] + rest * (sorted[base + 1] - sorted[base]);
};

/* 简易 CSV 解析：站点表/省级统计均为无引号单行记录 */
export const parseCsv = (text) => {
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
