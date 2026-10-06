/* ECharts 实例的视图级生命周期管理：统一 init/resize/dispose。
   initChart 对同一 DOM 复用已有实例，支持联动场景下反复 setOption 重绘。 */

import * as echarts from "echarts/core";
import { onBeforeUnmount, onMounted } from "vue";

export function useCharts() {
  const charts = [];

  const initChart = (el) => {
    let chart = echarts.getInstanceByDom(el);
    if (!chart) {
      chart = echarts.init(el, "bigscreen");
      charts.push(chart);
    }
    return chart;
  };

  const disposeAll = () => {
    charts.forEach((chart) => chart.dispose());
    charts.length = 0;
  };

  const resizeAll = () => {
    charts.forEach((chart) => chart.resize());
  };

  onMounted(() => window.addEventListener("resize", resizeAll));
  onBeforeUnmount(() => {
    window.removeEventListener("resize", resizeAll);
    disposeAll();
  });

  return { charts, initChart, disposeAll, resizeAll };
}
