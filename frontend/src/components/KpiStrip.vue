<template>
  <div class="kpi-strip">
    <div class="kpi" v-for="item in items" :key="item.label" :class="{ hero: item.hero }">
      <span class="label"><i></i>{{ item.label }}</span>
      <span class="value"><b>{{ renderOf(item) }}</b><small v-if="item.unit">{{ item.unit }}</small></span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";

/* 顶部 KPI 翻牌条：数值变化时 1.2s ease-out count-up 滚动 */
const props = defineProps({
  items: { type: Array, default: () => [] },
});

const fmt = (v, digits = 0) =>
  Number(v || 0).toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const displays = ref([]);
const renderOf = (item) => {
  const index = props.items.indexOf(item);
  return displays.value[index] ?? fmt(0, item.digits || 0);
};

const animate = (list) => {
  const start = performance.now();
  const from = list.map((item, i) => Number(String(displays.value[i] ?? "0").replace(/,/g, "")) || 0);
  const step = (now) => {
    const p = Math.min(1, (now - start) / 1200);
    const ease = 1 - Math.pow(1 - p, 3);
    displays.value = list.map((item, i) => fmt((from[i] || 0) + (Number(item.value) - (from[i] || 0)) * ease, item.digits || 0));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
};

watch(() => props.items, animate, { immediate: true, deep: true });
</script>
