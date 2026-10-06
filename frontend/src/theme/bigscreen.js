/* 按需引入 ECharts：只注册项目用到的图表/组件/渲染器，减小产物体积 */
import * as echarts from "echarts/core";
import { BarChart, CandlestickChart, GaugeChart, LineChart, PieChart, RadarChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  CandlestickChart,
  GaugeChart,
  LineChart,
  PieChart,
  RadarChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer
]);

/* 大屏 ECharts 主题：注册一次，所有图表 init 时传入 "bigscreen"。
   各系列自身的颜色/渐变仍可在 setOption 里覆盖。 */
echarts.registerTheme("bigscreen", {
  backgroundColor: "transparent",
  textStyle: { color: "#8fb3d9", fontFamily: "Bahnschrift, Microsoft YaHei, sans-serif" },
  color: ["#00d4fe", "#00ffa3", "#ffc53d", "#ff6b6b", "#7df0ff", "#0e4b8f"],
  axisPointer: { lineStyle: { color: "rgba(0, 212, 254, 0.4)" } },
  categoryAxis: {
    axisLine: { lineStyle: { color: "rgba(143, 179, 217, 0.25)" } },
    axisTick: { show: false },
    axisLabel: { color: "#8fb3d9" },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: "#8fb3d9" },
    splitLine: { lineStyle: { color: "rgba(143, 179, 217, 0.12)", type: "dashed" } },
  },
  logAxis: { axisLine: { show: false }, axisLabel: { color: "#8fb3d9" }, splitLine: { lineStyle: { color: "rgba(143, 179, 217, 0.12)", type: "dashed" } } },
  timeAxis: { axisLine: { lineStyle: { color: "rgba(143, 179, 217, 0.25)" } }, axisLabel: { color: "#8fb3d9" }, splitLine: { lineStyle: { color: "rgba(143, 179, 217, 0.12)", type: "dashed" } } },
  tooltip: {
    backgroundColor: "rgba(8, 20, 40, 0.92)",
    borderColor: "rgba(0, 212, 254, 0.4)",
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: "#e6f4ff", fontSize: 12 },
    extraCssText: "backdrop-filter: blur(6px); box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5); border-radius: 4px;",
  },
  legend: { textStyle: { color: "#8fb3d9", fontSize: 11 }, itemWidth: 10, itemHeight: 10, itemGap: 14 },
});
