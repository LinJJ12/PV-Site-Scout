<template>
  <div class="rank-rows">
    <div class="rank-row" v-for="(item, index) in items" :key="item.name">
      <span class="no" :class="{ top: index < 3 }">{{ String(index + 1).padStart(2, "0") }}</span>
      <span class="name">{{ item.name }}</span>
      <span class="bar"><b :style="{ width: ready ? widthOf(item) : '0%' }"></b></span>
      <strong>{{ item.text ?? item.value }}</strong>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref } from "vue";

/* 胶囊排行条（参照 DataV CapsuleChart 形态）：宽度按最大值归一化，入场生长动画 */
const props = defineProps({
  items: { type: Array, default: () => [] },
});

const ready = ref(false);
const widthOf = (item) => {
  const max = Math.max(...props.items.map((row) => Number(row.value) || 0), 1);
  return `${(Number(item.value) / max) * 100}%`;
};
nextTick(() => {
  requestAnimationFrame(() => (ready.value = true));
});
</script>
