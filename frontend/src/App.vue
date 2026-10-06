<template>
  <div ref="screenRef" class="screen" :class="{ 'data-load-error': dataLoadError }">
    <div class="scanline"></div>
    <div class="frame-corner tl"></div><div class="frame-corner tr"></div>
    <div class="frame-corner bl"></div><div class="frame-corner br"></div>
    <transition name="boot-fade" :duration="450">
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
        <router-link class="tab" active-class="active" to="/dashboard">选址态势</router-link>
        <router-link class="tab" active-class="active" to="/resource">资源收益评估</router-link>
        <router-link class="tab" active-class="active" to="/realtime">实时选址</router-link>
      </nav>
      <div class="timebox">
        <strong>{{ currentTime }}</strong>
        <span>{{ currentDate }}</span>
      </div>
    </header>

    <router-view />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

import { useFitScreen } from "@/composables/useFitScreen";
import { useSolarDataStore } from "@/stores/solarData";

const solar = useSolarDataStore();
const { dataLoadError } = solar;

const screenRef = ref(null);
useFitScreen(screenRef);

const booting = ref(true);
const currentTime = ref("--:--:--");
const currentDate = ref("");
let clockTimer;

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

onMounted(async () => {
  tick();
  clockTimer = window.setInterval(tick, 1000);
  // 地图边界与业务数据并行加载；任一失败不阻塞启动（页面会展示对应错误态）
  const [mapResult] = await Promise.allSettled([solar.loadChinaMap(), solar.loadData()]);
  if (mapResult.status === "rejected") {
    console.error("中国地图边界加载失败");
  }
  booting.value = false;
});

onBeforeUnmount(() => {
  window.clearInterval(clockTimer);
});
</script>
