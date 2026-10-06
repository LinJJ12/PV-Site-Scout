import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = path.resolve(frontendDir, "..");
const dataDir = path.join(frontendDir, "public", "data");

const stationCsv = path.join(projectRoot, "backend", "data", "solar", "pv_stations_mcdm_scored.csv");
const stationTarget = path.join(dataDir, "pv_stations_mcdm_scored.csv");
const statsTarget = path.join(dataDir, "provincial_statistics.csv");

await mkdir(dataDir, { recursive: true });

const parseCsv = (text) => {
  const [headerLine, ...lines] = text.trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines.map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  });
};

const formatNumber = (value, digits = 8) => {
  const fixed = Number(value).toFixed(digits);
  return fixed.replace(/\.?0+$/, "");
};

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
};

let stationText;
try {
  stationText = await readFile(stationCsv, "utf8");
} catch {
  // 全新克隆默认不含 backend/data/（已 gitignore）。跳过同步而不是让 dev/build 失败，
  // 前端仍可启动；需要完整站点表时按 README 准备数据后再运行本脚本。
  console.warn(`[sync:data] 未找到 ${path.relative(projectRoot, stationCsv)}，已跳过站点数据同步（不影响启动）`);
  process.exit(0);
}
const stations = parseCsv(stationText);
const byProvince = new Map();

for (const station of stations) {
  const province = station.province;
  const area = Number(station.area_km2);
  if (!province || !Number.isFinite(area)) {
    throw new Error(`invalid station row while generating statistics: ${JSON.stringify(station)}`);
  }
  if (!byProvince.has(province)) {
    byProvince.set(province, []);
  }
  byProvince.get(province).push(area);
}

const statsRows = [...byProvince.entries()]
  .map(([province, areas]) => {
    const totalArea = areas.reduce((sum, area) => sum + area, 0);
    return [
      province,
      areas.length,
      formatNumber(totalArea),
      formatNumber(totalArea / areas.length),
      formatNumber(median(areas))
    ];
  })
  .sort((a, b) => Number(b[2]) - Number(a[2]));

const statsText = [
  "province,Count,Total_Area_km2,Mean_Area_km2,Median_Area_km2",
  ...statsRows.map((row) => row.join(","))
].join("\n") + "\n";

await copyFile(stationCsv, stationTarget);
await writeFile(statsTarget, statsText, "utf8");

console.log(`synced ${path.relative(projectRoot, stationCsv)} -> ${path.relative(frontendDir, stationTarget)}`);
console.log(`generated ${path.relative(frontendDir, statsTarget)} from real station data`);
